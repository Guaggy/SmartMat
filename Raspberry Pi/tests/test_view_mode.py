"""Simple / Advanced view: only geometry changes, order is restored, state is untouched."""

import tkinter as tk
import unittest
from unittest import mock

import config


class ViewModeTests(unittest.TestCase):
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

    def order(self):
        return [(parent, [w for w in parent.pack_slaves()]) for parent, _ in self.app._rows]

    def show(self, view):
        self.app.view_var.set(view)
        self.app._apply_view()
        self.app.root.update_idletasks()

    def test_advanced_widgets_hidden_in_simple_and_order_restored(self):
        app = self.app
        before = self.order()
        self.assertTrue(app._advanced)
        self.show("Simple")
        for widget in app._advanced:
            if widget is not app.capture_button:
                self.assertFalse(widget.winfo_manager(), widget)
        self.assertTrue(app.data_menu.winfo_manager())          # Data dropdown stays
        self.assertTrue(app.record_button.winfo_manager())
        self.show("Advanced")
        self.assertEqual(self.order(), before)

    def test_order_restored_with_serial_widgets(self):
        app = self.app
        app.source_var.set("Serial")
        with mock.patch("gui.desktop.list_ports", return_value=[]):
            app._refresh_devices()
        before = self.order()
        self.show("Simple")
        self.assertFalse(app.capture_button.winfo_manager())
        self.assertTrue(app.protocol_menu.winfo_manager())
        self.show("Advanced")
        self.assertEqual(self.order(), before)
        self.assertTrue(app.capture_button.winfo_manager())

    def test_toggle_does_not_change_state(self):
        app = self.app
        app.mat_size_mm = (600.0, 480.0)
        app.mirror_h_var.set(True)
        app.paused_var.set(True)
        app.mode_var.set(app.mode_var.get())
        names = ("mat_size_mm", "source", "recorder", "calibration", "pressure_calibration", "frame", "roi")
        snapshot = {name: getattr(app, name) for name in names}
        variables = {name: getattr(app, name).get() for name in
                     ("mirror_h_var", "paused_var", "mode_var", "data_mode_var", "source_var", "device_var")}
        for view in ("Simple", "Advanced", "Simple"):
            self.show(view)
        self.assertEqual({name: getattr(app, name) for name in names}, snapshot)
        self.assertEqual({name: getattr(app, name).get() for name in variables}, variables)

    def test_hotspot_text(self):
        self.assertEqual(self.app._hotspot_text(), "Hotspots: -")


if __name__ == "__main__":
    unittest.main()
