"""ROI as a set of cells: mask builders, balance, consumers, and the ROI window."""

import math
import tkinter as tk
import unittest

import numpy as np

from processing.analysis import roi_statistics
from processing.hotspots import HotspotTracker
from processing.indices import evaluate_indices, validate_indices
from processing.motion import MotionAnalyzer
from processing.roi import (cells_mask, mask_to_cells, polygon_mask, rectangle_mask,
                            roi_balance, roi_centre, stroke_cells)
from processing.signals import Context
from processing.temporal import TemporalAnalysis
from processing.validation import compare_hotspot_roi

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
        self.assertEqual(len(window.trail), 1)                       # Apply starts a fresh balance trail
        self.frame(2)
        window.refresh()
        self.assertIn("9 cells", window.summary_var.get())
        self.assertEqual(len(window.trail), 2)
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


if __name__ == "__main__":
    unittest.main()
