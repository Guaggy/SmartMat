"""Desktop theme: palette helpers, contrast, live light/dark switching with every window open, persistence."""

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest import mock

import numpy as np
from matplotlib.colors import to_hex, to_rgba

import app_settings
import branding
import config
from gui import theme

PALETTES = {"light": branding.PALETTE_LIGHT, "dark": branding.PALETTE_DARK}


class PureTests(unittest.TestCase):
    def test_palette_lookup(self):
        self.assertIs(theme.palette("light"), branding.PALETTE_LIGHT)
        self.assertIs(theme.palette("dark"), branding.PALETTE_DARK)
        self.assertIs(theme.palette("purple"), branding.PALETTE_LIGHT)

    def test_heatmap_ramp_fades_into_the_theme_background(self):
        for mode, palette in PALETTES.items():
            cmap = theme.heatmap_cmap(mode)
            self.assertEqual(to_hex(cmap(0.0)).upper(), palette["hm_bg"].upper())
            first = theme._hex(branding.HEATMAP_STOPS[0][1])
            self.assertLess(np.abs(np.array(to_rgba(cmap(theme.FADE_BELOW))) - to_rgba(first)).max(), 0.02)
            self.assertEqual(to_hex(cmap(1.0)).upper(), theme._hex(branding.HEATMAP_STOPS[-1][1]))

    def test_contrast(self):
        self.assertAlmostEqual(theme.contrast("#FFFFFF", "#000000"), 21.0)
        self.assertAlmostEqual(theme.contrast("#777777", "#777777"), 1.0)
        for mode, p in PALETTES.items():
            pairs = {"ink/panel": (p["ink"], p["panel"]), "accent/on_accent": (p["accent"], p["on_accent"]),
                     "link on panel": (p["accent"], p["panel"]), "muted on panel2": (p["muted"], p["panel2"]),
                     "warn text": (p["warn_text"], p["panel"]), "ink on brand bar": (p["ink"], p["brandbar"])}
            for name, (first, second) in pairs.items():
                self.assertGreaterEqual(theme.contrast(first, second), 4.5, f"{mode} {name}")
            for state in ("ok", "warn", "bad", "idle", "line"):  # solid status cells
                self.assertGreaterEqual(theme.contrast(theme.text_on(p[state]), p[state]), 4.5, f"{mode} {state}")


class ThemeAppTests(unittest.TestCase):
    def setUp(self):
        from gui import desktop
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.file = Path(folder.name) / "settings.json"
        self.enterContext(mock.patch.object(app_settings, "FILE", self.file))
        self.enterContext(mock.patch.object(desktop, "save_mat_names"))
        for name in ("TOTAL_ROWS", "TOTAL_COLS"):
            self.addCleanup(setattr, config, name, getattr(config, name))
        self.desktop = desktop
        self.app = self.start()

    def start(self):
        try:
            app = self.desktop.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")

        def close():
            try:
                app._on_close()
            except tk.TclError:
                pass  # already closed by the test
        self.addCleanup(close)
        return app

    def switch(self, mode):
        self.app.theme_var.set(mode)
        self.app._set_theme()
        self.app.root.update_idletasks()

    def widgets(self, widget):
        yield widget
        for child in widget.winfo_children():
            yield from self.widgets(child)

    def test_light_is_the_default(self):
        self.assertEqual(self.app.theme_var.get(), "light")
        self.assertEqual(ttk.Style(self.app.root).lookup("TFrame", "background"), branding.PALETTE_LIGHT["panel"])

    def test_every_window_follows_a_flip(self):
        app = self.app
        app._handle_new_frame(np.full((config.TOTAL_ROWS, config.TOTAL_COLS), 400.0))
        for name in ("_open_about", "_open_calibration", "_open_plot_options", "_open_roi", "_open_analysis",
                     "_open_diagnostics", "_open_temporal", "_open_hotspots", "_open_motion", "_open_indices",
                     "_open_engineering", "_open_help", "_view_baseline"):
            getattr(app, name)()
        app._select_cell(1, 1)  # the selected-cell history window
        app.root.update_idletasks()
        for mode in ("dark", "light", "dark"):
            self.switch(mode)
            p = theme.palette(mode)
            style = ttk.Style(app.root)
            self.assertEqual(style.lookup("TFrame", "background"), p["panel"])
            self.assertEqual(style.lookup("Header.TFrame", "background"), p["brandbar"])
            seen = 0
            for widget in self.widgets(app.root):
                if widget.winfo_class() in ("Tk", "Toplevel", "Listbox", "Text"):
                    self.assertEqual(widget.cget("background").upper(), p["panel"].upper(), widget)
                    seen += 1
            self.assertGreater(seen, 10)
            for fig in list(theme._figures):
                self.assertEqual(to_hex(fig.get_facecolor()).upper(), p["panel"].upper())

    def test_toggle_is_saved_and_used_at_the_next_start(self):
        self.switch("dark")
        self.assertEqual(json.loads(self.file.read_text(encoding="utf-8"))["theme"], "dark")
        self.app._on_close()
        self.app = self.start()
        self.assertEqual(self.app.theme_var.get(), "dark")
        self.assertEqual(ttk.Style(self.app.root).lookup("TFrame", "background"), branding.PALETTE_DARK["panel"])

    def test_bad_saved_value_falls_back_to_light(self):
        for value in ("purple", 3, None):
            self.file.write_text(json.dumps({"theme": value, "mqtt": {"host": "x"}}), encoding="utf-8")
            self.assertEqual(app_settings.theme(), "light")
        with self.assertRaises(ValueError):
            app_settings.save_theme("purple")
        app_settings.save_theme("dark")
        self.assertEqual(json.loads(self.file.read_text(encoding="utf-8"))["mqtt"], {"host": "x"})  # kept


if __name__ == "__main__":
    unittest.main()
