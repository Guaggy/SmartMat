"""Tool windows as tabs: the Page adapter, open/select, Pop out, refresh of hidden tabs, Simple view, theme."""

import tkinter as tk
import unittest
from tkinter import ttk
from unittest import mock

from gui import theme
from gui.page import Page, is_shown, make_window


class PageTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(self.root.destroy)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack()
        self.notebook.add(ttk.Frame(self.notebook), text="Live")

    def test_toplevel_methods(self):
        page = make_window(self.notebook)
        self.assertIsInstance(page, Page)
        page.title("Tool")
        self.assertEqual(page.title(), "Tool")
        page.geometry("800x600")  # ignored
        self.assertTrue(page.selected())
        self.notebook.select(0)
        self.assertFalse(is_shown(page))
        page.lift()
        self.assertTrue(is_shown(page))
        closed = []
        page.protocol("WM_DELETE_WINDOW", lambda: closed.append(True))
        page.close()
        self.assertEqual(closed, [True])
        page.destroy()
        self.assertFalse(page.winfo_exists())
        self.assertEqual(len(self.notebook.tabs()), 1)

    def test_other_parent_gives_a_toplevel(self):
        window = make_window(self.root)
        self.assertIsInstance(window, tk.Toplevel)
        self.assertTrue(is_shown(window))


class DesktopTabTests(unittest.TestCase):
    def setUp(self):
        from gui import desktop
        self.enterContext(mock.patch.object(desktop, "save_mat_names"))
        self.enterContext(mock.patch("app_settings.save_theme"))
        try:
            self.app = desktop.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(self.app._on_close)
        self.show("Advanced")

    def show(self, view):
        self.app.view_var.set(view)
        self.app._apply_view()
        self.app.root.update()

    def names(self):
        return [self.app.notebook.tab(tab, "text") for tab in self.app.notebook.tabs()]

    def test_open_twice_selects_the_existing_tab(self):
        app = self.app
        app._open_hotspots()
        app._open_help()
        first = app.hotspot_window
        app._open_hotspots()
        self.assertIs(app.hotspot_window, first)
        self.assertEqual(self.names(), ["Live", "Hotspots", "Help"])
        self.assertTrue(first.window.selected())

    def test_pop_out_moves_the_tool_to_a_toplevel(self):
        app = self.app
        app._open_hotspots()
        page = app.hotspot_window.window
        app._pop_out(page)
        self.assertFalse(page.winfo_exists())
        self.assertIsInstance(app.hotspot_window.window, tk.Toplevel)
        self.assertEqual(self.names(), ["Live"])

    def test_only_the_selected_tab_is_refreshed(self):
        app = self.app
        app._open_hotspots()
        app._open_motion()  # selected; Hotspots now hidden
        app.root.update()
        with mock.patch.object(app.hotspot_window, "refresh") as hidden, \
                mock.patch.object(app.motion_window, "refresh") as shown:
            app._tab_changed()
            hidden.assert_not_called()
            shown.assert_called_once()
            app.hotspot_window.window.lift()
            app.root.update()  # <<NotebookTabChanged>> refreshes the newly selected tab once
            hidden.assert_called()
        self.assertFalse(app._shown(app.motion_window))
        self.assertTrue(app._shown(app.hotspot_window))

    def test_simple_hides_the_strip_and_advanced_restores_it(self):
        app = self.app
        app._open_hotspots()
        app._open_help()
        app.root.update()
        self.assertEqual(app.tab_actions.winfo_manager(), "place")  # Pop out / Close for the selected tab
        self.show("Simple")
        self.assertEqual(app.tab_actions.winfo_manager(), "")
        self.assertEqual(str(app.notebook.cget("style")), "Bare.TNotebook")
        self.assertEqual(app.notebook.select(), str(app.content))
        self.assertEqual(self.names(), ["Live", "Hotspots", "Help"])  # nothing closed
        self.show("Advanced")
        self.assertEqual(str(app.notebook.cget("style")), "TNotebook")
        self.assertTrue(app.help_window.window.selected())
        self.assertEqual(app.tab_actions.winfo_manager(), "place")
        app.notebook.select(app.content)
        app.root.update()
        self.assertEqual(app.tab_actions.winfo_manager(), "")  # nothing to pop out on Live

    def test_theme_flip_with_tabs_open_and_closed_tab_releases_figures(self):
        app = self.app
        for opener in (app._open_hotspots, app._open_temporal, app._open_indices, app._open_analysis):
            opener()
        app.root.update()
        for mode in ("dark", "light"):
            app.theme_var.set(mode)
            app._set_theme()
            app.root.update()
        figures = {app.analysis_window.distribution_figure}
        before = len(theme._figures)
        app.analysis_window.window.close()
        app.root.update()
        self.assertLess(len(theme._figures), before)
        self.assertFalse(figures & set(theme._figures))
        app.theme_var.set("dark")
        app._set_theme()
        app.root.update()


if __name__ == "__main__":
    unittest.main()
