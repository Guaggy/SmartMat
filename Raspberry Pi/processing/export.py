"""CSV export of one frame (long format) and of a whole recording (wide format).

Engineering aid for looking at the data in a spreadsheet or script, nothing more.
"""

import csv
import json
from datetime import datetime, timezone

import numpy as np

SNAPSHOT_COLUMNS = ("timestamp_iso", "mat_id", "row", "col", "raw_scaled_0_1000", "baseline_subtracted", "pressure_kpa")


def _iso(timestamp):
    """UTC, so the file is unambiguous (and any timestamp converts, even a near-zero playback clock)"""
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="milliseconds")


def _cell(value):
    """Empty text for a missing or non-finite value"""
    return "" if value is None or not np.isfinite(value) else float(value)


def snapshot_rows(frame, timestamp, mat_id=""):
    """One row per cell from a processed frame dict (frames.process_frame): raw, baseline-subtracted
    and calibrated pressure (kPa). Pressure is empty for every cell when the pressure calibration
    is incomplete; any NaN cell is empty too."""
    raw, baseline = frame["raw"], frame["baseline_subtracted"]
    pressure = frame.get("pressure")
    stamp = _iso(timestamp)
    rows = []
    for row in range(raw.shape[0]):
        for col in range(raw.shape[1]):
            rows.append([stamp, mat_id or "", row, col, _cell(raw[row, col]), _cell(baseline[row, col]),
                         "" if pressure is None else _cell(pressure[row, col])])
    return rows


def write_snapshot_csv(path, frame, timestamp, mat_id=""):
    """Write snapshot_rows to a CSV file; returns the number of cells written"""
    rows = snapshot_rows(frame, timestamp, mat_id)
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(SNAPSHOT_COLUMNS)
        writer.writerows(rows)
    return len(rows)


def recording_to_csv(json_path, csv_path):
    """Convert a recordings/*.json session to a wide CSV: one row per frame, columns timestamp_iso,
    elapsed_s, then r00_c00, r00_c01, ... in row-major order. Cell values are exactly as stored in
    the recording, i.e. already scaled to the app's 0-1000 range at ingest (not calibrated kPa);
    missing cells are empty. Returns the number of frames written."""
    with open(json_path, encoding="utf-8") as file:
        session = json.load(file)
    if session.get("format") != "smartmat_raw_v1":
        raise ValueError("Not a SmartMat recording (smartmat_raw_v1)")
    rows, cols = session["grid_shape"]
    frames = session["frames"]
    start = frames[0]["timestamp"] if frames else 0.0
    header = ["timestamp_iso", "elapsed_s"] + [f"r{row:02d}_c{col:02d}" for row in range(rows) for col in range(cols)]
    with open(csv_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        for frame in frames:
            values = np.asarray(frame["raw"], dtype=float).reshape(-1)  # None -> NaN
            if values.size != rows * cols:
                raise ValueError("Recording contains an invalid frame")
            writer.writerow([_iso(frame["timestamp"]), round(frame["timestamp"] - start, 6)]
                            + [_cell(value) for value in values])
    return len(frames)
