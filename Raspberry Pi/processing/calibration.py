"""Display tare and per-sensor pressure calibration."""

import copy
import json
import re
import time
from datetime import datetime
from pathlib import Path

import numpy as np

import config
import paths
from config import VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT
from processing.roi import cells_mask, mask_to_cells

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
        self._revision = 0       # bumped by every change, so the compiled form below is rebuilt only when needed
        self._compiled = None    # (key, linear mask, offsets, slopes, other cells), see apply()

    def _touch(self):
        self.modified_at = time.time()
        self._revision += 1

    @classmethod
    def default(cls):
        """Load the configured startup calibration or create a usable linear default."""
        calibration = cls()
        configured_path = getattr(config, "DEFAULT_PRESSURE_CALIBRATION_FILE", None)
        if configured_path:
            path = Path(configured_path)
            if not path.is_absolute():
                path = paths.APP_DIR / path
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
    def uses_default_curve(self):
        """True while any cell still has the built-in linear fallback (nobody calibrated it)"""
        return bool(self._default_cells)

    @property
    def calibrated_count(self):
        _key, linear, _offsets, _slopes, others = self._compile()   # cached: asked once per frame
        return int(linear.sum()) + len(others)

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

    def _compile(self):
        """Per-cell curves as arrays, so a frame is converted in a few array operations instead of one Python call per cell.
        Linear cells (the usual case) become an offset and a slope; other models stay one interp each. Cells without a usable
        curve stay NaN. Rebuilt only when a cell changed (_revision) or the cell table was replaced."""
        key = (self._revision, id(self.cells), len(self.cells))
        if self._compiled is not None and self._compiled[0] == key:
            return self._compiled
        shape = (config.TOTAL_ROWS, config.TOTAL_COLS)
        linear = np.zeros(shape, dtype=bool)
        offsets = np.zeros(shape)
        slopes = np.zeros(shape)
        others = []
        for (row, col), cell in self.cells.items():
            points = [(raw, pressure) for raw, pressure in cell["points"] if raw > cell["offset"]]
            if not points or not any(pressure > 0 for _, pressure in points):
                continue
            if cell["model"] == "linear":
                inputs = np.asarray([raw - cell["offset"] for raw, _ in points])
                outputs = np.asarray([pressure for _, pressure in points])
                linear[row, col] = True
                offsets[row, col] = cell["offset"]
                slopes[row, col] = float(np.dot(inputs, outputs) / np.dot(inputs, inputs))
            else:
                others.append((row, col, cell))
        self._compiled = (key, linear, offsets, slopes, others)
        return self._compiled

    def calibrated_mask(self):
        """is_calibrated(row, col) for the whole grid at once (from the compiled form, so cached between changes)"""
        _key, linear, _offsets, _slopes, others = self._compile()
        mask = linear.copy()
        for row, col, _cell in others:
            mask[row, col] = True
        return mask

    def apply(self, grid):
        if grid.shape != (config.TOTAL_ROWS, config.TOTAL_COLS):
            raise ValueError("Calibration grid size does not match configuration")
        _key, linear, offsets, slopes, others = self._compile()
        pressure = np.full(grid.shape, np.nan, dtype=float)
        with np.errstate(invalid="ignore"):
            np.maximum(0.0, (grid - offsets) * slopes, out=pressure, where=linear)
        for row, col, cell in others:
            pressure[row, col] = self._convert_cell(np.asarray([grid[row, col]]), cell)[0]
        return pressure

    def to_dict(self):
        data = {
            "format": INDIVIDUAL_FORMAT,
            "calibrated_at": _date_text(self.modified_at),
            "units": "kPa",
            "grid_shape": [config.TOTAL_ROWS, config.TOTAL_COLS],
            "cells": [dict(row=row, col=col, **self.get_cell(row, col))
                      for row, col in sorted(self.cells)],
        }
        if self._default_cells:  # so a saved profile still knows it was never calibrated
            data["default_cells"] = [list(cell) for cell in sorted(self._default_cells)]
        return data

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
        self._revision += 1
        self.modified_at = _parse_date(data.get("calibrated_at"))
        self._default_cells = {(int(row), int(col)) for row, col in data.get("default_cells", [])}

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

    def calibrated_mask(self):
        return np.full((config.TOTAL_ROWS, config.TOTAL_COLS), self.exists)

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
    def is_default_curve(self):
        """The active profile is still the built-in linear fallback, not a calibration"""
        return self.active_name == "individual" and self.individual.uses_default_curve

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


# ---- mat size: physical sensing size (width x height, mm) -> per-cell size of the oriented grid

def _valid_size(size):
    """(width, height) as floats when both are finite and positive, None for None; else ValueError"""
    if size is None:
        return None
    width, height = (float(value) for value in size)
    if not (np.isfinite(width) and np.isfinite(height) and width > 0 and height > 0):
        raise ValueError("Mat width and height must be positive numbers")
    return width, height


def parse_mat_size(text):
    """'600 x 500' (mm, width x height) -> (600.0, 500.0); empty text -> None (not set)"""
    text = text.strip()
    if not text:
        return None
    parts = re.split(r"\s*[x*,;]\s*|\s+", text.lower().replace("mm", ""))
    if len(parts) != 2:
        raise ValueError("Enter width and height in mm, for example 600 x 500")
    return _valid_size(parts)


def configured_mat_size():
    """The config.py default (MAT_WIDTH_MM x MAT_HEIGHT_MM), or None"""
    try:
        return _valid_size((config.MAT_WIDTH_MM, config.MAT_HEIGHT_MM))
    except (AttributeError, TypeError, ValueError):
        return None


def cell_size_mm(size_mm, rows, cols, rotation=0):
    """(cell_width, cell_height) in mm of the oriented rows x cols grid, or None when not known.

    size_mm is the mat as built (width along its columns). A 90/270 rotation makes the oriented
    columns run along the built height, so the axes swap; mirror and 180 change nothing. Without
    size_mm the older per-cell CELL_WIDTH_MM x CELL_HEIGHT_MM from config.py is the fallback."""
    swap = (rotation // 90) % 2 == 1
    if size_mm is not None:
        width, height = size_mm
        return (height / cols, width / rows) if swap else (width / cols, height / rows)
    try:
        cell = _valid_size((config.CELL_WIDTH_MM, config.CELL_HEIGHT_MM))
    except (AttributeError, TypeError, ValueError):
        return None
    return None if cell is None else (cell[1], cell[0]) if swap else cell


# ---- per-mat profiles: one JSON per real mat with its tare, both calibrations and orientation

PROFILE_FORMAT = "smartmat_mat_profile_v1"
PROFILES_DIR = paths.APP_DIR / "profiles"


def profile_path(mat_id):
    return PROFILES_DIR / (re.sub(r"[^\w.-]", "_", str(mat_id)) + ".json")


def save_profile(mat_id, baseline, pressure_calibration, orientation, size_mm=None, roi=None):
    """Write the current (oriented) grid's state for this mat; size_mm = (width, height) sensing size,
    roi = boolean cell mask of the grid or None"""
    data = {"format": PROFILE_FORMAT, "mat_id": mat_id,
            "grid_shape": [config.TOTAL_ROWS, config.TOTAL_COLS], "orientation": orientation,
            "size_mm": None if size_mm is None else list(size_mm),
            "roi": None if roi is None else {"shape": list(roi.shape), "cells": mask_to_cells(roi)},
            "baseline": None if baseline is None else np.asarray(baseline).tolist(),
            "active": pressure_calibration.active_name,
            "individual": pressure_calibration.individual.to_dict(),
            "uniform": pressure_calibration.uniform.to_dict()}
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profile_path(mat_id).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_profile(mat_id):
    """The saved profile dict, or None when there is none (or it is unreadable / not a profile)"""
    try:
        data = json.loads(profile_path(mat_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("format") == PROFILE_FORMAT else None


def profile_size_mm(data):
    """(width, height) mm saved in a profile, or None (old profiles have none)"""
    try:
        return _valid_size(data.get("size_mm"))
    except (AttributeError, TypeError, ValueError):
        return None


def profile_roi(data):
    """The ROI mask saved in a profile if it was saved for the current grid shape, else None (also for old profiles)"""
    shape = (config.TOTAL_ROWS, config.TOTAL_COLS)
    try:
        saved = data["roi"]
        return cells_mask(shape, saved["cells"]) if tuple(saved["shape"]) == shape else None
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def apply_profile(data, calibration, pressure_calibration):
    """Put a profile's tare and calibrations back; all-or-nothing (raises ValueError, changes nothing)"""
    try:
        individual, uniform = IndividualCalibration(), UniformCalibration()
        individual.load_dict(data["individual"])
        uniform.load_dict(data["uniform"])
        baseline = None if data["baseline"] is None else np.asarray(data["baseline"], dtype=float)
        if baseline is not None and baseline.shape != (config.TOTAL_ROWS, config.TOTAL_COLS):
            raise ValueError("Profile tare does not match the grid")
        active = data["active"] if data.get("active") in PressureCalibration.PROFILES else "individual"
    except (KeyError, TypeError) as error:
        raise ValueError(f"Incomplete mat profile: {error}") from error
    pressure_calibration.individual, pressure_calibration.uniform = individual, uniform
    pressure_calibration.use(active)
    calibration.baseline = baseline
