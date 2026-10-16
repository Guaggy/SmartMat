"""One mat's analysis pipeline without a GUI: the same processing/* steps the desktop runs in _poll."""

import threading
import time
from contextlib import contextmanager

import numpy as np

import config
from processing.calibration import (Calibration, IndividualCalibration, PressureCalibration, UniformCalibration,
                                    apply_profile, cell_size_mm, configured_mat_size, profile_size_mm)
from processing.frames import orient_grid, process_frame
from processing.hotspots import HotspotTracker
from processing.indices import IndexMonitor
from processing.modes import LiveMode
from processing.motion import MotionAnalyzer
from processing.occupancy import OccupancyDetector
from processing.posture import PostureTracker, classify_posture, risk_from
from processing.signals import Context, read_signal
from processing.statistics import contact_mask
from processing.temporal import TemporalAnalysis

STALE_AFTER_S = config.STALE_AFTER_S
INDEX_UPDATE_INTERVAL_S = config.INDEX_UPDATE_INTERVAL_S
SATURATION_LIMIT = config.VALUE_MAX_DEFAULT - config.HEALTH_SATURATION_MARGIN
NO_ORIENTATION = {"rotation": 0, "mirror_h": False, "mirror_v": False}

# processing/* reads the grid size from config.TOTAL_ROWS/COLS, so each mat runs with its own size set.
# ponytail: one global lock, mats are processed one at a time; fine for a ward of mats at ~10 fps.
_grid_lock = threading.RLock()


@contextmanager
def grid_shape(rows, cols):
    with _grid_lock:
        saved = config.TOTAL_ROWS, config.TOTAL_COLS
        config.TOTAL_ROWS, config.TOTAL_COLS = rows, cols
        try:
            yield
        finally:
            config.TOTAL_ROWS, config.TOTAL_COLS = saved


def _saturated_cells(raw):
    """Cells at the sensor's limit (app range): load and peak read low there"""
    try:
        from processing.statistics import saturated_cells  # added by the desktop package
        return int(saturated_cells(raw, config.VALUE_MAX_DEFAULT))
    except ImportError:
        return int(np.sum(np.isfinite(raw) & (raw >= SATURATION_LIMIT)))


class MatEngine:
    """Feed 0-1000 grids (as built, not oriented); snapshot() is the JSON-ready state of the mat"""

    def __init__(self, chip_id, rows, cols, value_max=config.VALUE_MAX_DEFAULT, profile=None, size_mm=None):
        self.chip_id = chip_id
        self.shape = (rows, cols)          # as built (the source's shape)
        self.value_max = value_max         # raw full scale, informational (grids arrive scaled)
        self.preset_size_mm = size_mm
        self.status = None                 # "online" / "offline" from the MQTT status topic, None = unknown
        self.clock = time.time             # demo mats replace it with their own (faster) clock
        self.profile_error = None
        self._lock = threading.RLock()
        try:
            self.set_profile(profile)
        except ValueError as error:        # like the desktop: a profile for another grid is ignored
            self.profile_error = str(error)
            self.set_profile(None)

    # ---- profile (tare, pressure calibration, orientation, mat size)

    def set_profile(self, profile):
        """Apply a profile dict (as saved by processing.calibration.save_profile), or None for a clean mat.
        All-or-nothing: raises ValueError and changes nothing when it does not fit this mat."""
        rows, cols = self.shape
        orientation = dict(NO_ORIENTATION)
        if profile is not None:
            try:
                orientation = {"rotation": int(profile["orientation"]["rotation"]),
                               "mirror_h": bool(profile["orientation"].get("mirror_h")),
                               "mirror_v": bool(profile["orientation"].get("mirror_v"))}
            except (KeyError, TypeError, ValueError, AttributeError) as error:
                raise ValueError(f"Profile has no valid orientation: {error}") from error
            if orientation["rotation"] not in (0, 90, 180, 270):
                raise ValueError("Profile rotation must be 0, 90, 180 or 270")
        if (orientation["rotation"] // 90) % 2:
            rows, cols = cols, rows
        if profile is not None and profile.get("grid_shape") != [rows, cols]:
            raise ValueError(f"Profile is for a {profile.get('grid_shape')} grid, this mat is {[rows, cols]}")
        with grid_shape(rows, cols):
            calibration, pressure_calibration = Calibration(), PressureCalibration()
            try:  # the desktop's _reset_calibration: the startup curve if it fits this grid
                pressure_calibration.individual = IndividualCalibration.default()
            except ValueError:
                pressure_calibration.individual = IndividualCalibration()
            pressure_calibration.uniform = UniformCalibration()
            if profile is not None:
                apply_profile(profile, calibration, pressure_calibration)
            trackers = (TemporalAnalysis(), HotspotTracker(), MotionAnalyzer(), OccupancyDetector(), IndexMonitor())
        size = profile_size_mm(profile) if profile else None
        size = size or self.preset_size_mm or configured_mat_size()
        cell = cell_size_mm(size, rows, cols, orientation["rotation"])
        try:
            version = int(profile.get("version") or 0) if profile else 0
        except (TypeError, ValueError) as error:
            raise ValueError("Profile version must be a whole number") from error
        with self._lock:
            self.oriented_shape = (rows, cols)
            self.orientation = orientation
            self.calibration, self.pressure_calibration = calibration, pressure_calibration
            self.temporal, self.hotspots, self.motion, self.occupancy, self.indices = trackers
            self.cell_area_m2 = None if cell is None else cell[0] * cell[1] / 1_000_000
            self.contact_threshold_kpa = config.CONTACT_THRESHOLD_KPA
            self.mode = LiveMode()
            self.posture = PostureTracker()
            self.profile = profile
            self.profile_version = version
            self.frame = None
            self.last_t = None
            self._last_index_t = None
            self.saturated = 0

    # ---- per frame

    def feed(self, grid, t):
        """One frame: values 0-1000 at the mat's own (as built) shape, t = its timestamp in seconds"""
        with self._lock, grid_shape(*self.oriented_shape):
            grid = orient_grid(np.asarray(grid, dtype=float), **self.orientation)
            if self.last_t is not None and t <= self.last_t:  # time went back (a replay loop): start over
                self.set_profile(self.profile)
            frame = process_frame(grid, self.mode, self.calibration, self.pressure_calibration)
            pressure = frame["pressure"]
            self.temporal.update(pressure, t)
            self.hotspots.update(pressure, t, self.temporal, self.cell_area_m2)
            events = self.motion.update(pressure, t, self.contact_threshold_kpa, self.cell_area_m2,
                                        self.hotspots.active, self.temporal)
            occupied = self.occupancy.update(pressure, t, self.contact_threshold_kpa)
            if self._last_index_t is None or t - self._last_index_t >= INDEX_UPDATE_INTERVAL_S:
                self._last_index_t = t
                self.indices.update(Context(pressure, t, self.contact_threshold_kpa, self.temporal,
                                            self.hotspots, self.motion, None), t, occupied)
            repositioned = any(kind == "reposition_detected" for kind, _ in events)
            self.posture.update(classify_posture(pressure, occupied, self.contact_threshold_kpa), t, repositioned)
            self.saturated = _saturated_cells(frame["raw"])
            self.frame, self.last_t = frame, t

    # ---- state

    def online(self, t):
        return self.last_t is not None and t - self.last_t <= STALE_AFTER_S and self.status != "offline"

    def snapshot(self, t=None):
        """JSON-ready state: the web dashboard's snapshot plus posture, risk, saturation and online"""
        with self._lock:
            t = self.clock() if t is None else t
            online = self.online(t)
            occupied = self.occupancy.occupied if online else None
            summary = [self.indices.states[d["name"]] for d in self.indices.definitions if d["layer"] == "summary"]
            snap = {"unit": "relative", "scale_max": float(config.VALUE_MAX_DEFAULT), "grid": None,
                    "occupied": occupied, "hotspots": [], "indices": [], "saturated_cells": self.saturated,
                    "posture": (self.posture.posture or "none") if online else "none",
                    "time_in_position_s": self.posture.time_in_position(t) if online else None,
                    "risk": risk_from(summary, occupied, online), "since_relief_s": None, "online": online, "peak_kpa": None,
                    "shape": list(self.oriented_shape), "profile_version": self.profile_version}
            if self.frame is None:
                return snap
            pressure = self.frame["pressure"]
            if pressure is not None:
                grid, snap["unit"], snap["scale_max"] = pressure, "kPa", float(config.PRESSURE_DISPLAY_MAX_KPA)
            else:  # not calibrated: the tared signal, and say so
                grid = self.frame["baseline_subtracted"]
            # same shape as gui/web.build_snapshot (the server must not import gui/)
            peak = np.nanmax(pressure) if pressure is not None and np.isfinite(pressure).any() else None
            snap["peak_kpa"] = None if peak is None else round(float(peak), 1)  # relative signal: no kPa
            snap["grid"] = [[round(float(v), 2) if np.isfinite(v) else None for v in row] for row in grid]
            snap["hotspots"] = [{"id": tr["id"], "peak_kpa": round(tr["peak_kpa"], 1),
                                 "cells": sorted([int(r), int(c)] for r, c in tr["cells"]),
                                 "active_s": round(tr["active_s"], 1), "persistent": bool(tr["persistent"])}
                                for tr in self.hotspots.active]
            for d in self.indices.definitions:
                value = self.indices.compared(d["name"])
                snap["indices"].append({"name": d["name"], "layer": d["layer"],
                                        "value": None if value is None else round(value, 3),
                                        "threshold": d["threshold"], "near": d["near_fraction"] * d["threshold"],
                                        "state": self.indices.states[d["name"]]})
            if occupied and pressure is not None:
                context = Context(pressure, self.last_t, self.contact_threshold_kpa, self.temporal,
                                  self.hotspots, self.motion, None)
                since = read_signal("since_relief", context)[contact_mask(pressure, self.contact_threshold_kpa)]
                since = since[np.isfinite(since)]
                snap["since_relief_s"] = round(float(since.max()), 1) if since.size else None
            return snap
