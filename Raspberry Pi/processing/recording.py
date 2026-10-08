"""Record raw frames with timestamps, and load older CSV sessions."""

import csv
import json
import os
import tempfile
import time
from pathlib import Path

import numpy as np

import config

RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "recordings"

class Recorder:
    """Collects grids for one named session until stopped"""

    def __init__(self, name, source="Unknown", metadata=None):
        self.name = name
        self.source = source
        self.metadata = metadata or {}
        self.started_at = time.time()
        RECORDINGS_DIR.mkdir(exist_ok=True)
        self._spool = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".jsonl",
                                                  prefix="smartmat_", dir=RECORDINGS_DIR, delete=False)
        self._frame_count = 0
        self.events = []

    @property
    def frame_count(self):
        return self._frame_count

    def add_frame(self, grid, timestamp=None):
        values = np.asarray(grid, dtype=float).astype(object)
        values[~np.isfinite(grid)] = None
        json.dump({
            "timestamp": time.time() if timestamp is None else timestamp,
            "raw": values.tolist(),
        }, self._spool, allow_nan=False)
        self._spool.write("\n")
        self._frame_count += 1

    def save(self):
        """Write a raw session to recordings/<name>_<timestamp>.json"""
        RECORDINGS_DIR.mkdir(exist_ok=True)
        safe_name = "".join(char if char.isalnum() or char in "-_" else "_" for char in self.name)
        path = RECORDINGS_DIR / f"{safe_name}_{int(self.started_at * 1000)}.json"
        session = {
            "format": "smartmat_raw_v1",
            "name": self.name,
            "started_at": self.started_at,
            "source": self.source,
            "grid_shape": [config.TOTAL_ROWS, config.TOTAL_COLS],
            "units": "relative sensor value",
            "metadata": self.metadata,
            "events": self.events,
        }
        self._spool.close()
        with open(path, "w", encoding="utf-8") as file:
            file.write(json.dumps(session, allow_nan=False)[:-1] + ', "frames": [')
            with open(self._spool.name, encoding="utf-8") as spool:
                for index, line in enumerate(spool):
                    if index:
                        file.write(",")
                    file.write(line.strip())
            file.write("]}")
        os.unlink(self._spool.name)
        return path

    def discard(self):
        if not self._spool.closed:
            self._spool.close()
        if os.path.exists(self._spool.name):
            os.unlink(self._spool.name)


def load_session(path, with_timestamps=False, with_details=False):
    """Return grids, plus usable timestamps when requested."""
    timestamps = None
    raw_format = False
    metadata, events = {}, []
    if Path(path).suffix == ".json":
        with open(path) as file:
            session = json.load(file)
        metadata = session.get("metadata", {})
        events = session.get("events", [])
        if session.get("format") not in (None, "smartmat_raw_v1"):
            raise ValueError("Unsupported recording format")
        if session.get("format") == "smartmat_raw_v1":
            raw_format = True
            if session.get("grid_shape") != [config.TOTAL_ROWS, config.TOTAL_COLS]:
                raise ValueError("Recording grid size does not match configuration")
            grids = [frame["raw"] for frame in session["frames"]]
            times = [frame.get("timestamp") for frame in session["frames"]]
            if all(isinstance(value, (int, float)) and np.isfinite(value) for value in times):
                if all(later > earlier for earlier, later in zip(times, times[1:])):
                    timestamps = times
        else:
            grids = session["frames"]
    else:
        with open(path, newline="") as file:
            grids = list(csv.reader(file))

    if not grids:
        raise ValueError("Recording contains no frames")

    frames = []
    for grid in grids:
        values = np.asarray(grid, dtype=float)
        if values.size != config.TOTAL_ROWS * config.TOTAL_COLS or (not raw_format and not np.all(np.isfinite(values))):
            raise ValueError("Recording contains an invalid frame")
        frames.append(values.reshape(config.TOTAL_ROWS, config.TOTAL_COLS))
    if with_details:
        return frames, timestamps, metadata, events
    return (frames, timestamps) if with_timestamps else frames


def load_session_details(path):
    if Path(path).suffix != ".json":
        return {}, []
    with open(path) as file:
        session = json.load(file)
    return session.get("metadata", {}), session.get("events", [])
