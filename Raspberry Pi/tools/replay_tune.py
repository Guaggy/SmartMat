"""Replay a recording through the analysis pipeline without the GUI and count events, to tune thresholds.

    python tools/replay_tune.py --file samples/seat_take1.json
    python tools/replay_tune.py --set HOTSPOT_ACTIVATE_KPA=30 --set HEALTH_NOISE_STD=8
    python tools/replay_tune.py --sweep HOTSPOT_ACTIVATE_FRACTION=0,1.5,2,2.5

Runs the same classes as gui/desktop.py's _handle_new_frame (Live mode, no tare, the default pressure
curve from config). --set NAME=value overrides a config value for the run. "Idle" is everything before
the first contact frame; "settled" starts SETTLE_S after it.
"""

import argparse
import ast
from collections import Counter
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # the app folder

import config  # noqa: E402
from processing.calibration import Calibration, PressureCalibration, cell_size_mm  # noqa: E402
from processing.frames import process_frame  # noqa: E402
from processing.hotspots import HotspotTracker  # noqa: E402
from processing.modes import LiveMode  # noqa: E402
from processing.motion import MotionAnalyzer  # noqa: E402
from processing.occupancy import OccupancyDetector  # noqa: E402
from processing.recording import load_session  # noqa: E402
from processing.sensor_health import HEALTH_STATES, SensorHealth  # noqa: E402
from processing.statistics import contact_mask  # noqa: E402
from processing.temporal import TemporalAnalysis  # noqa: E402

DEFAULT_FILE = Path(__file__).resolve().parent.parent / "samples" / "seat_take1.json"
SETTLE_S = 5.0


def _patch(overrides):
    """Set config values and every processing module's `from config import` copy; returns the undo list"""
    undo = []
    modules = [config] + [module for name, module in sys.modules.items()
                          if name.startswith("processing.") and module is not None]
    for name, value in overrides.items():
        if not any(hasattr(module, name) for module in modules):
            raise SystemExit(f"Unknown config value: {name}")
        for module in modules:
            if hasattr(module, name):
                undo.append((module, name, getattr(module, name)))
                setattr(module, name, value)
    return undo


def replay(path=DEFAULT_FILE, overrides=None):
    """Run the recording through the pipeline; return a dict of counts (see main for the meaning)"""
    frames, timestamps, metadata, _ = load_session(path, with_details=True)
    if timestamps is None:
        timestamps = [index * 0.1 for index in range(len(frames))]
    rows, cols = frames[0].shape
    undo = _patch({"TOTAL_ROWS": rows, "TOTAL_COLS": cols, **(overrides or {})})
    try:
        size = metadata.get("mat_size_mm")
        size = cell_size_mm(tuple(size), rows, cols) if size else None
        cell_area = None if size is None else size[0] * size[1] / 1_000_000
        contact = config.CONTACT_THRESHOLD_KPA
        mode, calibration, pressure_calibration = LiveMode(), Calibration(), PressureCalibration.default()
        temporal, hotspots, motion = TemporalAnalysis(), HotspotTracker(), MotionAnalyzer()
        occupancy, health = OccupancyDetector(), SensorHealth()

        events, health_frames = Counter(), Counter()
        idle = Counter()
        settled_starts, first_contact = 0, None
        previous_relief = previous_health = previous_occupied = None
        for grid, timestamp in zip(frames, timestamps):
            frame = process_frame(grid, mode, calibration, pressure_calibration)
            pressure = frame["pressure"]
            loaded = int(contact_mask(pressure, contact).sum())
            if first_contact is None and loaded:
                first_contact = timestamp
            temporal.update(pressure, timestamp)
            if temporal.last_event:
                events[temporal.last_event] += 1
            if previous_relief is not None:
                events["relief_cell_changes"] += int(np.count_nonzero(temporal.state != previous_relief))
            previous_relief = temporal.state.copy()
            for kind, _track in hotspots.update(pressure, timestamp, temporal, cell_area):
                events[kind] += 1
                if kind == "hotspot_started" and first_contact is not None and \
                        timestamp >= first_contact + SETTLE_S:
                    settled_starts += 1
            for _kind, payload in motion.update(pressure, timestamp, contact, cell_area,
                                                hotspots.active, temporal):
                category = payload.get("movement", {}).get("category", "reposition")
                events[category] += 1
            occupied = occupancy.update(pressure, timestamp, contact)
            if previous_occupied is not None and occupied != previous_occupied:
                events["occupancy_changes"] += 1
            previous_occupied = occupied
            health.update(frame["raw"], timestamp, pressure=pressure, contact_threshold_kpa=contact,
                          pressure_calibration=pressure_calibration)
            states = health.states.copy()
            health_frames.update(HEALTH_STATES[state] for state in states.ravel())
            if previous_health is not None:
                events["health_cell_changes"] += int(np.count_nonzero(states != previous_health))
            previous_health = states
            if first_contact is None:
                idle["frames"] += 1
                idle["hotspots"] += len(hotspots.active)
                idle["noisy_cells"] += int(np.count_nonzero(states == 1))
                idle["occupied_frames"] += bool(occupied)
        duration = timestamps[-1] - timestamps[0]
        settled_s = 0.0 if first_contact is None else max(0.0, timestamps[-1] - first_contact - SETTLE_S)
        total = sum(health_frames.values())
        return {
            "file": str(path), "frames": len(frames), "duration_s": duration,
            "fps": (len(frames) - 1) / duration if duration > 0 else 0.0,
            "first_contact_s": None if first_contact is None else first_contact - timestamps[0],
            "events": dict(events),
            "per_min": {kind: count * 60 / duration for kind, count in events.items()} if duration > 0 else {},
            "idle": dict(idle),
            "settled_new_hotspots": settled_starts,
            "settled_new_hotspots_per_min": settled_starts * 60 / settled_s if settled_s > 0 else 0.0,
            "health_share": {state: count / total for state, count in health_frames.items()},
        }
    finally:
        for module, name, value in reversed(undo):
            setattr(module, name, value)


def _value(text):
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text


def _print(result, label):
    print(f"== {label}")
    print(f"  {result['frames']} frames, {result['duration_s']:.1f} s, {result['fps']:.1f} fps, "
          f"first contact at {result['first_contact_s']} s")
    idle = result["idle"]
    print(f"  idle ({idle.get('frames', 0)} frames): hotspot-frames {idle.get('hotspots', 0)}, "
          f"noisy cell-frames {idle.get('noisy_cells', 0)}, occupied frames {idle.get('occupied_frames', 0)}")
    print(f"  new hotspot ids after settling: {result['settled_new_hotspots']} "
          f"({result['settled_new_hotspots_per_min']:.1f}/min)")
    for kind in sorted(result["events"]):
        print(f"  {kind:28s} {result['events'][kind]:6d}  {result['per_min'][kind]:8.1f}/min")
    shares = ", ".join(f"{state} {share:.1%}" for state, share in sorted(result["health_share"].items()))
    print(f"  health cell-frames: {shares}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Replay a recording and count analysis events")
    parser.add_argument("--file", default=str(DEFAULT_FILE), help="recording .json (default: the seat take)")
    parser.add_argument("--set", action="append", default=[], metavar="NAME=value",
                        help="override a config value (repeatable)")
    parser.add_argument("--sweep", metavar="NAME=a,b,c", help="run once per value of one config name")
    args = parser.parse_args(argv)
    overrides = {}
    for item in args.set:
        name, _, text = item.partition("=")
        overrides[name.strip()] = _value(text)
    if not args.sweep:
        _print(replay(args.file, overrides), ", ".join(args.set) or "current config")
        return
    name, _, values = args.sweep.partition("=")
    for text in values.split(","):
        _print(replay(args.file, {**overrides, name: _value(text)}), f"{name}={text}")


if __name__ == "__main__":
    main()
