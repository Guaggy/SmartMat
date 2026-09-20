"""Compare event counts from two settings without changing the loaded recording."""

import numpy as np

from config import CONTACT_THRESHOLD_KPA
from processing.calibration import Calibration, PressureCalibration
from processing.frames import process_frame
from processing.hotspots import HotspotTracker
from processing.modes import LiveMode, AverageMode, ExponentialAverageMode
from processing.motion import MotionAnalyzer
from processing.session_events import STATE_EVENTS, apply_state_event, event_is_due
from processing.settings import apply_settings, default_settings
from processing.temporal import TemporalAnalysis


def analyze_recording(frames, timestamps, metadata, events, settings=None, cell_area_m2=None):
    """Replay raw frames with recorded settings, or supplied experimental settings."""
    calibration = Calibration()
    pressure_calibration = PressureCalibration()
    temporal = TemporalAnalysis()
    hotspots = HotspotTracker()
    motion = MotionAnalyzer()
    modes = {mode.label: mode for mode in (LiveMode(), AverageMode(), ExponentialAverageMode())}
    if metadata.get("pressure_calibration"):
        pressure_calibration.load_dict(metadata["pressure_calibration"])
    if metadata.get("baseline_processed") is not None:
        calibration.baseline = np.asarray(metadata["baseline_processed"], dtype=float)
    reproduce = settings is None
    if reproduce:
        settings = default_settings()
        settings["contact_threshold_kpa"] = metadata.get("contact_threshold_kpa", CONTACT_THRESHOLD_KPA)
        for group in ("temporal", "hotspots", "movement"):
            settings[group].update(metadata.get(group, {}))
    threshold = apply_settings(settings, temporal, hotspots, motion)
    mode = modes.get(metadata.get("processing_mode", "Live"), modes["Live"])
    parameter = metadata.get("processing_parameter")
    if parameter is not None and mode.param_label:
        mode.set_param(parameter)
    state_events = [event for event in events if event.get("kind") in STATE_EVENTS]
    event_index = 0
    counts = {"hotspots": 0, "movements": 0, "repositions": 0}
    for index, raw in enumerate(frames):
        timestamp = timestamps[index] if timestamps is not None else index * 0.1
        while event_index < len(state_events) and event_is_due(state_events[event_index], index, timestamp):
            event = state_events[event_index]
            event_index += 1
            if not reproduce and event["kind"] in ("algorithm_settings_changed",
                    "temporal_parameters_changed", "processing_mode_changed", "contact_threshold_changed"):
                continue
            new_threshold = apply_state_event(event, calibration, pressure_calibration,
                                              temporal, hotspots, motion)
            if new_threshold is not None:
                threshold = new_threshold
            if reproduce and event["kind"] == "processing_mode_changed":
                payload = event["payload"]
                mode = modes.get(payload["mode"], modes["Live"])
                mode.reset()
                if payload.get("parameter") is not None and mode.param_label:
                    mode.set_param(payload["parameter"])
            temporal.invalidate()
            hotspots.invalidate()
            motion.invalidate()
        frame = process_frame(np.asarray(raw, dtype=float), mode, calibration, pressure_calibration)
        pressure = frame["pressure"]
        temporal.update(pressure, timestamp)
        hotspot_events = hotspots.update(pressure, timestamp, temporal, cell_area_m2)
        motion_events = motion.update(pressure, timestamp, threshold, cell_area_m2,
                                      hotspots.active, temporal)
        counts["hotspots"] += sum(kind == "hotspot_started" for kind, _ in hotspot_events)
        counts["movements"] += sum(kind == "movement" for kind, _ in motion_events)
        counts["repositions"] += sum(kind == "reposition_detected" for kind, _ in motion_events)
    return counts


def compare_recording(frames, timestamps, metadata, events, current_settings, cell_area_m2=None):
    original = analyze_recording(frames, timestamps, metadata, events, cell_area_m2=cell_area_m2)
    current = analyze_recording(frames, timestamps, metadata, events, current_settings,
                                cell_area_m2=cell_area_m2)
    return {"recorded_settings": original, "current_settings": current,
            "difference": {key: current[key] - original[key] for key in original}}
