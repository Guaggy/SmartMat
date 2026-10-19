"""The desktop's "cells at sensor limit" note shows in both views and hides again (needs a Tk display)."""

import unittest
from unittest import mock

import numpy as np

import config
import gui.desktop as desktop_module

SHAPE = (config.TOTAL_ROWS, config.TOTAL_COLS)


class SaturationNoteTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        for patch in (mock.patch.object(desktop_module, "load_mat_names", return_value={}),
                      mock.patch.object(desktop_module, "INDEX_UPDATE_INTERVAL_S", 0.0)):
            patch.start()
            self.addCleanup(patch.stop)
        try:
            self.app = desktop_module.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(self.app._on_close)

    def test_saturation_note_shows_in_both_views_and_hides_again(self):
        self.app._connect()
        grid = np.zeros(SHAPE)
        grid[:2, :2] = config.VALUE_MAX_DEFAULT
        self.app._handle_new_frame(grid, sample_time=1)
        self.assertEqual(self.app.saturation_var.get(), "4 cells at sensor limit: load and peak read low")
        for view in ("Advanced", "Simple"):
            self.app.view_var.set(view)
            self.app._apply_view()
            self.assertTrue(self.app.saturation_label.winfo_manager())
        self.app._handle_new_frame(np.zeros(SHAPE), sample_time=2)
        self.assertFalse(self.app.saturation_label.winfo_manager())
        self.app._disconnect()


if __name__ == "__main__":
    unittest.main()
