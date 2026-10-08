"""Compact engineering summaries and machine-readable exports."""

import os

import numpy as np

import config
from config import CELL_WIDTH_MM, CELL_HEIGHT_MM
from processing.recording import RECORDINGS_DIR
from processing.validation import reposition_validation

SUMMARY_FORMAT = "smartmat_analysis_summary_v1"


def health_warning_count(states):
    """Cells in Saturated..Invalid (3-6); Noisy/Drifting have their own diagnostics views"""
    return int(np.count_nonzero((states >= 3) & (states <= 6)))


def readiness(app):
    source = app.source
    quality = source.quality.snapshot() if source is not None else None
    warnings = []
    if source is None:
        warnings.append("No source connected")
    elif quality["age_s"] is None or quality["age_s"] > 2:
        warnings.append("No recent valid frame")
    if quality is not None and quality["valid"] >= 10 and quality["rate_hz"] < 5:
        warnings.append("Recent source rate below 5 frames/s")
    if app.raw_grid is not None and app.raw_grid.shape != (config.TOTAL_ROWS, config.TOTAL_COLS):
        warnings.append("Grid dimensions differ from configuration")
    if not app.pressure_calibration.is_complete:
        warnings.append("Pressure calibration incomplete")
    if app.calibration.baseline is None:
        warnings.append("No tare baseline captured")
    if not CELL_WIDTH_MM or not CELL_HEIGHT_MM:
        warnings.append("Physical cell dimensions not configured")
    if not RECORDINGS_DIR.exists() or not os.access(RECORDINGS_DIR, os.W_OK):
        warnings.append("Recording directory may not be writable")
    if health_warning_count(app.sensor_health.states):
        warnings.append("Sensor-health warnings present")
    return warnings


def session_summary(app, match_window_s):
    source = app.source
    quality = source.quality.snapshot() if source is not None else None
    quality = quality or {"received": 0, "valid": 0, "malformed": 0, "dropped": 0,
                          "longest_arrival_gap_s": 0, "average_rate_hz": 0}
    annotations = [event for event in app.timeline.events if event.get("kind") == "annotation"]
    validation = reposition_validation(annotations, list(app.motion.repositions), match_window_s)
    health_warnings = health_warning_count(app.sensor_health.states)
    observed_duration = None
    if app.session_state is not None and app.frame_timestamp is not None:
        observed_duration = max(0.0, app.frame_timestamp - app.session_state["started_at"])
    data_quality = {
        "observed_duration_s": observed_duration,
        "received_frames": quality["received"], "valid_frames": quality["valid"],
        "valid_frame_percent": (100 * quality["valid"] / quality["received"]
                                if quality["received"] else None),
        "malformed_frames": quality["malformed"], "dropped_frames": quality["dropped"],
        "longest_arrival_gap_s": quality["longest_arrival_gap_s"],
        "average_arrival_fps": quality["average_rate_hz"],
        "calibrated_cells": app.pressure_calibration.calibrated_count,
        "calibrated_percent": 100 * app.pressure_calibration.calibrated_count / (config.TOTAL_ROWS * config.TOTAL_COLS),
        "baseline_present": app.calibration.baseline is not None,
        "sensor_health_warnings": health_warnings,
        "unknown_temporal_cells": int(np.count_nonzero(app.temporal.state == 0)),
        "unknown_temporal_percent": float(np.count_nonzero(app.temporal.state == 0) /
                                          app.temporal.state.size * 100),
    }
    events = {
        "hotspots_observed": app.hotspots.created_total,
        "persistent_hotspots": app.hotspots.persistent_total,
        "longest_observed_hotspot_s": app.hotspots.longest_observed_s,
        "movement_events": app.motion.movement_total,
        "major_movements": app.motion.major_total,
        "reposition_events": app.motion.reposition_total,
        "manual_repositions": sum(item.get("payload", {}).get("type") == "Known reposition"
                                  for item in annotations),
        "total_cell_exposure_kpa_min": float(np.sum(app.temporal.exposure)),
        "maximum_cell_burden": float(np.max(app.temporal.burden)),
    }
    timeline = []
    for event in app.timeline.events:
        compact = {key: event[key] for key in ("timestamp", "kind", "note", "frame_index") if key in event}
        if event.get("kind") in ("annotation", "reposition_detected", "movement"):
            compact["payload"] = event.get("payload")
        timeline.append(compact)
    return {
        "format": SUMMARY_FORMAT,
        "session_initial": app.session_state,
        "experiment": app.experiment_info.copy(),
        "playback_policy": app._replay_policy if app._playback_metadata is not None else None,
        "preset": app.preset_name,
        "settings": app.current_settings(),
        "data_quality": data_quality,
        "pressure_statistics": app.stats,
        "algorithm_events": events,
        "reposition_validation": validation,
        "readiness_warnings": readiness(app),
        "timeline": timeline,
    }
