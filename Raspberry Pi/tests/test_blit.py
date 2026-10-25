"""gui/blit.py on an Agg canvas (no Tk needed): a blitted update looks exactly like a full draw."""

import unittest

import matplotlib
matplotlib.use("Agg")
import numpy as np  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from gui.blit import Blitter  # noqa: E402


class Plot:
    """Heatmap + colorbar + a marker and a contour that change every frame, like the live view"""

    def __init__(self):
        self.figure = Figure(figsize=(4, 4))
        self.canvas = FigureCanvasAgg(self.figure)
        self.axes = self.figure.add_subplot()
        self.image = self.axes.imshow(np.zeros((8, 8)), vmin=0, vmax=10, aspect="auto")
        self.figure.colorbar(self.image, ax=self.axes)
        self.marker, = self.axes.plot([], [], marker="+", linestyle="None")
        self.contour = None
        self.blitter = Blitter(self.canvas)

    def show(self, seed, vmax=10, holes=False):
        grid = np.random.default_rng(seed).random((8, 8)) * 10
        if holes:  # NaN cells draw transparent
            grid[seed % 4:seed % 4 + 3, 2:5] = np.nan
        for collection in list(self.axes.collections):
            collection.remove()
        self.image.set_data(grid)
        if self.image.get_clim() != (0, vmax):
            self.image.set_clim(0, vmax)
        self.marker.set_data([seed % 8], [3])
        self.contour = self.axes.contour(np.nan_to_num(grid), levels=[5], colors="k")
        self.blitter.set_artists([self.image, self.marker, self.contour, *self.axes.spines.values()], (0, vmax))
        self.blitter.update()

    def pixels(self):
        return np.asarray(self.canvas.buffer_rgba()).copy()

    def full_draw(self):
        """The same state through a plain draw (an unanimated copy of what is shown)"""
        saved = self.blitter.background  # this draw would bake the unanimated artists into the cached bitmap
        artists, self.blitter.artists = self.blitter.artists, []  # the draw_event hook must not draw them a second time
        for artist in artists:
            artist.set_animated(False)
        self.image.set_visible(True)
        self.canvas.draw()
        pixels = self.pixels()
        self.image.set_visible(False)
        for artist in artists:
            artist.set_animated(True)
        self.blitter.artists = artists
        self.blitter.background = saved
        return pixels


class BlitterTests(unittest.TestCase):
    def test_blitted_update_equals_full_draw(self):
        plot = Plot()
        plot.show(1)  # first update: no bitmap yet, so a full draw
        self.assertIsNotNone(plot.blitter.background)
        for seed in range(2, 6):
            plot.show(seed)  # these only blit
            blitted = plot.pixels()
            np.testing.assert_array_equal(blitted, plot.full_draw(), err_msg=f"frame {seed}")

    def test_transparent_cells_do_not_show_the_previous_frame(self):
        plot = Plot()
        plot.show(1)
        for seed in range(2, 7):
            plot.show(seed, holes=True)
            np.testing.assert_array_equal(plot.pixels(), plot.full_draw(), err_msg=f"frame {seed}")

    def test_blit_does_not_run_a_full_draw(self):
        plot = Plot()
        plot.show(1)
        draws = []
        plot.canvas.mpl_connect("draw_event", lambda event: draws.append(event))
        for seed in range(2, 6):
            plot.show(seed)
        self.assertEqual(draws, [])

    def test_changed_signature_forces_a_full_draw_with_the_new_colorbar(self):
        plot = Plot()
        plot.show(1)
        plot.show(2)
        draws = []
        plot.canvas.mpl_connect("draw_event", lambda event: draws.append(event))
        plot.show(3, vmax=20)  # colour scale changed: the colorbar in the cached bitmap is stale
        self.assertEqual(len(draws), 1)
        np.testing.assert_array_equal(plot.pixels(), plot.full_draw())

    def test_resize_falls_back_to_a_full_draw(self):
        plot = Plot()
        plot.show(1)
        plot.figure.set_size_inches(5, 3)
        draws = []
        plot.canvas.mpl_connect("draw_event", lambda event: draws.append(event))
        plot.show(2)
        self.assertEqual(len(draws), 1)
        np.testing.assert_array_equal(plot.pixels(), plot.full_draw())

    def test_invalidate_redraws_fully_next_time(self):
        plot = Plot()
        plot.show(1)
        plot.blitter.invalidate()
        draws = []
        plot.canvas.mpl_connect("draw_event", lambda event: draws.append(event))
        plot.show(2)
        self.assertEqual(len(draws), 1)
        self.assertIsNotNone(plot.blitter.background)


class UiKnobTests(unittest.TestCase):
    def test_knobs_fall_back_on_missing_or_bad_config(self):
        try:
            import gui.desktop as desktop
        except ImportError:
            self.skipTest("tkinter not installed")
        for value, expected in ((None, 5.0), ("fast", 5.0), (0, 5.0), (-3, 5.0), (8, 8.0), ("2", 2.0)):
            with unittest.mock.patch.object(desktop.app_config, "UI_MAX_FPS", value, create=True):
                self.assertEqual(desktop._ui_number("UI_MAX_FPS", 5, 0.5), expected)
        with unittest.mock.patch.object(desktop.app_config, "UI_MAX_FPS", create=True, new=None):
            delattr(desktop.app_config, "UI_MAX_FPS")
            self.assertEqual(desktop._ui_number("UI_MAX_FPS", 5, 0.5), 5.0)


if __name__ == "__main__":
    unittest.main()
