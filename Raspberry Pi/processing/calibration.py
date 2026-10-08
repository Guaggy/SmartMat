"""Display tare and per-sensor pressure calibration."""

import copy
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np

import config
from config import VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT

class Calibration:
    """Display range, plus an optional baseline grid subtracted from future frames"""

    def __init__(self):
        self.auto = False
        self.vmin = VALUE_MIN_DEFAULT
        self.vmax = VALUE_MAX_DEFAULT
        self.baseline = None

    def apply_baseline(self, grid):
        """Subtract the captured baseline (if any), clamped back into range."""
        if self.baseline is None:
            return grid
        return np.clip(grid - self.baseline, VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT)

    def capture_baseline(self, grid):
        """Calibrate button: remember this (pre-baseline) reading as the new zero point."""
        self.baseline = grid.copy()

    def update(self, grid):
        """Call once per new (already baseline-corrected) frame"""
        if not self.auto:
            return
        lowest = float(grid.min())
        highest = float(grid.max())
        if lowest < highest:
            self.vmin, self.vmax = lowest, highest

    def toggle_auto(self):
        self.auto = not self.auto

    def reset(self):
        """Reset button. Back to the default fixed range, no baseline"""
        self.auto = False
        self.vmin = VALUE_MIN_DEFAULT
        self.vmax = VALUE_MAX_DEFAULT
        self.baseline = None


INDIVIDUAL_FORMAT = "smartmat_pressure_calibration_v1"
UNIFORM_FORMAT = "smartmat_uniform_pressure_calibration_v1"
MIN_FINITE_FRACTION = 0.9  # share of cells that must read a value to take a whole-grid mean


def _convert_curve(values, curve):
    """kPa for `values` under one {offset, model, points} curve (shared by both profiles)"""
    offset = curve["offset"]
    points = [(raw, pressure) for raw, pressure in curve["points"] if raw > offset]
    if not points or not any(pressure > 0 for _, pressure in points):
        return np.full_like(values, np.nan, dtype=float)
    if curve["model"] == "linear":
        inputs = np.asarray([raw - offset for raw, _ in points])
        outputs = np.asarray([pressure for _, pressure in points])
        slope = float(np.dot(inputs, outputs) / np.dot(inputs, inputs))
        return np.maximum(0.0, (values - offset) * slope)
    knots = [(offset, 0.0)] + points
    return np.interp(values, [raw for raw, _ in knots],
                     [pressure for _, pressure in knots])


def _curve_calibrated(curve):
    return any(raw > curve["offset"] and pressure > 0 for raw, pressure in curve["points"])


def _date_text(timestamp):
    return None if timestamp is None else datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")


def _parse_date(text):
    try:
        return None if not text else datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError):
        return None


def _check_grid(grid):
    values = np.asarray(grid, dtype=float)
    if values.shape != (config.TOTAL_ROWS, config.TOTAL_COLS) or not np.all(np.isfinite(values)):
        raise ValueError("Current grid must contain a finite value for every sensor")
    return values


def _grid_mean(grid):
    """One representative value for the whole mat (uniform profile has a single curve)"""
    values = np.asarray(grid, dtype=float)
    if values.shape != (config.TOTAL_ROWS, config.TOTAL_COLS):
        raise ValueError("Current grid size does not match configuration")
    finite = values[np.isfinite(values)]
    if finite.size < MIN_FINITE_FRACTION * values.size:
        raise ValueError("Too many sensors have no valid reading to take a whole-grid value")
    return float(finite.mean())


class IndividualCalibration:
    """Convert received sensor values to kPa using each cell's saved curve."""

    def __init__(self):
        self.cells = {}
        self.path = None
        self.modified_at = None
        self._default_cells = set()

    def _touch(self):
        self.modified_at = time.time()

    @classmethod
    def default(cls):
        """Load the configured startup calibration or create a usable linear default."""
        calibration = cls()
        configured_path = getattr(config, "DEFAULT_PRESSURE_CALIBRATION_FILE", None)
        if configured_path:
            path = Path(configured_path)
            if not path.is_absolute():
                path = Path(config.__file__).resolve().parent / path
            if path.exists():
                calibration.load(path)
                return calibration

        raw_max = float(getattr(config, "DEFAULT_PRESSURE_CALIBRATION_RAW_MAX",
                                VALUE_MAX_DEFAULT))
        pressure_max = float(getattr(config, "DEFAULT_PRESSURE_CALIBRATION_KPA",
                                     getattr(config, "PRESSURE_DISPLAY_MAX_KPA", 50.0)))
        if raw_max <= VALUE_MIN_DEFAULT or pressure_max <= 0:
            raise ValueError("Default pressure calibration values must be positive")
        calibration.set_all_offsets(VALUE_MIN_DEFAULT)
        calibration.add_grid_point(
            np.full((config.TOTAL_ROWS, config.TOTAL_COLS), raw_max, dtype=float), pressure_max)
        calibration._default_cells = {
            (row, col) for row in range(config.TOTAL_ROWS) for col in range(config.TOTAL_COLS)
        }
        calibration.modified_at = None  # the built-in default was never calibrated by anyone
        return calibration

    @property
    def calibrated_count(self):
        return sum(self.is_calibrated(row, col) for row, col in self.cells)

    @property
    def is_complete(self):
        return self.calibrated_count == config.TOTAL_ROWS * config.TOTAL_COLS

    def _cell(self, row, col):
        if not (0 <= row < config.TOTAL_ROWS and 0 <= col < config.TOTAL_COLS):
            raise ValueError("Sensor cell is outside the configured grid")
        return self.cells.setdefault((row, col), {"offset": 0.0, "model": "linear", "points": []})

    def get_cell(self, row, col):
        cell = self._cell(row, col)
        return {"offset": cell["offset"], "model": cell["model"],
                "points": [point[:] for point in cell["points"]]}

    def set_offset(self, row, col, raw):
        raw = float(raw)
        if not np.isfinite(raw):
            raise ValueError("Offset must be finite")
        self._cell(row, col)["offset"] = raw
        self._touch()

    def set_all_offsets(self, raw):
        for row in range(config.TOTAL_ROWS):
            for col in range(config.TOTAL_COLS):
                self.set_offset(row, col, raw)

    def capture_offsets(self, grid):
        values = np.asarray(grid, dtype=float)
        if values.shape != (config.TOTAL_ROWS, config.TOTAL_COLS) or not np.all(np.isfinite(values)):
            raise ValueError("Current grid must contain a finite value for every sensor")
        for row in range(config.TOTAL_ROWS):
            for col in range(config.TOTAL_COLS):
                self.set_offset(row, col, values[row, col])

    def add_point(self, row, col, raw, pressure_kpa):
        raw = float(raw)
        pressure_kpa = float(pressure_kpa)
        if not np.isfinite(raw) or not np.isfinite(pressure_kpa) or pressure_kpa < 0:
            raise ValueError("Calibration values must be finite and pressure nonnegative")
        cell = self._cell(row, col)
        if (row, col) in self._default_cells:
            cell["points"] = []
            self._default_cells.remove((row, col))
        cell["points"] = [point for point in cell["points"] if point[0] != raw]
        cell["points"].append([raw, pressure_kpa])
        cell["points"].sort(key=lambda point: point[0])
        self._touch()

    def add_grid_point(self, grid, pressure_kpa):
        values = np.asarray(grid, dtype=float)
        if values.shape != (config.TOTAL_ROWS, config.TOTAL_COLS) or not np.all(np.isfinite(values)):
            raise ValueError("Current grid must contain a finite value for every sensor")
        for row in range(config.TOTAL_ROWS):
            for col in range(config.TOTAL_COLS):
                self.add_point(row, col, values[row, col], pressure_kpa)

    def remove_point(self, row, col, index):
        self._cell(row, col)["points"].pop(index)
        self._touch()

    def set_model(self, row, col, model):
        if model not in ("linear", "piecewise"):
            raise ValueError("Unknown calibration model")
        self._cell(row, col)["model"] = model
        self._touch()

    def set_model_all(self, model):
        for row in range(config.TOTAL_ROWS):
            for col in range(config.TOTAL_COLS):
                self.set_model(row, col, model)

    def copy_cell_to_all(self, row, col):
        source = self.get_cell(row, col)
        if not self.is_calibrated(row, col):
            raise ValueError("Calibrate the selected cell first")
        for target_row in range(config.TOTAL_ROWS):
            for target_col in range(config.TOTAL_COLS):
                self.cells[(target_row, target_col)] = {
                    "offset": source["offset"], "model": source["model"],
                    "points": [point[:] for point in source["points"]],
                }
        self._default_cells.clear()
        self._touch()

    def is_calibrated(self, row, col):
        cell = self.cells.get((row, col))
        return cell is not None and _curve_calibrated(cell)

    def _convert_cell(self, values, cell):
        return _convert_curve(values, cell)

    def convert_cell(self, row, col, raw):
        return float(self._convert_cell(np.asarray([raw], dtype=float), self._cell(row, col))[0])

    def apply(self, grid):
        if grid.shape != (config.TOTAL_ROWS, config.TOTAL_COLS):
            raise ValueError("Calibration grid size does not match configuration")
        pressure = np.full(grid.shape, np.nan, dtype=float)
        for (row, col), cell in self.cells.items():
            pressure[row, col] = self._convert_cell(np.asarray([grid[row, col]]), cell)[0]
        return pressure

    def to_dict(self):
        return {
            "format": INDIVIDUAL_FORMAT,
            "calibrated_at": _date_text(self.modified_at),
            "units": "kPa",
            "grid_shape": [config.TOTAL_ROWS, config.TOTAL_COLS],
            "cells": [dict(row=row, col=col, **self.get_cell(row, col))
                      for row, col in sorted(self.cells)],
        }

    def load_dict(self, data):
        if data.get("format") != INDIVIDUAL_FORMAT:
            raise ValueError("Unsupported pressure calibration format")
        if data.get("grid_shape") != [config.TOTAL_ROWS, config.TOTAL_COLS] or data.get("units") != "kPa":
            raise ValueError("Calibration grid or units do not match configuration")
        loaded = IndividualCalibration()
        for item in data["cells"]:
            row, col = int(item["row"]), int(item["col"])
            loaded.set_offset(row, col, item["offset"])
            loaded.set_model(row, col, item["model"])
            for raw, pressure in item["points"]:
                loaded.add_point(row, col, raw, pressure)
        self.cells = loaded.cells
        self.modified_at = _parse_date(data.get("calibrated_at"))
        self._default_cells.clear()

    def save(self, path):
        path = Path(path)
        with path.open("w") as file:
            json.dump(self.to_dict(), file, indent=2)
        self.path = path

    def load(self, path):
        path = Path(path)
        with path.open() as file:
            self.load_dict(json.load(file))
        self.path = path


class UniformCalibration:
    """One shared {offset, model, points} curve applied to every cell at once."""

    def __init__(self):
        self.curve = {"offset": 0.0, "model": "linear", "points": []}
        self.path = None
        self.modified_at = None

    def _touch(self):
        self.modified_at = time.time()

    def get_curve(self):
        return {"offset": self.curve["offset"], "model": self.curve["model"],
                "points": [point[:] for point in self.curve["points"]]}

    @property
    def exists(self):
        return _curve_calibrated(self.curve)

    @property
    def calibrated_count(self):
        return config.TOTAL_ROWS * config.TOTAL_COLS if self.exists else 0

    @property
    def is_complete(self):
        return self.exists

    def is_calibrated(self, row=None, col=None):
        return self.exists

    def set_offset(self, raw):
        raw = float(raw)
        if not np.isfinite(raw):
            raise ValueError("Offset must be finite")
        self.curve["offset"] = raw
        self._touch()

    def capture_offset(self, grid):
        self.set_offset(_grid_mean(grid))

    def add_point(self, raw, pressure_kpa):
        raw = float(raw)
        pressure_kpa = float(pressure_kpa)
        if not np.isfinite(raw) or not np.isfinite(pressure_kpa) or pressure_kpa < 0:
            raise ValueError("Calibration values must be finite and pressure nonnegative")
        points = [point for point in self.curve["points"] if point[0] != raw]
        points.append([raw, pressure_kpa])
        self.curve["points"] = sorted(points, key=lambda point: point[0])
        self._touch()

    def add_grid_point(self, grid, pressure_kpa):
        self.add_point(_grid_mean(grid), pressure_kpa)

    def remove_point(self, index):
        self.curve["points"].pop(index)
        self._touch()

    def set_model(self, model):
        if model not in ("linear", "piecewise"):
            raise ValueError("Unknown calibration model")
        self.curve["model"] = model
        self._touch()

    def convert(self, raw):
        return float(_convert_curve(np.asarray([raw], dtype=float), self.curve)[0])

    def convert_cell(self, row, col, raw):
        return self.convert(raw)

    def apply(self, grid):
        grid = np.asarray(grid, dtype=float)
        if grid.shape != (config.TOTAL_ROWS, config.TOTAL_COLS):
            raise ValueError("Calibration grid size does not match configuration")
        return _convert_curve(grid, self.curve)

    def to_dict(self):
        return {"format": UNIFORM_FORMAT, "calibrated_at": _date_text(self.modified_at),
                "units": "kPa", "grid_shape": [config.TOTAL_ROWS, config.TOTAL_COLS], **self.get_curve()}

    def load_dict(self, data):
        if data.get("format") != UNIFORM_FORMAT:
            raise ValueError("Unsupported pressure calibration format")
        if data.get("grid_shape") != [config.TOTAL_ROWS, config.TOTAL_COLS] or data.get("units") != "kPa":
            raise ValueError("Calibration grid or units do not match configuration")
        loaded = UniformCalibration()
        loaded.set_offset(data["offset"])
        loaded.set_model(data["model"])
        for raw, pressure in data["points"]:
            loaded.add_point(raw, pressure)
        self.curve = loaded.curve
        self.modified_at = _parse_date(data.get("calibrated_at"))

    def save(self, path):
        path = Path(path)
        with path.open("w") as file:
            json.dump(self.to_dict(), file, indent=2)
        self.path = path

    def load(self, path):
        path = Path(path)
        with path.open() as file:
            self.load_dict(json.load(file))
        self.path = path


class PressureCalibration:
    """Holds the Individual and Uniform profiles and forwards to whichever is active.

    app.pressure_calibration stays one long-lived object, so everything that keeps a
    reference to it (windows, playback restore, event replay) is unaffected by switching.
    """

    PROFILES = ("individual", "uniform")

    def __init__(self):
        self.individual = IndividualCalibration()
        self.uniform = UniformCalibration()
        self.active_name = "individual"

    @classmethod
    def default(cls):
        calibration = cls()
        calibration.individual = IndividualCalibration.default()
        return calibration

    @property
    def active(self):
        return self.individual if self.active_name == "individual" else self.uniform

    def use(self, name):
        if name not in self.PROFILES:
            raise ValueError("Unknown calibration profile")
        self.active_name = name

    def __getattr__(self, name):
        # only reached for names not defined above; forward to the active profile
        if name in ("individual", "uniform", "active_name"):
            raise AttributeError(name)
        return getattr(self.active, name)

    def capture_tare(self, grid):
        """Set both profiles' zero point from a tare grid; all-or-nothing.

        Refuses if it would leave any previously calibrated cell uncalibrated (the new
        offset would sit above its calibration points), e.g. a tare taken under load.
        """
        grid = _check_grid(grid)
        for label, profile, capture in (
                ("individual", self.individual, lambda p: p.capture_offsets(grid)),
                ("uniform", self.uniform, lambda p: p.capture_offset(grid))):
            trial = copy.deepcopy(profile)
            capture(trial)
            lost = profile.calibrated_count - trial.calibrated_count
            if lost > 0:
                raise ValueError(f"Tare would uncalibrate {lost} cells in the {label} "
                                 "calibration - tare with the mat unloaded")
        self.individual.capture_offsets(grid)
        self.uniform.capture_offset(grid)

    def to_dict(self):
        return self.active.to_dict()

    def load_dict(self, data):
        """Load either profile's dict into that profile and make it active"""
        name = {INDIVIDUAL_FORMAT: "individual", UNIFORM_FORMAT: "uniform"}.get(data.get("format"))
        if name is None:
            raise ValueError("Unsupported pressure calibration format")
        getattr(self, name).load_dict(data)
        self.active_name = name

    def save(self, path):
        self.active.save(path)

    def load(self, path):
        path = Path(path)
        with path.open() as file:
            self.load_dict(json.load(file))
        self.active.path = path
