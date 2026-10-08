"""Validated engineering settings and human-readable presets."""

import json
import math
from pathlib import Path

from config import CONTACT_THRESHOLD_KPA
from processing.hotspots import HotspotTracker
from processing.indices import validate_indices
from processing.motion import MotionAnalyzer
from processing.temporal import TemporalAnalysis

PRESET_FORMAT = "smartmat_engineering_preset_v1"


def capture_settings(contact_threshold, temporal, hotspots, motion):
    return {"contact_threshold_kpa": float(contact_threshold),
            "temporal": temporal.settings(), "hotspots": hotspots.settings(),
            "movement": motion.settings()}


def default_settings():
    return capture_settings(CONTACT_THRESHOLD_KPA, TemporalAnalysis(),
                            HotspotTracker(), MotionAnalyzer())


def builtin_preset(name):
    settings = default_settings()
    if name == "Default":
        return settings
    hotspot = settings["hotspots"]
    movement = settings["movement"]
    if name == "Sensitive":
        hotspot["activate_kpa"] *= 0.75
        hotspot["deactivate_kpa"] *= 0.75
        hotspot["persistence_s"] *= 0.5
        movement["small_score"] *= 0.75
        movement["significant_score"] *= 0.75
        movement["major_score"] *= 0.75
        movement["reposition_min_score"] *= 0.75
    elif name == "Conservative":
        hotspot["activate_kpa"] *= 1.25
        hotspot["deactivate_kpa"] *= 1.25
        hotspot["persistence_s"] *= 2
        movement["small_score"] = min(0.9, movement["small_score"] * 1.25)
        movement["significant_score"] = min(0.95, movement["significant_score"] * 1.25)
        movement["major_score"] = min(1.0, movement["major_score"] * 1.25)
        movement["reposition_min_score"] = min(1.0, movement["reposition_min_score"] * 1.25)
        movement["reposition_min_change"] = min(1.0, movement["reposition_min_change"] * 1.25)
    elif name == "Experimental":
        settings["temporal"]["exposure_mode"] = "Above threshold"
        hotspot["persistence_s"] = 10.0
        movement["before_s"] = 15.0
        movement["after_s"] = 15.0
    else:
        raise ValueError("Unknown preset")
    return settings


def validate_settings(settings):
    if not isinstance(settings, dict):
        raise ValueError("Settings must be a JSON object")
    defaults = default_settings()
    result = {}
    try:
        contact = float(settings["contact_threshold_kpa"])
        if not math.isfinite(contact) or contact < 0:
            raise ValueError
        result["contact_threshold_kpa"] = contact
        for group in ("temporal", "hotspots", "movement"):
            source = settings[group]
            result[group] = {}
            for key, original in defaults[group].items():
                value = source[key]
                if key == "exposure_mode":
                    if value not in ("Full pressure", "Above threshold"):
                        raise ValueError
                elif isinstance(original, int) and not isinstance(original, bool):
                    number = float(value)
                    if not math.isfinite(number) or not number.is_integer() or number < 0:
                        raise ValueError
                    value = int(number)
                else:
                    value = float(value)
                    if not math.isfinite(value) or value < 0:
                        raise ValueError
                result[group][key] = value
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("Preset has missing or invalid values") from error
    h, m, t = result["hotspots"], result["movement"], result["temporal"]
    if not (0 <= h["deactivate_kpa"] < h["activate_kpa"] and h["min_cells"] >= 1 and
            h["max_move_cells"] >= 0 and h["persistence_s"] >= 0 and h["end_relief_s"] >= 0):
        raise ValueError("Hotspot thresholds or durations are invalid")
    if not (0 <= m["small_score"] < m["significant_score"] < m["major_score"] <= 1 and
            m["cop_scale_cells"] > 0 and 0 <= m["reposition_min_score"] <= 1 and
            0 <= m["reposition_min_change"] <= 1 and m["before_s"] > 0 and m["after_s"] > 0 and
            m["reposition_min_contact_cells"] >= 1):
        raise ValueError("Movement or reposition thresholds are invalid")
    if not (0 <= t["relief_full_ratio"] < t["relief_partial_ratio"] < 1 and
            0 < t["roi_relief_fraction"] <= 1 and t["burden_recovery_time_s"] > 0 and
            t["max_gap_s"] > 0 and t["bucket_s"] > 0):
        raise ValueError("Temporal thresholds are invalid")
    if "indices" in settings:  # absent = leave the current indices alone (older presets)
        result["indices"] = validate_indices(settings["indices"])
    return result


def save_preset(path, settings, name="Custom"):
    document = {"format": PRESET_FORMAT, "name": name,
                "settings": validate_settings(settings)}
    Path(path).write_text(json.dumps(document, indent=2), encoding="utf-8")


def load_preset(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("format") != PRESET_FORMAT:
        raise ValueError("Unsupported preset format")
    return document.get("name", "Custom"), validate_settings(document["settings"])


def apply_settings(settings, temporal, hotspots, motion):
    settings = validate_settings(settings)
    hotspot_counts = tuple(getattr(hotspots, key) for key in
                           ("created_total", "persistent_total", "ended_total", "longest_observed_s"))
    motion_counts = tuple(getattr(motion, key) for key in
                          ("movement_total", "major_total", "reposition_total"))
    bucket_changed = temporal.bucket_s != settings["temporal"]["bucket_s"]
    for key, value in settings["temporal"].items():
        setattr(temporal, key, value)
    if bucket_changed:
        temporal.reset_all()
    else:
        temporal.invalidate()
    for key, value in settings["hotspots"].items():
        setattr(hotspots, key, value)
    hotspots.reset()
    (hotspots.created_total, hotspots.persistent_total, hotspots.ended_total,
     hotspots.longest_observed_s) = hotspot_counts
    for key, value in settings["movement"].items():
        setattr(motion, key, value)
    motion.reset()
    motion.movement_total, motion.major_total, motion.reposition_total = motion_counts
    return settings["contact_threshold_kpa"]
