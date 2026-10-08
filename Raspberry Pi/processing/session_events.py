"""Apply recorded state changes to a playback-only processing session."""

import numpy as np

import config
from processing.settings import apply_settings

STATE_EVENTS = {
    "tare_captured", "baseline_cleared", "calibration_changed",
    "calibration_loaded", "temporal_parameters_changed",
    "processing_mode_changed", "contact_threshold_changed",
    "algorithm_settings_changed",
}


def event_is_due(event, frame_index, timestamp):
    if event.get("kind") not in STATE_EVENTS:
        return False
    if "frame_index" in event:
        return event["frame_index"] <= frame_index
    return event.get("timestamp", float("inf")) < timestamp


def apply_state_event(event, calibration, pressure_calibration, temporal,
                      hotspots=None, motion=None):
    kind = event.get("kind")
    payload = event.get("payload")
    if kind == "tare_captured":
        baseline = np.asarray(payload["baseline"], dtype=float)
        if baseline.shape != (config.TOTAL_ROWS, config.TOTAL_COLS):
            raise ValueError("Recorded tare grid has the wrong size")
        calibration.baseline = baseline.copy()
    elif kind == "baseline_cleared":
        calibration.baseline = None
    elif kind in ("calibration_changed", "calibration_loaded"):
        pressure_calibration.load_dict(payload["calibration"])
    elif kind == "temporal_parameters_changed":
        for key, value in payload["temporal"].items():
            if key in temporal.settings():
                setattr(temporal, key, value)
    elif kind == "contact_threshold_changed":
        return float(payload["threshold_kpa"])
    elif kind == "algorithm_settings_changed" and hotspots is not None and motion is not None:
        return apply_settings(payload["settings"], temporal, hotspots, motion)
    return None
