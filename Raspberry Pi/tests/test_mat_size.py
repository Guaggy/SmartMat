"""Mat size: per-cell dimensions, rotation swap, profile round trip and the indicative load text."""

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

import config
from processing import calibration
from processing.calibration import (PressureCalibration, cell_size_mm, load_profile, parse_mat_size,
                                    profile_path, profile_size_mm, save_profile)
from processing.statistics import load_estimate_text, pressure_statistics

ORIENTATION = {"rotation": 0, "mirror_h": False, "mirror_v": False}


class CellSizeTests(unittest.TestCase):
    def setUp(self):
        for name in ("CELL_WIDTH_MM", "CELL_HEIGHT_MM"):
            self.enterContext(mock.patch.object(config, name, None, create=True))

    def test_non_square_grid_with_different_width_and_height(self):
        width, height = cell_size_mm((600.0, 480.0), rows=16, cols=15)
        self.assertAlmostEqual(width, 40.0)   # 600 / 15 columns
        self.assertAlmostEqual(height, 30.0)  # 480 / 16 rows

    def test_rotation_swaps_axes_mirror_and_180_do_not(self):
        # as built 16 x 15 (600 x 480); turned 90 the grid is 15 rows x 16 cols
        self.assertEqual(cell_size_mm((600.0, 480.0), 15, 16, 90), (30.0, 40.0))
        self.assertEqual(cell_size_mm((600.0, 480.0), 15, 16, 270), (30.0, 40.0))
        self.assertEqual(cell_size_mm((600.0, 480.0), 16, 15, 180), (40.0, 30.0))

    def test_not_set_and_cell_fallback(self):
        self.assertIsNone(cell_size_mm(None, 16, 15))
        with mock.patch.object(config, "CELL_WIDTH_MM", 10.0), mock.patch.object(config, "CELL_HEIGHT_MM", 20.0):
            self.assertEqual(cell_size_mm(None, 16, 15), (10.0, 20.0))
            self.assertEqual(cell_size_mm(None, 15, 16, 90), (20.0, 10.0))
            self.assertEqual(cell_size_mm((150.0, 160.0), 16, 15), (10.0, 10.0))  # mat size wins

    def test_parse(self):
        self.assertEqual(parse_mat_size("600 x 480"), (600.0, 480.0))
        self.assertEqual(parse_mat_size("600x480mm"), (600.0, 480.0))
        self.assertIsNone(parse_mat_size("  "))
        for bad in ("600", "a x b", "0 x 5", "-1 x 5", "1 x 2 x 3"):
            with self.assertRaises(ValueError, msg=bad):
                parse_mat_size(bad)


class ProfileSizeTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(calibration, "PROFILES_DIR", Path(folder)))

    def test_round_trip(self):
        save_profile("matA", None, PressureCalibration.default(), ORIENTATION, (600.0, 480.0))
        self.assertEqual(profile_size_mm(load_profile("matA")), (600.0, 480.0))
        save_profile("matB", None, PressureCalibration.default(), ORIENTATION)
        self.assertIsNone(profile_size_mm(load_profile("matB")))

    def test_old_profile_without_size_still_loads(self):
        save_profile("old", None, PressureCalibration.default(), ORIENTATION)
        data = load_profile("old")
        del data["size_mm"]
        profile_path("old").write_text(__import__("json").dumps(data))
        data = load_profile("old")
        self.assertIsNotNone(data)
        self.assertIsNone(profile_size_mm(data))
        calibration.apply_profile(data, calibration.Calibration(), PressureCalibration())

    def test_default_curve_flag_survives_a_profile(self):
        pressure = PressureCalibration.default()
        self.assertTrue(pressure.is_default_curve)
        save_profile("dflt", None, pressure, ORIENTATION)
        restored = PressureCalibration()
        calibration.apply_profile(load_profile("dflt"), calibration.Calibration(), restored)
        self.assertTrue(restored.is_default_curve)
        restored.individual.add_point(0, 0, 500, 10)  # calibrating one cell leaves the others default
        self.assertTrue(restored.is_default_curve)
        restored.use("uniform")
        self.assertFalse(restored.is_default_curve)


class LoadEstimateTests(unittest.TestCase):
    def test_uniform_pressure_grid(self):
        width, height = cell_size_mm((600.0, 480.0), 16, 15)
        area = width * height / 1_000_000
        stats = pressure_statistics(np.full((16, 15), 1.0), 0.5, area)  # 1 kPa over 0.288 m2 = 288 N
        self.assertAlmostEqual(stats["force_n"], 288.0)
        self.assertEqual(load_estimate_text(stats["force_n"]), "Estimated load: 29.4 kg (indicative)")

    def test_states(self):
        self.assertEqual(load_estimate_text(None), "Estimated load: set mat size")
        self.assertEqual(load_estimate_text(98.1, default_curve=True),
                         "Estimated load: 10.0 kg (indicative) - default curve, not calibrated")


class DesktopCellSizeTests(unittest.TestCase):
    def setUp(self):
        from gui import desktop
        for name in ("TOTAL_ROWS", "TOTAL_COLS"):
            self.addCleanup(setattr, config, name, getattr(config, name))
        self.enterContext(mock.patch.object(desktop, "save_mat_names"))
        try:
            self.app = desktop.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(self.app._on_close)

    def test_one_value_follows_size_grid_and_rotation(self):
        app = self.app
        app.mat_size_mm = None
        with mock.patch.object(config, "CELL_WIDTH_MM", None), mock.patch.object(config, "CELL_HEIGHT_MM", None):
            self.assertIsNone(app.cell_area_m2)
            app.mat_size_mm = (600.0, 480.0)
            config.TOTAL_ROWS, config.TOTAL_COLS = 16, 15
            self.assertAlmostEqual(app.cell_area_m2, 0.04 * 0.03)
            app._rotation = 90
            config.TOTAL_ROWS, config.TOTAL_COLS = 15, 16
            self.assertEqual(app.cell_size_mm, (30.0, 40.0))
            self.assertAlmostEqual(app.cell_area_m2, 0.04 * 0.03)
            app._update_cell_info()
            self.assertEqual(app.cell_info_var.get(), "Cell: 30.0 x 40.0 mm")

    def test_bad_mat_size_message_survives_the_next_frame(self):
        app = self.app
        with mock.patch("gui.desktop.simpledialog.askstring", return_value="abc"):
            app._set_mat_size()
        app._handle_new_frame(np.zeros((config.TOTAL_ROWS, config.TOTAL_COLS)))
        self.assertIn("Mat size not changed", app.status_var.get())

    def test_mat_size_button_is_visible_in_simple_view_and_only_once(self):
        def buttons(widget):
            found = [widget] if widget.winfo_class() == "TButton" and widget.cget("text") == "Mat size..." else []
            for child in widget.winfo_children():
                found += buttons(child)
            return found
        app = self.app
        self.assertEqual(len(buttons(app.root)), 1)
        app.view_var.set("Simple")
        app._apply_view()
        self.assertTrue(buttons(app.root)[0].winfo_manager())

    def test_playback_uses_the_recordings_own_size(self):
        app = self.app
        app.source = None  # a recording is not a real mat: no profile
        app.mat_size_mm = None
        app._playback_metadata = {"mat_size_mm": [600.0, 480.0], "orientation": {"rotation": 0}}
        with mock.patch.object(config, "MAT_WIDTH_MM", None, create=True):
            app._load_profile()
            self.assertEqual(app.mat_size_mm, (600.0, 480.0))
            app._playback_metadata = {"mat_size_mm": [600.0, 480.0], "orientation": {"rotation": 90}}
            app._load_profile()  # recorded turned 90, app at 0: cells must be sized with the axes swapped
            self.assertEqual(app.mat_size_mm, (480.0, 600.0))
            app._playback_metadata = {}  # older recording: falls back as before
            app._load_profile()
            self.assertIsNone(app.mat_size_mm)

    def test_size_entered_before_connect_goes_to_a_mat_without_one(self):
        app = self.app
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(calibration, "PROFILES_DIR", Path(folder)))
        with mock.patch("gui.desktop.simpledialog.askstring", return_value="600 x 480"):
            app._set_mat_size()
        self.assertEqual(app._pending_mat_size, (600.0, 480.0))
        app.source = SimpleNamespace(mat_id="matA", shape=(16, 15), stop=lambda: None)
        note = app._apply_pending_size(app._pending_mat_size)
        self.assertIn("applied", note)
        self.assertEqual(app.mat_size_mm, (600.0, 480.0))
        self.assertEqual(profile_size_mm(load_profile("matA")), (600.0, 480.0))
        # a mat whose profile has its own size keeps it and says so
        save_profile("matB", None, PressureCalibration.default(), ORIENTATION, (300.0, 200.0))
        app.source = SimpleNamespace(mat_id="matB", shape=(16, 15), stop=lambda: None)
        app.mat_size_mm = (300.0, 200.0)
        self.assertIn("kept", app._apply_pending_size((600.0, 480.0)))
        self.assertEqual(app.mat_size_mm, (300.0, 200.0))
        self.assertEqual(profile_size_mm(load_profile("matB")), (300.0, 200.0))


if __name__ == "__main__":
    unittest.main()
