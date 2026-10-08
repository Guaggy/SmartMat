# ROI Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an ROI a set of cells of any shape, and move selection (box, polygon, paint) and all ROI output (stats, mini grid, balance plot, history) into one new ROI window.

**Architecture:** `processing/roi.py` holds pure functions that build boolean cell masks and compute balance within a mask. Every ROI consumer switches from `(row0, row1, col0, col1)` to the mask in one pass, so there is a single representation. `gui/roi_window.py` edits a working selection through plain `press` / `drag` / `release` handlers (matplotlib events only translate pointer positions to cells) and hands it to `DesktopApp.set_roi()` on Apply.

**Tech Stack:** Python 3.13, numpy, Tkinter, matplotlib, `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-08-roi-window-design.md`

## Global Constraints

- An ROI is a boolean array of shape `(config.TOTAL_ROWS, config.TOTAL_COLS)`, or `None`. An all-False mask is never stored as the live ROI.
- No second ROI representation is kept. Nothing may unpack an ROI as four numbers after Task 2.
- Balance is relative to the region's own centre (`roi_centre`); a cell on the dividing row/column counts half to each side; right and up are positive; no load returns `None`.
- "Left/right" in the UI means as drawn on screen, and the window says so.
- Working selection changes nothing live until Apply. Apply of an empty selection clears the ROI. Apply resets ROI history and temporal time-since-relief tracking.
- Undo keeps 20 steps; a whole paint stroke is one step. Balance trail keeps 60 samples.
- Read the grid size only as `config.TOTAL_ROWS` / `config.TOTAL_COLS`.
- No new dependencies. No commits (unrelated uncommitted work is in the tree). No AI attribution.
- After every task, from `Raspberry Pi/`: `python -m unittest discover -s tests -v`. Baseline: 109 tests, OK. One file: `python -m unittest discover -s tests -p "test_roi.py" -v`.

## Where the spec did not match the code

1. **Nothing reads a recorded annotation's `"roi"` back.** The spec has `mask_from_legacy` convert old four-number annotations on load, but the app only ever writes that field. `mask_from_legacy` and `mask_from_cells` are therefore not built; `mask_to_cells` (the write side) is. Old recordings are unaffected because the field is never parsed.
2. **A contour between cell centres cuts corners**, so the heatmap outline would not follow cell edges. The outline is drawn from an 8x upsampled, one-cell-padded copy of the mask, which gives square corners and closes regions that touch the mat edge. Task 3.
3. **`TemporalAnalysis.roi()` is called three times per frame** for the history sample. Called once after this change. Task 3.

## Review Focus

1. Pointer positions outside the grid (dragging off the canvas, a corner clicked in the margin) must be ignored, not raise or wrap around to the other side via negative indices. Tests in Tasks 1 and 4.
2. A region with no load, or with only NaN cells, must give blank balance and centre values, not a division warning or a dot at the centre. Tests in Tasks 1 and 2.
3. Equal masks that are different array objects must not reset time-since-relief on every frame. Test in Task 2.
4. Editing without Apply must leave the live ROI, its history and the indices untouched. Test in Task 4.
5. A grid-size change with the ROI window open must not leave a working selection of the old shape. Test in Task 4.

## File Structure

| File | Change |
|---|---|
| `processing/roi.py` | new: mask builders, `mask_to_cells`, `roi_centre`, `roi_balance` |
| `processing/analysis.py` | `roi_statistics` takes a mask, adds centre offsets |
| `processing/temporal.py` | ROI tracking by mask |
| `processing/validation.py` | `compare_hotspot_roi` takes a mask |
| `processing/indices.py` | `"roi"` region reduces over the mask |
| `gui/desktop.py` | `set_roi`, cell outline, history sample, annotation payload, "ROI..." button; old two-click selection removed |
| `gui/roi_window.py` | new: selection canvas and ROI output |
| `gui/analysis_window.py` | ROI tab and buttons removed |
| `gui/annotation_window.py`, `gui/help_window.py` | wording |
| `tests/test_roi.py` | new |
| `tests/test_phase3.py`, `tests/test_phase4.py`, `tests/test_indices.py` | four-number ROIs become masks |
| `STATUS.md`, `notes.md`, `README.md` | docs |

---

### Task 1: Mask builders and balance

**Files:**
- Create: `processing/roi.py`
- Test: `tests/test_roi.py` (create)

**Interfaces:**
- Produces (cells are `(row, col)` tuples; `shape` is `(rows, cols)`):
  - `rectangle_mask(shape, first, second) -> bool ndarray`
  - `polygon_mask(shape, corners) -> bool ndarray`
  - `stroke_cells(first, second) -> list[(row, col)]`
  - `cells_mask(shape, cells) -> bool ndarray` (out-of-range cells ignored)
  - `mask_to_cells(mask) -> list[[row, col]]` (sorted, plain ints)
  - `roi_centre(mask) -> (row: float, col: float)`
  - `roi_balance(grid, mask) -> dict | None` with keys `left`, `right`, `upper`, `lower` (percent), `quadrants` (`upper_left`, `upper_right`, `lower_left`, `lower_right`), `x`, `y` (-1..1)

- [ ] **Step 1: Write the failing tests** - create `tests/test_roi.py`:

```python
"""ROI as a set of cells: mask builders, balance, consumers, and the ROI window."""

import unittest

import numpy as np

from processing.roi import (cells_mask, mask_to_cells, polygon_mask, rectangle_mask,
                            roi_balance, roi_centre, stroke_cells)

SHAPE = (16, 15)


def l_shape():
    """(0,0) (1,0) (2,0) (2,1) (2,2)"""
    return rectangle_mask(SHAPE, (0, 0), (2, 0)) | rectangle_mask(SHAPE, (2, 0), (2, 2))


class MaskTests(unittest.TestCase):
    def test_rectangle_in_any_corner_order_and_clipped_to_the_grid(self):
        mask = rectangle_mask(SHAPE, (3, 4), (1, 2))
        self.assertEqual(int(mask.sum()), 9)
        self.assertTrue(mask[1:4, 2:5].all())
        self.assertEqual(int(rectangle_mask(SHAPE, (-2, -2), (1, 20)).sum()), 30)
        self.assertEqual(int(rectangle_mask(SHAPE, (-5, -5), (-1, -1)).sum()), 0)

    def test_polygon_includes_cells_inside_or_on_the_outline(self):
        triangle = polygon_mask(SHAPE, [(0, 0), (0, 4), (4, 0)])
        expected = np.zeros(SHAPE, dtype=bool)
        for row in range(5):
            expected[row, :5 - row] = True
        np.testing.assert_array_equal(triangle, expected)

    def test_concave_polygon_and_too_few_corners(self):
        concave = polygon_mask(SHAPE, [(0, 0), (0, 4), (2, 4), (2, 2), (4, 2), (4, 0)])
        self.assertEqual(int(concave.sum()), 21)
        self.assertFalse(concave[3, 3])
        self.assertTrue(concave[4, 2])
        self.assertEqual(int(polygon_mask(SHAPE, [(0, 0), (3, 3)]).sum()), 0)

    def test_stroke_leaves_no_gaps(self):
        self.assertEqual(stroke_cells((0, 0), (3, 3)), [(0, 0), (1, 1), (2, 2), (3, 3)])
        self.assertEqual(stroke_cells((2, 2), (2, 2)), [(2, 2)])
        cells = stroke_cells((0, 0), (2, 5))
        self.assertEqual((cells[0], cells[-1], len(cells)), ((0, 0), (2, 5), 6))
        for (row, col), (next_row, next_col) in zip(cells, cells[1:]):
            self.assertLessEqual(max(abs(next_row - row), abs(next_col - col)), 1)

    def test_cells_outside_the_grid_are_ignored(self):
        mask = cells_mask(SHAPE, [(0, 0), (-1, 3), (16, 0), (2, 15), (1, 2)])
        self.assertEqual(mask_to_cells(mask), [[0, 0], [1, 2]])
        self.assertIsInstance(mask_to_cells(mask)[0][0], int)


class BalanceTests(unittest.TestCase):
    def setUp(self):
        self.mask = rectangle_mask(SHAPE, (0, 0), (1, 3))   # 2 rows x 4 cols, centre (0.5, 1.5)
        self.grid = np.zeros(SHAPE)

    def test_centre_is_the_mean_cell_position(self):
        self.assertEqual(roi_centre(self.mask), (0.5, 1.5))
        row, col = roi_centre(l_shape())
        self.assertAlmostEqual(row, 1.4)
        self.assertAlmostEqual(col, 0.6)

    def test_all_load_in_one_corner_and_an_even_region(self):
        self.grid[0, 0] = 10.0
        corner = roi_balance(self.grid, self.mask)
        self.assertEqual((corner["x"], corner["y"]), (-1.0, 1.0))   # screen left, top
        self.assertEqual(corner["quadrants"]["upper_left"], 100.0)
        self.grid[self.mask] = 5.0
        even = roi_balance(self.grid, self.mask)
        self.assertAlmostEqual(even["x"], 0.0)
        self.assertAlmostEqual(even["y"], 0.0)
        self.assertEqual(set(round(share) for share in even["quadrants"].values()), {25})

    def test_cell_on_the_dividing_line_counts_half_each_way(self):
        mask = rectangle_mask(SHAPE, (0, 0), (0, 2))   # centre column 1
        self.grid[0, 1] = 10.0
        result = roi_balance(self.grid, mask)
        self.assertEqual((result["left"], result["right"], result["x"]), (50.0, 50.0, 0.0))

    def test_no_load_or_only_unknown_cells_is_blank(self):
        self.assertIsNone(roi_balance(self.grid, self.mask))
        self.grid[self.mask] = np.nan
        self.assertIsNone(roi_balance(self.grid, self.mask))
        self.grid[0, 3] = 10.0   # unknown cells are skipped, load outside the mask is ignored
        self.grid[5, 5] = 99.0
        self.assertEqual(roi_balance(self.grid, self.mask)["x"], 1.0)

    def test_region_off_to_one_side_of_the_mat_can_still_be_balanced(self):
        mask = rectangle_mask(SHAPE, (0, 10), (1, 13))
        self.grid[mask] = 7.0
        self.assertAlmostEqual(roi_balance(self.grid, mask)["x"], 0.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, expect failure** - `ModuleNotFoundError: No module named 'processing.roi'`.

- [ ] **Step 3: Implement** - create `processing/roi.py`:

```python
"""A region of interest is a set of cells: a boolean mask the size of the mat."""

import numpy as np


def rectangle_mask(shape, first, second):
    """Cells in the box spanned by two (row, col) cells, in any order"""
    mask = np.zeros(shape, dtype=bool)
    row0, row1 = sorted((first[0], second[0]))
    col0, col1 = sorted((first[1], second[1]))
    mask[max(row0, 0):max(row1 + 1, 0), max(col0, 0):max(col1 + 1, 0)] = True
    return mask


def polygon_mask(shape, corners):
    """Cells whose centre is inside or on the outline of the polygon through (row, col) corners"""
    mask = np.zeros(shape, dtype=bool)
    if len(corners) < 3:
        return mask
    edges = list(zip(corners, list(corners[1:]) + [corners[0]]))
    for row in range(shape[0]):
        for col in range(shape[1]):
            inside = False
            for (row1, col1), (row2, col2) in edges:
                cross = (col2 - col1) * (row - row1) - (row2 - row1) * (col - col1)
                if (cross == 0 and min(row1, row2) <= row <= max(row1, row2)
                        and min(col1, col2) <= col <= max(col1, col2)):
                    inside = True  # on the outline
                    break
                if (row1 > row) != (row2 > row) and col < (col2 - col1) * (row - row1) / (row2 - row1) + col1:
                    inside = not inside
            mask[row, col] = inside
    return mask


def stroke_cells(first, second):
    """Cells on the straight line between two (row, col) cells, so a fast drag leaves no gaps"""
    steps = max(abs(second[0] - first[0]), abs(second[1] - first[1]))
    if steps == 0:
        return [tuple(first)]
    return [(round(first[0] + (second[0] - first[0]) * step / steps),
             round(first[1] + (second[1] - first[1]) * step / steps)) for step in range(steps + 1)]


def cells_mask(shape, cells):
    """Mask of the given (row, col) cells; cells outside the grid are ignored"""
    mask = np.zeros(shape, dtype=bool)
    for row, col in cells:
        if 0 <= row < shape[0] and 0 <= col < shape[1]:
            mask[row, col] = True
    return mask


def mask_to_cells(mask):
    """Sorted [[row, col], ...] of the selected cells, for JSON"""
    return [[int(row), int(col)] for row, col in np.argwhere(mask)]


def roi_centre(mask):
    """Mean (row, col) position of the selected cells"""
    rows, cols = np.nonzero(mask)
    return float(rows.mean()), float(cols.mean())


def _side(positions, centre):
    """Share of each row/column that lies before the centre: 1, 0, or 0.5 on the dividing line"""
    return np.where(positions < centre, 1.0, np.where(positions == centre, 0.5, 0.0))


def roi_balance(grid, mask):
    """How the load inside the region is shared around the region's own centre, None without load.

    x and y run -1..1; right and up (as drawn on screen) are positive.
    """
    values = np.where(mask & np.isfinite(grid), np.maximum(grid, 0), 0.0)
    total = float(values.sum())
    if total <= 0:
        return None
    centre_row, centre_col = roi_centre(mask)
    upper = _side(np.arange(grid.shape[0]), centre_row)[:, None]
    left = _side(np.arange(grid.shape[1]), centre_col)[None, :]

    def share(weights):
        return float((values * weights).sum() / total * 100)

    left_share, upper_share = share(left), share(upper)
    return {
        "left": left_share, "right": 100 - left_share,
        "upper": upper_share, "lower": 100 - upper_share,
        "quadrants": {"upper_left": share(upper * left), "upper_right": share(upper * (1 - left)),
                      "lower_left": share((1 - upper) * left), "lower_right": share((1 - upper) * (1 - left))},
        "x": (100 - 2 * left_share) / 100, "y": (2 * upper_share - 100) / 100,
    }
```

- [ ] **Step 4: Run everything** - `python -m unittest discover -s tests -v` -> 119 tests, OK.

---

### Task 2: Processing consumers take a mask

**Files:**
- Modify: `processing/analysis.py`, `processing/temporal.py`, `processing/validation.py`, `processing/indices.py`
- Modify tests: `tests/test_phase3.py`, `tests/test_phase4.py`, `tests/test_indices.py`
- Test: `tests/test_roi.py`

**Interfaces:**
- Consumes: `roi_centre`, `rectangle_mask` (Task 1).
- Produces:
  - `roi_statistics(grid, roi_mask, unit, threshold_kpa=0, cell_area_m2=None)` - same keys as before plus `centre_offset_x`, `centre_offset_y`.
  - `TemporalAnalysis.roi(mask)` - same keys as before; `TemporalAnalysis._roi_mask`.
  - `compare_hotspot_roi(roi_mask, tracks)` - same keys as before.
  - `Context.roi` is a mask or `None`.

- [ ] **Step 1: Write the failing tests** - add to `tests/test_roi.py` (imports: `import math`, `from processing.analysis import roi_statistics`, `from processing.temporal import TemporalAnalysis`, `from processing.validation import compare_hotspot_roi`, `from processing.hotspots import HotspotTracker`, `from processing.motion import MotionAnalyzer`, `from processing.indices import evaluate_indices, validate_indices`, `from processing.signals import Context`):

```python
class ConsumerTests(unittest.TestCase):
    def test_statistics_use_exactly_the_selected_cells(self):
        pressure = np.zeros(SHAPE)
        pressure[0, 0], pressure[2, 2], pressure[1, 1] = 10.0, 30.0, 99.0   # (1,1) is outside the L
        stats = roi_statistics(pressure, l_shape(), "kPa", 5, 0.0001)
        self.assertEqual((stats["sensors"], stats["peak"], stats["mean"]), (5, 30.0, 8.0))
        self.assertEqual(stats["contact_cells"], 2)
        self.assertAlmostEqual(stats["force_n"], 4.0)
        self.assertAlmostEqual(stats["center_x"], 1.5)
        self.assertAlmostEqual(stats["center_y"], 1.5)
        self.assertAlmostEqual(stats["centre_offset_x"], 0.9)
        self.assertAlmostEqual(stats["centre_offset_y"], 0.1)

    def test_statistics_without_load_or_data_are_blank(self):
        stats = roi_statistics(np.zeros(SHAPE), l_shape(), "kPa", 5)
        self.assertIsNone(stats["center_x"])
        self.assertIsNone(stats["centre_offset_x"])
        blank = roi_statistics(np.full(SHAPE, np.nan), l_shape(), "kPa", 5)
        self.assertEqual((blank["sensors"], blank["mean"]), (5, None))

    def test_temporal_roi_uses_the_mask_and_tracks_relief(self):
        analysis = TemporalAnalysis()
        analysis.max_gap_s = 30
        analysis.relief_min_duration_s = 0
        mask = l_shape()
        pressure = np.zeros(SHAPE)
        pressure[mask] = 30.0
        pressure[1, 1] = 90.0
        analysis.roi(mask)
        for timestamp in (0, 10, 20, 30):
            analysis.update(pressure, timestamp)
        result = analysis.roi(mask)
        self.assertAlmostEqual(result["mean_exposure"], float(analysis.exposure[mask].mean()))
        self.assertLess(result["max_exposure"], float(analysis.exposure[1, 1]))
        self.assertEqual(result["loaded_fraction"], 1.0)
        for timestamp in (40, 50, 60):
            analysis.update(np.zeros(SHAPE), timestamp)
        self.assertTrue(math.isfinite(analysis.roi(mask)["since_relief_s"]))

    def test_equal_mask_does_not_restart_relief_tracking(self):
        analysis = TemporalAnalysis()
        analysis.roi(l_shape())
        analysis._roi_last_relief = 5.0
        analysis.roi(l_shape())               # equal cells, different array object
        self.assertEqual(analysis._roi_last_relief, 5.0)
        analysis.roi(rectangle_mask(SHAPE, (0, 0), (1, 1)))
        self.assertIsNone(analysis._roi_last_relief)

    def test_hotspot_comparison_overlaps_cell_by_cell(self):
        track = {"id": 3, "cells": {(2, 2), (2, 1), (5, 5)}, "centroid": (2.0, 1.5),
                 "total_active_s": 12.0, "started_before_session": False}
        result = compare_hotspot_roi(l_shape(), [track])
        self.assertEqual((result["detected"], result["hotspot_id"]), (True, 3))
        self.assertAlmostEqual(result["overlap"], 0.4)
        self.assertAlmostEqual(result["centroid_distance_cells"], math.dist((1.4, 0.6), (2.0, 1.5)))

    def test_index_roi_region_reduces_over_the_mask(self):
        pressure = np.zeros(SHAPE)
        pressure[0, 0], pressure[1, 1] = 30.0, 60.0
        definition = {"name": "Peak", "layer": "summary", "threshold": 1.0, "near_fraction": 0.8, "terms": [
            {"signal": "pressure", "window_min": None, "reducer": "peak", "region": "roi",
             "reference": 60.0, "weight": 1.0, "inverted": False}]}
        context = Context(pressure, 0.0, 2.0, TemporalAnalysis(), HotspotTracker(), MotionAnalyzer(), l_shape())
        self.assertAlmostEqual(evaluate_indices(validate_indices([definition]), context)["Peak"], 0.5)
```

- [ ] **Step 2: Run, expect failure** - the new tests error (`too many values to unpack` / `KeyError: 'centre_offset_x'`).

- [ ] **Step 3: `processing/analysis.py`** - add `from processing.roi import roi_centre` and replace `roi_statistics` with:

```python
def roi_statistics(grid, roi, unit, threshold_kpa=0, cell_area_m2=None):
    """Statistics over the cells of a boolean ROI mask"""
    values = grid[roi]
    cell_rows, cell_cols = np.nonzero(roi)
    valid = np.isfinite(values)
    usable = values[valid]
    sensors = values.size
    result = {"sensors": sensors, "unit": unit, "area_m2": None,
              "mean": None, "peak": None, "minimum": None, "std": None,
              "force_n": None, "contact_cells": None, "contact_area_m2": None,
              "center_x": None, "center_y": None,
              "centre_offset_x": None, "centre_offset_y": None}
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

    if mask.any():
        weights = values[mask]
        result["center_x"] = float(np.dot(cell_cols[mask], weights) / weights.sum())
        result["center_y"] = float(np.dot(cell_rows[mask], weights) / weights.sum())
        centre_row, centre_col = roi_centre(roi)
        result["centre_offset_x"] = result["center_x"] - centre_col
        result["centre_offset_y"] = result["center_y"] - centre_row
    return result
```

- [ ] **Step 4: `processing/temporal.py`** - rename `_roi_bounds` to `_roi_mask` in `reset_all` and `clear_roi`; in `update()` replace the `if self._roi_bounds is not None:` block with:

```python
        if self._roi_mask is not None:
            area = self.state[self._roi_mask]
            if np.count_nonzero(area == FULL) >= area.size * self.roi_relief_fraction:
                self._roi_last_relief = timestamp
```

and replace the head of `roi()` (signature through `count = states.size`) with:

```python
    def roi(self, mask):
        """Temporal statistics over the cells of a boolean ROI mask"""
        if self._roi_mask is None or not np.array_equal(mask, self._roi_mask):
            self._roi_mask = mask.copy()
            self._roi_last_relief = None
        area = mask
        states = self.state[area]
        count = states.size
```

(the returned dict below it is unchanged: `self.exposure[area]` etc. already work with a mask).

- [ ] **Step 5: `processing/validation.py`** - add `import numpy as np` and `from processing.roi import roi_centre`; replace the first four lines of `compare_hotspot_roi`'s body with:

```python
    expected = {(int(row), int(col)) for row, col in np.argwhere(roi)}
    center = roi_centre(roi)
```

- [ ] **Step 6: `processing/indices.py`** - in `_reduce`, replace the two lines `row0, row1, col0, col1 = roi` and `grid = grid[row0:row1 + 1, col0:col1 + 1]` with `grid = grid[roi]`.

- [ ] **Step 7: Update existing tests to masks** (add `from processing.roi import rectangle_mask` to each file):
  - `tests/test_phase3.py`: `roi_statistics(pressure, (1, 2, 1, 3), ...)` -> `roi_statistics(pressure, rectangle_mask(pressure.shape, (1, 1), (2, 3)), ...)`.
  - `tests/test_phase4.py`: `self.analysis.roi((0, 1, 0, 1))` -> `self.analysis.roi(rectangle_mask((config.TOTAL_ROWS, config.TOTAL_COLS), (0, 0), (1, 1)))`.
  - `tests/test_indices.py`: both `roi=(0, 1, 0, 1)` -> `roi=rectangle_mask(SHAPE, (0, 0), (1, 1))`.

- [ ] **Step 8: Run everything** - `python -m unittest discover -s tests -v`. The six new tests and all processing tests pass; GUI tests that reach `DesktopApp` ROI code are fixed in Task 3 (none of the existing ones select an ROI, so expect 125 tests, OK).

---

### Task 3: Main window uses the mask; old selection removed

**Files:**
- Modify: `gui/desktop.py`, `gui/analysis_window.py`, `gui/annotation_window.py`, `gui/help_window.py`
- Test: `tests/test_roi.py`

**Interfaces:**
- Consumes: mask-based `roi_statistics`, `TemporalAnalysis.roi`, `compare_hotspot_roi`, `mask_to_cells`.
- Produces (on `DesktopApp`): `roi` (mask or `None`), `set_roi(mask)`. Removed: `roi_corner`, `selecting_roi`, `roi_patch`, `_begin_roi_selection`, `_clear_roi`.

- [ ] **Step 1: Write the failing tests** - add to `tests/test_roi.py` (import `import tkinter as tk`):

```python
class DesktopRoiTests(unittest.TestCase):
    def setUp(self):
        from gui.desktop import DesktopApp
        try:
            self.app = DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(self.app._on_close)

    def frame(self, timestamp=1):
        grid = np.zeros(SHAPE)
        grid[0, 0], grid[2, 2], grid[1, 1] = 100.0, 300.0, 900.0
        self.app._handle_new_frame(grid, sample_time=timestamp)

    def test_set_roi_feeds_history_outline_and_temporal(self):
        self.frame(1)
        self.app.set_roi(l_shape())
        np.testing.assert_array_equal(self.app.roi, l_shape())
        self.frame(2)
        self.assertAlmostEqual(self.app.roi_history[-1]["mean"], 80.0)   # (100 + 300) / 5 cells
        self.assertEqual(self.app.roi_history[-1]["peak"], 300.0)
        self.app._update_plot()                                          # draws the cell outline
        np.testing.assert_array_equal(self.app.temporal._roi_mask, l_shape())

    def test_empty_or_none_clears_the_roi(self):
        self.app.set_roi(l_shape())
        self.app.set_roi(np.zeros(SHAPE, dtype=bool))
        self.assertIsNone(self.app.roi)
        self.app.set_roi(l_shape())
        self.app.set_roi(None)
        self.assertIsNone(self.app.roi)
        self.assertEqual(len(self.app.roi_history), 0)

    def test_known_hotspot_annotation_stores_the_cells(self):
        self.frame(1)
        self.app.set_roi(l_shape())
        event = self.app.add_annotation("Known hotspot")
        self.assertEqual(event["payload"]["roi"], [[0, 0], [1, 0], [2, 0], [2, 1], [2, 2]])
        self.assertIn("overlap", event["payload"]["comparison"])

    def test_old_selection_path_is_gone(self):
        self.assertFalse(hasattr(self.app, "_begin_roi_selection"))
        self.app._open_analysis()
        tabs = self.app.analysis_window.tabs
        self.assertEqual([tabs.tab(tab, "text") for tab in tabs.tabs()], ["Distribution", "Load and symmetry"])
```

- [ ] **Step 2: Run, expect failure** - `AttributeError: 'DesktopApp' object has no attribute 'set_roi'`.

- [ ] **Step 3: `gui/desktop.py`**
  - Remove `from matplotlib.patches import Rectangle`. Add `from processing.roi import mask_to_cells`.
  - In `__init__` delete `self.roi_corner = None` and `self.selecting_roi = False`.
  - In `_build_plot` delete `self.roi_patch = None`.
  - In `_apply_grid_shape` replace `self.roi = self.roi_corner = None` and `self.selecting_roi = False` with `self.roi = None`.
  - In `add_annotation` replace `payload["roi"] = list(self.roi)` with `payload["roi"] = mask_to_cells(self.roi)`.
  - Replace `_begin_roi_selection` and `_clear_roi` with:

```python
    def set_roi(self, mask):
        """Make a boolean cell mask the live ROI; None or an empty mask clears it"""
        self.roi = mask.copy() if mask is not None and mask.any() else None
        self.temporal.clear_roi()
        self.roi_history.clear()
        self._add_roi_history_sample()
        self._update_plot()
        self._refresh_analysis()

    def _outline_cells(self, mask, **style):
        """Draw a line along the cell edges around the selected cells of a mask"""
        fine = np.kron(np.pad(mask, 1).astype(float), np.ones((8, 8)))  # padded: closes at the mat edge
        y = (np.arange(fine.shape[0]) + 0.5) / 8 - 1.5
        x = (np.arange(fine.shape[1]) + 0.5) / 8 - 1.5
        self.axes.contour(x, y, fine, levels=[0.5], **style)
```

  - In `_update_plot` replace the whole block from `if self.roi_patch is not None:` through `self.axes.add_patch(self.roi_patch)` with:

```python
            if self.roi is not None:
                self._outline_cells(self.roi, colors="blue", linewidths=1.5)
```

  - In `_on_plot_click` delete the whole `if self.selecting_roi:` block (through its `return`).
  - Replace the body of `_add_roi_history_sample` after the `if self.roi is None or self.frame is None: return` guard with:

```python
        grid, _unit = self._analysis_grid()
        values = grid[self.roi]
        valid = values[np.isfinite(values)]
        if valid.size:
            pressure = self.frame["pressure"]
            temporal = self.temporal.roi(self.roi)
            self.roi_history.append({"time": self.frame_timestamp,
                                     "mean": float(valid.mean()), "peak": float(valid.max()),
                                     "pressure_mean": None if pressure is None else float(np.nanmean(pressure[self.roi])),
                                     "exposure_mean": temporal["mean_exposure"],
                                     "burden_mean": temporal["mean_burden"],
                                     "relieved_fraction": temporal["relieved_fraction"]})
```

- [ ] **Step 4: `gui/analysis_window.py`**
  - Remove `roi_statistics` from the import, the `bar` frame with the two ROI buttons, the `roi_tab` frame and its `self.tabs.add(roi_tab, text="ROI")`, the `self.roi_text` / `self.roi_figure` / `self.roi_canvas` block, and the whole `_refresh_roi` method.
  - `refresh()` becomes:

```python
    def refresh(self):
        if not self.window.winfo_exists():
            return
        if self.tabs.index("current") == 0:
            self._refresh_distribution()
        else:
            self._refresh_load()
```

  - Change the intro label to `'How pressure is spread over the whole mat, and its left/right and upper/lower balance. Regions are in the ROI window.'`.

- [ ] **Step 5: Wording** - `gui/annotation_window.py`: both "on the main heatmap" strings become "in the ROI window" (`"Uses the ROI currently applied in the ROI window"` / `"Apply an ROI in the ROI window first"`). `gui/help_window.py` line 39: `Analysis — distributions, load balance, and symmetry.` followed by a new line `ROI — pick a region (box, polygon or paint) and see its pressure, balance and history.`

- [ ] **Step 6: Leftover check** - this must print nothing:

```bash
grep -rnE "roi_corner|selecting_roi|roi_patch|_begin_roi_selection|_clear_roi\b|_roi_bounds|row0, row1, col0, col1" --include="*.py" gui processing
```

- [ ] **Step 7: Run everything** - `python -m unittest discover -s tests -v` -> 129 tests, OK.

---

### Task 4: ROI window

**Files:**
- Create: `gui/roi_window.py`
- Modify: `gui/desktop.py`
- Test: `tests/test_roi.py`

**Interfaces:**
- Consumes: `app.set_roi(mask)`, `app.roi`, `app.roi_history`, `app.frame`, `app._analysis_grid()`, `app.temporal.roi(mask)`, `app.hotspots.active`, `app.contact_threshold_kpa`, `app.cell_area_m2`; all of `processing/roi.py`; `roi_statistics`.
- Produces: `RoiWindow(parent, app)` with `window`, `selection` (working mask), `mode_var` (`"2 corners"`, `"Polygon"`, `"Paint"`), `remove_var`, `pending` (corners placed so far), `trail`, `summary_var`; handlers `press(cell, double=False)`, `drag(cell)`, `release()`, `cancel()`, `undo()`, `clear()`, `invert()`, `apply()`, `new_snapshot()`, `reset()`, `refresh()`. `cell` is `(row, col)` or `None` when the pointer is off the grid. `DesktopApp.roi_window`, `DesktopApp._open_roi()`.

- [ ] **Step 1: Write the failing tests** - add to `DesktopRoiTests`:

```python
    def open_window(self):
        self.frame(1)
        self.app._open_roi()
        return self.app.roi_window

    def test_each_mode_builds_the_selection_and_remove_takes_away(self):
        window = self.open_window()
        window.mode_var.set("2 corners")
        window.press((0, 0))
        window.drag((1, 2))                    # preview only
        self.assertEqual(int(window.selection.sum()), 0)
        window.press((1, 2))
        self.assertEqual(int(window.selection.sum()), 6)

        window.mode_var.set("Polygon")
        for corner in ((5, 5), (5, 9), (9, 5)):
            window.press(corner)
        window.press((9, 5), double=True)      # double-click closes
        self.assertEqual(int(window.selection.sum()), 6 + 15)
        self.assertEqual(window.pending, [])

        window.mode_var.set("Paint")
        window.remove_var.set(True)
        window.press((0, 0))
        window.drag((0, 2))                    # fast drag: (0,1) is filled in
        window.drag(None)                      # pointer left the grid
        window.release()
        self.assertEqual(int(window.selection.sum()), 6 + 15 - 3)
        self.assertFalse(window.selection[0, 1])

    def test_polygon_needs_three_corners_and_escape_cancels(self):
        window = self.open_window()
        window.mode_var.set("Polygon")
        window.press((1, 1))
        window.press((4, 4))
        window.press((4, 4), double=True)
        self.assertEqual((int(window.selection.sum()), len(window.pending)), (0, 2))
        window.cancel()
        self.assertEqual(window.pending, [])
        window.mode_var.set("2 corners")
        window.press(None)                     # click in the margin
        self.assertEqual(window.pending, [])

    def test_undo_clear_and_invert(self):
        window = self.open_window()
        window.mode_var.set("Paint")
        window.press((3, 3))
        window.drag((3, 6))
        window.release()                       # one stroke = one undo step
        window.invert()
        self.assertEqual(int(window.selection.sum()), 240 - 4)
        window.clear()
        self.assertEqual(int(window.selection.sum()), 0)
        window.undo()
        window.undo()
        self.assertEqual(int(window.selection.sum()), 4)
        window.undo()
        self.assertEqual(int(window.selection.sum()), 0)
        window.undo()                          # nothing left to undo
        self.assertEqual(int(window.selection.sum()), 0)

    def test_nothing_is_live_until_apply_and_the_output_follows(self):
        self.app.set_roi(l_shape())
        window = self.open_window()
        np.testing.assert_array_equal(window.selection, l_shape())   # starts from the live ROI
        history = len(self.app.roi_history)
        window.mode_var.set("2 corners")
        window.press((0, 0))
        window.press((2, 2))
        np.testing.assert_array_equal(self.app.roi, l_shape())       # not applied yet
        self.assertEqual(len(self.app.roi_history), history)
        window.apply()
        self.assertEqual(int(self.app.roi.sum()), 9)
        self.frame(2)
        window.refresh()
        self.assertIn("9 cells", window.summary_var.get())
        self.assertEqual(len(window.trail), 1)
        window.clear()
        window.apply()                                               # empty selection clears the ROI
        self.assertIsNone(self.app.roi)
        window.refresh()
        self.assertIn("No ROI applied", window.summary_var.get())

    def test_grid_size_change_resets_the_open_window(self):
        import config
        self.addCleanup(setattr, config, "TOTAL_ROWS", config.TOTAL_ROWS)
        self.addCleanup(setattr, config, "TOTAL_COLS", config.TOTAL_COLS)
        window = self.open_window()
        window.press((0, 0))
        self.app._apply_grid_shape(20, 12)
        self.assertEqual(window.selection.shape, (20, 12))
        self.assertEqual((int(window.selection.sum()), window.pending), (0, []))
        window.refresh()
```

- [ ] **Step 2: Run, expect failure** - `AttributeError: 'DesktopApp' object has no attribute '_open_roi'`.

- [ ] **Step 3: Implement the window** - create `gui/roi_window.py`:

```python
"""Pick a region of interest (box, polygon or paint) and see its pressure, balance and history."""

import tkinter as tk
from collections import deque
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import ListedColormap
from matplotlib.figure import Figure

import config
from processing.analysis import roi_statistics
from processing.roi import cells_mask, polygon_mask, rectangle_mask, roi_balance, stroke_cells

MODES = ("2 corners", "Polygon", "Paint")
UNDO_STEPS = 20
TRAIL_SAMPLES = 60
SELECTED_COLORS = ListedColormap(["#b8b8b8", "#5b9d61"])  # unselected grey, selected green


def _show(value, suffix="", digits=2):
    return "-" if value is None or not np.isfinite(value) else f"{value:.{digits}f}{suffix}"


class RoiWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("ROI")
        self.window.geometry("1100x760")
        ttk.Label(self.window, wraplength=1060, padding=(8, 6), text=(
            "Pick a region on the frozen snapshot, then Apply. Left/right and upper/lower mean as drawn "
            "on screen - the app does not know which way the mat lies under the person.")).pack(fill=tk.X)

        bar = ttk.Frame(self.window, padding=(8, 0))
        bar.pack(fill=tk.X)
        self.mode_var = tk.StringVar(value=MODES[0])
        self.mode_var.trace_add("write", lambda *_: self.cancel())
        for mode in MODES:
            ttk.Radiobutton(bar, text=mode, value=mode, variable=self.mode_var).pack(side=tk.LEFT)
        self.remove_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Remove (instead of add)", variable=self.remove_var).pack(side=tk.LEFT, padx=12)
        for text, command in (("Undo", self.undo), ("Clear", self.clear), ("Invert", self.invert),
                              ("New snapshot", self.new_snapshot), ("Apply", self.apply)):
            ttk.Button(bar, text=text, command=command).pack(side=tk.LEFT, padx=3)
        self.hint_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.hint_var).pack(side=tk.LEFT, padx=12)

        body = ttk.Frame(self.window)
        body.pack(fill=tk.BOTH, expand=True)
        self.select_figure = Figure(figsize=(5, 5))
        self.select_axes = self.select_figure.add_subplot()
        self.select_canvas = FigureCanvasTkAgg(self.select_figure, master=body)
        self.select_canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.select_canvas.mpl_connect("button_press_event",
                                       lambda event: self.press(self._cell(event), double=event.dblclick))
        self.select_canvas.mpl_connect("motion_notify_event", lambda event: self.drag(self._cell(event)))
        self.select_canvas.mpl_connect("button_release_event", lambda _event: self.release())
        self.window.bind("<Escape>", lambda _event: self.cancel())

        side = ttk.Frame(body)
        side.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.summary_var = tk.StringVar()
        ttk.Label(side, textvariable=self.summary_var, justify=tk.LEFT, wraplength=520,
                  padding=6).pack(fill=tk.X)
        self.output_figure = Figure(figsize=(5.4, 5.2))
        self.output_canvas = FigureCanvasTkAgg(self.output_figure, master=side)
        self.output_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.trail = deque(maxlen=TRAIL_SAMPLES)  # recent balance points of the live ROI
        self.reset()

    # ---- working selection

    @staticmethod
    def _shape():
        return config.TOTAL_ROWS, config.TOTAL_COLS

    def reset(self):
        """Start over from the live ROI (also called when the mat's grid size changes)"""
        live = self.app.roi
        self.selection = live.copy() if live is not None else np.zeros(self._shape(), dtype=bool)
        self._undo = deque(maxlen=UNDO_STEPS)
        self.pending = []     # corners placed so far (box: first corner; polygon: all corners)
        self._stroke = None   # cells of the paint stroke in progress
        self._hover = None
        self.trail.clear()
        self.new_snapshot()
        self.refresh()

    def new_snapshot(self):
        """Freeze the grid the main window is showing, to select against"""
        self.snapshot = None if self.app.frame is None else np.array(self.app._analysis_grid()[0], dtype=float)
        if self.snapshot is not None and self.snapshot.shape != self._shape():
            self.snapshot = None
        self._draw_selection()

    def _cell(self, event):
        if event.inaxes != self.select_axes or event.xdata is None or event.ydata is None:
            return None
        row, col = round(event.ydata), round(event.xdata)
        rows, cols = self._shape()
        return (row, col) if 0 <= row < rows and 0 <= col < cols else None

    def _commit(self, mask):
        self._undo.append(self.selection.copy())
        self.selection = self.selection & ~mask if self.remove_var.get() else self.selection | mask

    def press(self, cell, double=False):
        mode = self.mode_var.get()
        if mode == "Polygon" and double:
            if len(self.pending) >= 3:
                self._commit(polygon_mask(self._shape(), self.pending))
                self.pending = []
        elif cell is None:
            return
        elif mode == "Paint":
            self._stroke = [cell]
        elif mode == "2 corners":
            if not self.pending:
                self.pending = [cell]
            else:
                self._commit(rectangle_mask(self._shape(), self.pending[0], cell))
                self.pending = []
        elif len(self.pending) >= 3 and cell == self.pending[0]:
            self._commit(polygon_mask(self._shape(), self.pending))  # clicked the first corner again
            self.pending = []
        elif not self.pending or cell != self.pending[-1]:
            self.pending.append(cell)
        self._draw_selection()

    def drag(self, cell):
        if cell is None:
            return
        if self._stroke is not None:
            self._stroke.extend(stroke_cells(self._stroke[-1], cell)[1:])
        elif not self.pending or cell == self._hover:
            return
        self._hover = cell
        self._draw_selection()

    def release(self):
        if self._stroke is not None:
            self._commit(cells_mask(self._shape(), self._stroke))
            self._stroke = None
            self._draw_selection()

    def cancel(self):
        self.pending = []
        self._stroke = None
        self._draw_selection()

    def undo(self):
        if self._undo:
            self.selection = self._undo.pop()
            self._draw_selection()

    def clear(self):
        self._undo.append(self.selection.copy())
        self.selection = np.zeros(self._shape(), dtype=bool)
        self._draw_selection()

    def invert(self):
        self._undo.append(self.selection.copy())
        self.selection = ~self.selection
        self._draw_selection()

    def apply(self):
        """Make the working selection the live ROI (an empty one clears it)"""
        self.trail.clear()
        self.app.set_roi(self.selection)
        self.refresh()

    def _draw_selection(self):
        axes = self.select_axes
        axes.clear()
        rows, cols = self._shape()
        background = np.zeros((rows, cols)) if self.snapshot is None else np.nan_to_num(self.snapshot)
        axes.imshow(background, cmap="Greys", aspect="auto", vmin=0, vmax=max(1.0, float(background.max())))
        shown = self.selection.copy()
        if self._stroke is not None:
            stroke = cells_mask((rows, cols), self._stroke)
            shown = shown & ~stroke if self.remove_var.get() else shown | stroke
        axes.imshow(np.ma.masked_where(~shown, shown), cmap=ListedColormap(["#5b9d61"]), alpha=0.55,
                    aspect="auto", vmin=0, vmax=1)
        axes.set_xticks(np.arange(-0.5, cols), minor=True)
        axes.set_yticks(np.arange(-0.5, rows), minor=True)
        axes.grid(which="minor", color="#cccccc", linewidth=0.4)
        axes.tick_params(which="minor", length=0)
        if self.pending:
            corners = self.pending + ([self._hover] if self._hover is not None else [])
            if self.mode_var.get() == "2 corners" and len(corners) == 2:
                (row0, col0), (row1, col1) = corners
                corners = [(row0, col0), (row0, col1), (row1, col1), (row1, col0), (row0, col0)]
            axes.plot([col for _row, col in corners], [row for row, _col in corners],
                      color="blue", marker="o", markersize=4, linewidth=1)
        axes.set_xlim(-0.5, cols - 0.5)
        axes.set_ylim(rows - 0.5, -0.5)
        axes.set_title("Snapshot" if self.snapshot is not None else "No data yet - you can still select cells",
                       fontsize=9)
        changed = self.app.roi is None and self.selection.any() or (
            self.app.roi is not None and not np.array_equal(self.app.roi, self.selection))
        self.hint_var.set(f"{int(self.selection.sum())} cells selected" + (" - not applied" if changed else ""))
        self.select_canvas.draw_idle()

    # ---- output for the live ROI

    def refresh(self):
        if not self.window.winfo_exists():
            return
        if self.selection.shape != self._shape():
            self.reset()
            return
        self.output_figure.clear()
        roi = self.app.roi
        if roi is None or self.app.frame is None:
            self.summary_var.set("No ROI applied. Select cells on the snapshot and press Apply."
                                 if roi is None else "Waiting for data.")
            self.output_canvas.draw_idle()
            return
        grid, unit = self.app._analysis_grid()
        stats = roi_statistics(grid, roi, unit, self.app.contact_threshold_kpa, self.app.cell_area_m2)
        temporal = self.app.temporal.roi(roi)
        balance = roi_balance(grid, roi)
        cells = {(int(row), int(col)) for row, col in np.argwhere(roi)}
        hotspots = sum(1 for track in self.app.hotspots.active if cells & track["cells"])
        if balance is not None:
            self.trail.append((balance["x"], balance["y"]))
        self.summary_var.set(self._summary(stats, temporal, hotspots, unit))

        layout = self.output_figure.add_gridspec(2, 2, height_ratios=(3, 2))
        mini = self.output_figure.add_subplot(layout[0, 0])
        mini.imshow(roi.astype(int), cmap=SELECTED_COLORS, vmin=0, vmax=1, aspect="auto")
        if stats["center_x"] is not None:
            mini.plot([stats["center_x"]], [stats["center_y"]], marker="+", color="black",
                      markersize=12, markeredgewidth=2)
        mini.set_title("Selected cells (+ = centre of pressure)", fontsize=9)
        mini.set_xticks([])
        mini.set_yticks([])
        self._draw_balance(self.output_figure.add_subplot(layout[0, 1]), balance)
        history = self.output_figure.add_subplot(layout[1, :])
        if self.app.roi_history:
            start = self.app.roi_history[0]["time"]
            times = [item["time"] - start for item in self.app.roi_history]
            history.plot(times, [item["mean"] for item in self.app.roi_history], label="Mean")
            history.plot(times, [item["peak"] for item in self.app.roi_history], label="Peak")
            history.legend(fontsize=8)
        history.set_xlabel("Time since Apply (s)")
        history.set_ylabel(unit)
        self.output_figure.tight_layout()
        self.output_canvas.draw_idle()

    def _draw_balance(self, axes, balance):
        axes.set_xlim(-1, 1)
        axes.set_ylim(-1, 1)
        axes.set_aspect("equal")
        axes.axhline(0, color="#999999", linewidth=0.8)
        axes.axvline(0, color="#999999", linewidth=0.8)
        axes.set_xlabel("left  <-  load  ->  right", fontsize=8)
        axes.set_ylabel("lower  <-  load  ->  upper", fontsize=8)
        if balance is None:
            axes.set_title("No load in this region", fontsize=9)
            return
        axes.set_title("Balance within the region", fontsize=9)
        if len(self.trail) > 1:
            axes.plot([x for x, _y in self.trail], [y for _x, y in self.trail], color="#9da7b1", linewidth=1)
        axes.plot([balance["x"]], [balance["y"]], marker="o", color="#5b9d61", markersize=9)
        quadrants = balance["quadrants"]
        for key, x, y, horizontal, vertical in (("upper_left", -0.95, 0.95, "left", "top"),
                                                ("upper_right", 0.95, 0.95, "right", "top"),
                                                ("lower_left", -0.95, -0.95, "left", "bottom"),
                                                ("lower_right", 0.95, -0.95, "right", "bottom")):
            axes.text(x, y, f"{quadrants[key]:.0f}%", ha=horizontal, va=vertical, fontsize=9)

    def _summary(self, stats, temporal, hotspots, unit):
        area = _show(None if stats["area_m2"] is None else stats["area_m2"] * 10_000, " cm²", 1)
        contact = "needs kPa" if stats["contact_cells"] is None else str(stats["contact_cells"])
        contact_area = _show(None if stats["contact_area_m2"] is None else stats["contact_area_m2"] * 10_000,
                             " cm²", 1)
        centre = ("-" if stats["center_x"] is None else
                  f"x={stats['center_x']:.1f}, y={stats['center_y']:.1f} "
                  f"(offset from region centre {stats['centre_offset_x']:+.1f}, {stats['centre_offset_y']:+.1f} cells)")
        since = temporal["since_relief_s"]
        return (
            f"{stats['sensors']} cells | area {area}\n"
            f"Mean {_show(stats['mean'], ' ' + unit)} | peak {_show(stats['peak'], ' ' + unit)} | "
            f"min {_show(stats['minimum'], ' ' + unit)} | std {_show(stats['std'], ' ' + unit)}\n"
            f"Force {_show(stats['force_n'], ' N')} | contact {contact} cells ({contact_area})\n"
            f"{'Centre of pressure' if unit == 'kPa' else 'Signal centre'}: {centre}\n"
            f"Since region last relieved: {_show(since / 60, ' min', 1)} | loaded "
            f"{100 * temporal['loaded_fraction']:.0f}% | relieved {100 * temporal['relieved_fraction']:.0f}%\n"
            f"Exposure mean/max {temporal['mean_exposure']:.2f}/{temporal['max_exposure']:.2f} kPa·min | "
            f"burden mean/max {temporal['mean_burden']:.2f}/{temporal['max_burden']:.2f}\n"
            f"Active hotspots overlapping: {hotspots}")
```

- [ ] **Step 4: Wire it into `gui/desktop.py`**
  - Import `from gui.roi_window import RoiWindow`.
  - In `__init__` next to `self.analysis_window = None`: `self.roi_window = None`.
  - In `_build_data_bar`, before the "Analysis..." button: `ttk.Button(bar, text="ROI...", command=self._open_roi).pack(side=tk.LEFT, padx=(0, 8))`.
  - Next to `_open_analysis`:

```python
    def _open_roi(self):
        if self.roi_window is not None and self.roi_window.window.winfo_exists():
            self.roi_window.window.lift()
        else:
            self.roi_window = RoiWindow(self.root, self)
```

  - In `_poll`, inside the `if time.time() - self._last_feature_draw >= 0.5:` block:

```python
                if self.roi_window is not None and self.roi_window.window.winfo_exists():
                    self.roi_window.refresh()
```

  - At the end of `_apply_grid_shape`:

```python
        if self.roi_window is not None and self.roi_window.window.winfo_exists():
            self.roi_window.reset()
```

- [ ] **Step 5: Run everything** - `python -m unittest discover -s tests -v` -> 134 tests, OK.

---

### Task 5: Docs

**Files:**
- Modify: `Raspberry Pi/STATUS.md`, `Raspberry Pi/notes.md`, `Raspberry Pi/README.md`

- [ ] **Step 1:** `STATUS.md`: add `roi.py` to the `processing/` map (ROI = boolean cell mask; builders and balance) and `roi_window.py` to `gui/`; note that `analysis.py` no longer owns ROI selection; add the spec/plan under design docs as built.
- [ ] **Step 2:** `notes.md`: replace the "ROI window rework" bullet under larger design passes and the "Analysis: rename button to Select ROI" bullet with one line saying the ROI window is built, and what is not included (several named ROIs, saving ROIs, brush size, remembering the ROI across restarts).
- [ ] **Step 3:** `README.md`: one sentence under "First run" on **ROI...**.
- [ ] **Step 4: Final run** - `python -m unittest discover -s tests -v` -> 134 tests, OK. Then start the app on the Simulated source, open **ROI...**, try each mode with Add and Remove, Apply, and confirm the outline on the main heatmap, the mini grid, the balance plot and the history line.
