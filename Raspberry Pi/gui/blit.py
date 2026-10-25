"""Redraw only the artists that change each frame; axes, ticks, labels and the colorbar stay a cached bitmap.

A full matplotlib draw lays out every tick label and text again (about 40 ms for the live heatmap, nearly all of it
text), while the heatmap image and its overlays are a few ms. The live view animates the image, overlays and markers
(`set_artists`), `update()` restores the cached bitmap and draws just those. Anything that changes what the cached
bitmap shows (colour limits, colormap, a resize, a theme change) needs one full draw: `set_artists` takes a
signature of that static state, and a resize or any other full draw refreshes the bitmap by itself (draw_event).
Needs no Tk: any canvas with copy_from_bbox / restore_region / blit works (tests use Agg).
"""

from matplotlib.artist import Artist
from matplotlib.image import AxesImage


def flatten(artist):
    """The drawable artists of a plot call's result (matplotlib before 3.8: a ContourSet is a list of collections)"""
    if isinstance(artist, Artist):
        return [artist]
    return list(getattr(artist, "collections", []))


class Blitter:
    def __init__(self, canvas):
        self.canvas = canvas
        self.background = None
        self.artists = []
        self.signature = None
        self._size = None
        canvas.mpl_connect("draw_event", self._on_draw)

    def set_artists(self, artists, signature):
        """The artists to redraw each update (animated: a full draw skips them, then draws them on the bitmap itself);
        a changed signature of the static parts forces the next update to be a full draw"""
        # drawn in z-order like matplotlib does (a spine sits over the image edge, text over both)
        self.artists = sorted((item for artist in artists for item in flatten(artist)), key=lambda item: item.get_zorder())
        for artist in self.artists:
            artist.set_animated(True)
            if isinstance(artist, AxesImage):
                # matplotlib draws an animated image anyway; keeping it invisible between our draws keeps it out of the
                # cached bitmap, so cells a new frame leaves transparent (NaN) cannot show the old frame through
                artist.set_visible(False)
        if signature != self.signature:
            self.signature = signature
            self.background = None

    def invalidate(self):
        self.background = None

    def _on_draw(self, event):
        if event is not None and event.canvas is not self.canvas:
            return
        figure = self.canvas.figure
        self.background = self.canvas.copy_from_bbox(figure.bbox)
        self._size = tuple(figure.bbox.size)
        self._draw_artists()

    def _draw_artists(self):
        for artist in self.artists:
            hidden = isinstance(artist, AxesImage)
            if hidden:
                artist.set_visible(True)
            self.canvas.figure.draw_artist(artist)
            if hidden:
                artist.set_visible(False)

    def update(self):
        """Blit the animated artists onto the cached bitmap; a full (idle) draw when there is no valid bitmap yet"""
        figure = self.canvas.figure
        if self.background is None or self._size != tuple(figure.bbox.size):
            self.background = None
            self.canvas.draw_idle()
            return
        self.canvas.restore_region(self.background)
        self._draw_artists()
        self.canvas.blit(figure.bbox)
