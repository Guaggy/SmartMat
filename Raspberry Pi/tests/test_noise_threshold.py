"""'Ignore signal <=' applies to every non-derived Data mode, Calibrated pressure included."""

import tkinter as tk
import unittest

import numpy as np

import config


class NoiseThresholdTests(unittest.TestCase):
    def setUp(self):
        from gui.desktop import DesktopApp
        try:
            self.app = DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(self.app._on_close)
        self.app.display_scale = 1                 # no interpolation: image cell == grid cell
        self.app.data_mode_var.set("Calibrated pressure")
        grid = np.zeros((config.TOTAL_ROWS, config.TOTAL_COLS))
        grid[0, 0], grid[1, 1] = 100.0, 400.0     # default curve: 1000 raw = 50 kPa -> 5 and 20 kPa
        self.app._handle_new_frame(grid, sample_time=1)

    def shown(self):
        self.app._update_plot()
        return np.asarray(self.app.image.get_array())

    def test_cells_at_or_below_the_threshold_show_as_zero(self):
        self.assertAlmostEqual(self.shown()[0, 0], 5.0)
        self.app.noise_threshold_var.set("5")
        self.app._apply_noise_threshold()
        shown = self.shown()
        self.assertEqual(shown[0, 0], 0.0)
        self.assertAlmostEqual(shown[1, 1], 20.0)

    def test_difference_view_uses_the_threshold_too(self):
        self.app.noise_threshold_var.set("10")
        self.app._apply_noise_threshold()
        self.app.reference_grid = np.zeros((config.TOTAL_ROWS, config.TOTAL_COLS))
        self.app.reference_mode = "pressure"
        self.app.difference_var.set(True)
        shown = self.shown()
        self.assertEqual(shown[0, 0], 0.0)
        self.assertAlmostEqual(shown[1, 1], 20.0)


if __name__ == "__main__":
    unittest.main()
