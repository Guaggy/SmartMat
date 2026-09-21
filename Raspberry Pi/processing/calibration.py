"""Display tare and per-sensor pressure calibration."""

import json
from pathlib import Path

import numpy as np

import config
from config import TOTAL_ROWS, TOTAL_COLS, VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT

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


class PressureCalibration:
    """Convert received sensor values to kPa using each cell's saved curve."""

    def __init__(self):
        self.cells = {}
        self.path = None
        self._default_cells = set()

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
            np.full((TOTAL_ROWS, TOTAL_COLS), raw_max, dtype=float), pressure_max)
        calibration._default_cells = {
            (row, col) for row in range(TOTAL_ROWS) for col in range(TOTAL_COLS)
        }
        return calibration

    @property
    def calibrated_count(self):
        return sum(self.is_calibrated(row, col) for row, col in self.cells)

    @property
    def is_complete(self):
        return self.calibrated_count == TOTAL_ROWS * TOTAL_COLS

    def _cell(self, row, col):
        if not (0 <= row < TOTAL_ROWS and 0 <= col < TOTAL_COLS):
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

    def set_all_offsets(self, raw):
        for row in range(TOTAL_ROWS):
            for col in range(TOTAL_COLS):
                self.set_offset(row, col, raw)

    def capture_offsets(self, grid):
        values = np.asarray(grid, dtype=float)
        if values.shape != (TOTAL_ROWS, TOTAL_COLS) or not np.all(np.isfinite(values)):
            raise ValueError("Current grid must contain a finite value for every sensor")
        for row in range(TOTAL_ROWS):
            for col in range(TOTAL_COLS):
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

    def add_grid_point(self, grid, pressure_kpa):
        values = np.asarray(grid, dtype=float)
        if values.shape != (TOTAL_ROWS, TOTAL_COLS) or not np.all(np.isfinite(values)):
            raise ValueError("Current grid must contain a finite value for every sensor")
        for row in range(TOTAL_ROWS):
            for col in range(TOTAL_COLS):
                self.add_point(row, col, values[row, col], pressure_kpa)

    def remove_point(self, row, col, index):
        self._cell(row, col)["points"].pop(index)

    def set_model(self, row, col, model):
        if model not in ("linear", "piecewise"):
            raise ValueError("Unknown calibration model")
        self._cell(row, col)["model"] = model

    def set_model_all(self, model):
        for row in range(TOTAL_ROWS):
            for col in range(TOTAL_COLS):
                self.set_model(row, col, model)

    def copy_cell_to_all(self, row, col):
        source = self.get_cell(row, col)
        if not self.is_calibrated(row, col):
            raise ValueError("Calibrate the selected cell first")
        for target_row in range(TOTAL_ROWS):
            for target_col in range(TOTAL_COLS):
                self.cells[(target_row, target_col)] = {
                    "offset": source["offset"], "model": source["model"],
                    "points": [point[:] for point in source["points"]],
                }
        self._default_cells.clear()

    def is_calibrated(self, row, col):
        cell = self.cells.get((row, col))
        if cell is None:
            return False
        return any(raw > cell["offset"] and pressure > 0
                   for raw, pressure in cell["points"])

    def _convert_cell(self, values, cell):
        offset = cell["offset"]
        points = [(raw, pressure) for raw, pressure in cell["points"] if raw > offset]
        if not points or not any(pressure > 0 for _, pressure in points):
            return np.full_like(values, np.nan, dtype=float)
        if cell["model"] == "linear":
            inputs = np.asarray([raw - offset for raw, _ in points])
            outputs = np.asarray([pressure for _, pressure in points])
            slope = float(np.dot(inputs, outputs) / np.dot(inputs, inputs))
            return np.maximum(0.0, (values - offset) * slope)
        knots = [(offset, 0.0)] + points
        return np.interp(values, [raw for raw, _ in knots],
                         [pressure for _, pressure in knots])

    def convert_cell(self, row, col, raw):
        return float(self._convert_cell(np.asarray([raw], dtype=float), self._cell(row, col))[0])

    def apply(self, grid):
        if grid.shape != (TOTAL_ROWS, TOTAL_COLS):
            raise ValueError("Calibration grid size does not match configuration")
        pressure = np.full(grid.shape, np.nan, dtype=float)
        for (row, col), cell in self.cells.items():
            pressure[row, col] = self._convert_cell(np.asarray([grid[row, col]]), cell)[0]
        return pressure

    def to_dict(self):
        return {
            "format": "smartmat_pressure_calibration_v1",
            "units": "kPa",
            "grid_shape": [TOTAL_ROWS, TOTAL_COLS],
            "cells": [dict(row=row, col=col, **self.get_cell(row, col))
                      for row, col in sorted(self.cells)],
        }

    def load_dict(self, data):
        if data.get("format") != "smartmat_pressure_calibration_v1":
            raise ValueError("Unsupported pressure calibration format")
        if data.get("grid_shape") != [TOTAL_ROWS, TOTAL_COLS] or data.get("units") != "kPa":
            raise ValueError("Calibration grid or units do not match configuration")
        loaded = PressureCalibration()
        for item in data["cells"]:
            row, col = int(item["row"]), int(item["col"])
            loaded.set_offset(row, col, item["offset"])
            loaded.set_model(row, col, item["model"])
            for raw, pressure in item["points"]:
                loaded.add_point(row, col, raw, pressure)
        self.cells = loaded.cells
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
