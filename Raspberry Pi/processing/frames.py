"""Keep each sensor frame's processing stages separate."""

import numpy as np

from config import VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT


def process_frame(grid, mode, calibration, pressure_calibration=None):
    raw = grid.copy()
    valid = np.isfinite(raw) & (raw >= VALUE_MIN_DEFAULT) & (raw <= VALUE_MAX_DEFAULT)
    filtered = mode.apply(np.where(valid, raw, np.nan)).copy()
    baseline_subtracted = calibration.apply_baseline(filtered).copy()
    frame = {
        "raw": raw,
        "filtered": filtered,
        "baseline_subtracted": baseline_subtracted,
        "display": baseline_subtracted.copy(),
    }
    update_pressure(frame, calibration, pressure_calibration)
    return frame


def update_pressure(frame, calibration, pressure_calibration):
    frame["calibrated_pressure"] = None
    frame["pressure"] = None
    if pressure_calibration is None or not pressure_calibration.is_complete:
        return
    calibrated = pressure_calibration.apply(frame["filtered"])
    pressure = calibrated.copy()
    if calibration.baseline is not None:
        baseline_pressure = pressure_calibration.apply(calibration.baseline)
        pressure = np.maximum(0.0, pressure - baseline_pressure)
    frame["calibrated_pressure"] = calibrated
    frame["pressure"] = pressure
