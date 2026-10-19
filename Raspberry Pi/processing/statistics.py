"""Contact and pressure statistics from real sensor cells."""

import numpy as np

import config
from config import HEALTH_SATURATION_MARGIN, VALUE_MAX_DEFAULT

SATURATION_WARN_CELLS = getattr(config, "SATURATION_WARN_CELLS", 1)   # an older config.py may not have it


def contact_mask(pressure_kpa, threshold_kpa):
    return np.isfinite(pressure_kpa) & (pressure_kpa > threshold_kpa)


def weighted_center(values, threshold=0.0):
    """Return the value-weighted center of real cells above a noise threshold."""
    weights = np.asarray(values, dtype=float)
    mask = np.isfinite(weights) & (weights > threshold)
    if not mask.any():
        return None, None
    rows, cols = np.nonzero(mask)
    loaded = weights[mask]
    total = loaded.sum()
    if total <= 0:
        return None, None
    return float(np.dot(cols, loaded) / total), float(np.dot(rows, loaded) / total)


def pressure_statistics(pressure_kpa, threshold_kpa, cell_area_m2=None):
    mask = contact_mask(pressure_kpa, threshold_kpa)
    count = int(mask.sum())
    stats = {"contact_cells": count, "peak_kpa": 0.0, "mean_kpa": None,
             "contact_area_m2": None, "force_n": None, "cop_x": None, "cop_y": None}
    valid = pressure_kpa[np.isfinite(pressure_kpa)]
    if valid.size:
        stats["peak_kpa"] = float(valid.max())
        if cell_area_m2 is not None:
            stats["force_n"] = float(np.maximum(valid, 0).sum() * 1000 * cell_area_m2)
    if not count:
        return stats

    loaded = pressure_kpa[mask]
    stats["mean_kpa"] = float(loaded.mean())
    if cell_area_m2 is not None:
        stats["contact_area_m2"] = count * cell_area_m2

    stats["cop_x"], stats["cop_y"] = weighted_center(pressure_kpa, threshold_kpa)
    return stats


def saturated_cells(raw_scaled_grid, value_max=VALUE_MAX_DEFAULT):
    """Cells at the sensor limit in a received (0-1000 scaled) grid; NaN cells are ignored"""
    grid = np.asarray(raw_scaled_grid, dtype=float)
    return int((np.isfinite(grid) & (grid >= value_max - HEALTH_SATURATION_MARGIN)).sum())


def load_estimate_text(force_n, default_curve=False, saturated=0):
    """Sidebar line for the rough load (force / g in kg); saturated cells make it a lower bound"""
    if force_n is None:
        return "Estimated load: set mat size"
    sign = ">= " if saturated >= SATURATION_WARN_CELLS else "~"
    text = f"Estimated load: {sign}{force_n / 9.81:.0f} kg (rough)"
    return text + " - default curve, not calibrated" if default_curve else text
