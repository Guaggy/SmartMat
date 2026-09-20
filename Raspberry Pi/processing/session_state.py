"""A small snapshot of what was actually known at session start."""

import numpy as np

from processing.statistics import contact_mask


def initial_session_state(timestamp, source, raw_grid, pressure, calibration,
                          baseline, contact_threshold, hotspots):
    valid_raw = np.isfinite(raw_grid)
    if pressure is None or not np.any(np.isfinite(pressure)):
        occupancy = "unknown"
        contact_cells = None
    else:
        contacted = contact_mask(pressure, contact_threshold)
        occupancy = "loaded" if contacted.any() else "unloaded"
        contact_cells = int(contacted.sum())
    return {
        "started_at": float(timestamp),
        "source": source,
        "grid_shape": list(raw_grid.shape),
        "valid_raw_cells": int(valid_raw.sum()),
        "calibrated_cells": calibration.calibrated_count,
        "calibration_complete": calibration.is_complete,
        "baseline_present": baseline is not None,
        "occupancy": occupancy,
        "contact_cells": contact_cells,
        "initial_hotspot_ids": [track["id"] for track in hotspots.active],
        "prior_pressure_history_known": False,
        "prior_relief_history_known": False,
        "source_status": "valid frame received",
    }
