"""ROI and distribution analysis on real sensor cells."""

import numpy as np

from processing.statistics import contact_mask


def roi_statistics(grid, roi, unit, threshold_kpa=0, cell_area_m2=None):
    row0, row1, col0, col1 = roi
    values = grid[row0:row1 + 1, col0:col1 + 1]
    valid = np.isfinite(values)
    usable = values[valid]
    sensors = values.size
    result = {"sensors": sensors, "unit": unit, "area_m2": None,
              "mean": None, "peak": None, "minimum": None, "std": None,
              "force_n": None, "contact_cells": None, "contact_area_m2": None,
              "center_x": None, "center_y": None}
    if cell_area_m2 is not None:
        result["area_m2"] = sensors * cell_area_m2
    if not usable.size:
        return result
    result["mean"] = float(usable.mean())
    result["peak"] = float(usable.max())
    result["minimum"] = float(usable.min())
    result["std"] = float(usable.std())
    if unit == "kPa":
        mask = contact_mask(values, threshold_kpa)
        result["contact_cells"] = int(mask.sum())
        if cell_area_m2 is not None:
            result["contact_area_m2"] = result["contact_cells"] * cell_area_m2
            result["force_n"] = float(np.maximum(usable, 0).sum() * 1000 * cell_area_m2)
    else:
        mask = valid & (values > 0)

    rows, cols = np.nonzero(mask)
    if len(rows):
        weights = values[mask]
        result["center_x"] = float(col0 + np.dot(cols, weights) / weights.sum())
        result["center_y"] = float(row0 + np.dot(rows, weights) / weights.sum())
    return result


def pressure_distribution(pressure_kpa, threshold_kpa, bins=20, cell_area_m2=None):
    values = pressure_kpa[contact_mask(pressure_kpa, threshold_kpa)]
    result = {"values": values, "histogram": None, "bin_edges": None,
              "percentiles": None, "area_thresholds": None, "area_above": None,
              "area_unit": "cm2" if cell_area_m2 is not None else "cells"}
    if not values.size:
        return result

    result["histogram"], result["bin_edges"] = np.histogram(values, bins=bins)
    ordered = np.sort(values)
    result["percentiles"] = {fraction: float(ordered[int(np.ceil(fraction / 100 * len(ordered))) - 1])
                             for fraction in (90, 95, 99)}
    positive = pressure_kpa[np.isfinite(pressure_kpa) & (pressure_kpa > 0)]
    thresholds = np.linspace(0, float(positive.max()), 51)
    counts = np.asarray([np.count_nonzero(positive >= value) for value in thresholds])
    result["area_thresholds"] = thresholds
    result["area_above"] = counts * (cell_area_m2 * 10_000 if cell_area_m2 is not None else 1)
    return result


def load_distribution(grid, calibrated=False, cell_area_m2=None):
    values = np.where(np.isfinite(grid), np.maximum(grid, 0), 0)
    total = float(values.sum())
    if total <= 0:
        return None
    rows, cols = values.shape
    left = np.zeros(cols)
    upper = np.zeros(rows)
    left[:cols // 2] = 1
    upper[:rows // 2] = 1
    if cols % 2:
        left[cols // 2] = 0.5
    if rows % 2:
        upper[rows // 2] = 0.5
    right = 1 - left
    lower = 1 - upper
    left_percent = float((values * left).sum() / total * 100)
    upper_percent = float((values * upper[:, None]).sum() / total * 100)
    quadrants = {
        "upper_left": float((values * upper[:, None] * left).sum() / total * 100),
        "upper_right": float((values * upper[:, None] * right).sum() / total * 100),
        "lower_left": float((values * lower[:, None] * left).sum() / total * 100),
        "lower_right": float((values * lower[:, None] * right).sum() / total * 100),
    }
    return {
        "basis": "force" if calibrated and cell_area_m2 is not None else
                 ("pressure signal" if calibrated else "relative sensor signal"),
        "left": left_percent, "right": 100 - left_percent,
        "upper": upper_percent, "lower": 100 - upper_percent,
        "quadrants": quadrants,
        "left_right_imbalance": 2 * left_percent - 100,
        "upper_lower_imbalance": 2 * upper_percent - 100,
    }
