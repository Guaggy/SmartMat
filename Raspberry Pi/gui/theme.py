"""Flat light/dark theme built from the branding palette: ttk styles, plain tk widgets and matplotlib figures.

apply_theme(root, mode) can be called again at any time: every open window and every figure made with
figure() follows. The pure helpers (palette, heatmap_cmap, contrast, text_on) need no display.
"""

import functools
import weakref
import tkinter as tk
from tkinter import font as tkfont, ttk

import matplotlib
from matplotlib.colors import LinearSegmentedColormap, ListedColormap
from matplotlib.figure import Figure

from branding import HEATMAP_STOPS, PALETTE_DARK, PALETTE_LIGHT

MODES = ("light", "dark")
FONT_SIZES = {"small": 9, "body": 10, "title": 12, "big": 16}
FADE_BELOW = 0.02  # heatmap values below this fraction of full scale fade into the background
_mode = "light"
_family = "TkDefaultFont"  # replaced by Segoe UI (or the Tk default's family) in apply_theme
_figures = weakref.WeakSet()


# ---- pure helpers

def palette(mode=None):
    """The colour tokens of a mode (default: the active one)"""
    return PALETTE_DARK if (mode or _mode) == "dark" else PALETTE_LIGHT


def current_mode():
    return _mode


def _rgb(colour):
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(colour):
    def channel(value):
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(value) for value in _rgb(colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(first, second):
    """WCAG contrast ratio of two #RRGGBB colours (1..21)"""
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def text_on(background):
    """White or brand navy, whichever reads better on background (for solid status cells)"""
    return max(("#FFFFFF", PALETTE_LIGHT["ink"]), key=lambda colour: contrast(colour, background))


def heatmap_cmap(mode=None):
    """The shared pressure ramp; the lowest FADE_BELOW of the scale fades into the theme's hm_bg"""
    return _heatmap_cmap(mode if mode in MODES else _mode)


@functools.lru_cache(maxsize=None)
def _heatmap_cmap(mode):
    stops = [(0.0, palette(mode)["hm_bg"]), (FADE_BELOW, _hex(HEATMAP_STOPS[0][1]))]
    stops += [(t, _hex(rgb)) for t, rgb in HEATMAP_STOPS[1:]]
    return LinearSegmentedColormap.from_list(f"smartmat_{mode}", stops)


def health_cmap(mode=None):
    """Sensor-health states (processing.sensor_health.HEALTH_STATES order), palette colours where one fits"""
    p = palette(mode)
    return ListedColormap([p["ok"], p["warn"], "#9a77bb", "#db7950", p["bad"], p["idle"], p["ink"], p["line"]])


def _hex(rgb):
    return "#%02X%02X%02X" % rgb


# ---- Tk

def _font_family(root):
    families = set(tkfont.families(root))
    return "Segoe UI" if "Segoe UI" in families else tkfont.nametofont("TkDefaultFont", root).actual("family")


def font(size="small", weight="normal"):
    """A font tuple in the theme's family and size scale (FONT_SIZES key)"""
    return (_family, FONT_SIZES[size], weight)


def _configure_fonts(root):
    family = _font_family(root)
    small = FONT_SIZES["small"]
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkIconFont", "TkTooltipFont", "TkSmallCaptionFont"):
        tkfont.nametofont(name, root).configure(family=family, size=small)
    tkfont.nametofont("TkHeadingFont", root).configure(family=family, size=small, weight="normal")
    tkfont.nametofont("TkCaptionFont", root).configure(family=family, size=FONT_SIZES["body"])
    return family


def _style(root, p, family):
    style = ttk.Style(root)
    if "smartmat" not in style.theme_names():
        style.theme_create("smartmat", parent="clam")
    style.theme_use("smartmat")
    flat = {"lightcolor": p["panel"], "darkcolor": p["panel"], "bordercolor": p["line"]}
    style.configure(".", background=p["panel"], foreground=p["ink"], troughcolor=p["panel2"],
                    fieldbackground=p["panel"], selectbackground=p["accent"], selectforeground=p["on_accent"],
                    insertcolor=p["ink"], focuscolor=p["accent"], relief="flat", font="TkDefaultFont", **flat)
    style.map(".", foreground=[("disabled", p["muted"])])

    button = {"background": p["panel2"], "lightcolor": p["panel2"], "darkcolor": p["panel2"],
              "bordercolor": p["line"], "padding": (6, 2)}
    style.configure("TButton", **button)
    style.map("TButton", background=[("disabled", p["panel"]), ("pressed", p["line"]), ("active", p["line"])],
              lightcolor=[("pressed", p["line"]), ("active", p["line"])],
              darkcolor=[("pressed", p["line"]), ("active", p["line"])])
    style.configure("Accent.TButton", background=p["accent"], foreground=p["on_accent"], bordercolor=p["accent"],
                    lightcolor=p["accent"], darkcolor=p["accent"], font=(family, FONT_SIZES["small"], "bold"))
    style.map("Accent.TButton", background=[("disabled", p["panel2"]), ("pressed", p["accent_fill"]),
                                            ("active", p["accent_fill"])],
              lightcolor=[("pressed", p["accent_fill"]), ("active", p["accent_fill"])],
              darkcolor=[("pressed", p["accent_fill"]), ("active", p["accent_fill"])],
              bordercolor=[("disabled", p["line"])], foreground=[("disabled", p["muted"])])

    for name in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(name, fieldbackground=p["panel"], background=p["panel2"], foreground=p["ink"],
                        arrowcolor=p["muted"], padding=(4, 2), **flat)
        style.map(name, fieldbackground=[("readonly", p["panel"]), ("disabled", p["panel2"])],
                  bordercolor=[("focus", p["accent"])], lightcolor=[("focus", p["panel"])],
                  background=[("active", p["line"])])
    # a read-only combobox would otherwise paint its value as an accent-coloured selection
    style.map("TCombobox", selectbackground=[("readonly", p["panel"])], selectforeground=[("readonly", p["ink"])])
    style.configure("ComboboxPopdownFrame", background=p["panel"], bordercolor=p["line"], relief="solid",
                    borderwidth=1)

    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=p["panel"], indicatorbackground=p["panel"], indicatorforeground=p["ink"],
                        upperbordercolor=p["muted"], lowerbordercolor=p["muted"], indicatormargin=(0, 0, 4, 0))
        style.map(name, background=[("active", p["panel"])],
                  indicatorbackground=[("pressed", p["panel2"]), ("disabled", p["panel2"])])

    style.configure("Toolbutton", background=p["panel"], foreground=p["muted"], padding=(8, 3), relief="flat")
    style.map("Toolbutton", background=[("selected", p["panel2"]), ("active", p["panel2"])],
              foreground=[("selected", p["accent"]), ("active", p["ink"])])

    style.configure("TNotebook", background=p["panel"], tabmargins=(0, 2, 0, 0), **flat)
    style.configure("TNotebook.Tab", background=p["panel2"], foreground=p["muted"], padding=(10, 3),
                    lightcolor=p["panel2"], darkcolor=p["panel2"], bordercolor=p["line"])
    style.map("TNotebook.Tab", background=[("selected", p["panel"])], foreground=[("selected", p["accent"])],
              lightcolor=[("selected", p["panel"])], expand=[("selected", (0, 0, 0, 0))])

    style.configure("Treeview", background=p["panel"], fieldbackground=p["panel"], foreground=p["ink"],
                    rowheight=20, **flat)
    style.map("Treeview", background=[("selected", p["accent"])], foreground=[("selected", p["on_accent"])])
    style.configure("Treeview.Heading", background=p["panel2"], foreground=p["muted"], relief="flat",
                    lightcolor=p["panel2"], darkcolor=p["panel2"], bordercolor=p["line"])
    style.map("Treeview.Heading", background=[("active", p["line"])])

    style.configure("TScrollbar", background=p["panel2"], troughcolor=p["panel"], arrowcolor=p["muted"],
                    gripcount=0, lightcolor=p["panel2"], darkcolor=p["panel2"], bordercolor=p["line"])
    style.map("TScrollbar", background=[("active", p["line"])])
    style.configure("TSeparator", background=p["line"])
    style.configure("TLabelframe", background=p["panel"], **flat)
    style.configure("TLabelframe.Label", background=p["panel"], foreground=p["muted"])

    # app-specific styles
    style.configure("Muted.TLabel", foreground=p["muted"])
    style.configure("Group.TLabel", foreground=p["muted"])
    style.configure("Heading.TLabel", font=(family, FONT_SIZES["body"], "bold"))
    style.configure("Warn.TLabel", foreground=p["warn_text"])
    style.configure("Link.TLabel", foreground=p["accent"], font=(family, FONT_SIZES["small"], "underline"))
    style.configure("Toolbar.TFrame", background=p["panel2"])
    style.configure("Toolbar.TLabel", background=p["panel2"], foreground=p["muted"])
    style.configure("Toolbar.TCheckbutton", background=p["panel2"], indicatorbackground=p["panel"])
    style.map("Toolbar.TCheckbutton", background=[("active", p["panel2"])])
    style.configure("Toolbar.TSeparator", background=p["line"])
    style.configure("Status.TFrame", background=p["panel2"])
    style.configure("Status.TLabel", background=p["panel2"], foreground=p["ink"])
    style.configure("StatusMuted.TLabel", background=p["panel2"], foreground=p["muted"])
    bar, bar_ink = p["brandbar"], p["ink"]  # brandbar = the logo lockup's own background in each mode
    style.configure("Header.TFrame", background=bar)
    style.configure("Header.TLabel", background=bar, foreground=bar_ink)
    style.configure("HeaderMuted.TLabel", background=bar, foreground=p["muted"])
    style.configure("Header.TButton", background=bar, foreground=bar_ink, bordercolor=p["line"],
                    lightcolor=bar, darkcolor=bar)
    style.map("Header.TButton", background=[("active", p["line"])])
    style.configure("Header.Toolbutton", background=bar, foreground=p["muted"])
    style.map("Header.Toolbutton", background=[("selected", bar), ("active", bar)],
              foreground=[("selected", p["accent"]), ("active", bar_ink)])
    return style


def _tk_options(p):
    """Option-database defaults (new plain tk widgets) and live settings (existing ones), by widget class"""
    listish = {"background": p["panel"], "foreground": p["ink"], "selectBackground": p["accent"],
               "selectForeground": p["on_accent"], "highlightBackground": p["line"], "highlightColor": p["accent"],
               "highlightThickness": 1, "borderWidth": 0, "relief": "flat"}
    return {
        "Tk": {"background": p["panel"]},
        "Toplevel": {"background": p["panel"]},
        "Frame": {"background": p["panel"]},
        "Listbox": listish,
        "Text": {**listish, "insertBackground": p["ink"]},
        "Canvas": {"background": p["panel"], "highlightThickness": 0},
        "Menu": {"background": p["panel"], "foreground": p["ink"], "activeBackground": p["accent"],
                 "activeForeground": p["on_accent"], "relief": "flat"},
    }


def _restyle_tk(widget, options):
    """Recolour plain tk widgets under widget (ttk ones follow the style). tk.Labels are left alone: the app
    uses them only for state cells, which it recolours itself."""
    settings = options.get(widget.winfo_class())
    if settings:
        try:
            widget.configure(**{key.lower(): value for key, value in settings.items()})
        except tk.TclError:
            pass
    for child in widget.winfo_children():
        _restyle_tk(child, options)


# ---- matplotlib

def _rc(p):
    return {"figure.facecolor": p["panel"], "axes.facecolor": p["panel"], "axes.edgecolor": p["line"],
            "axes.labelcolor": p["ink"], "axes.titlecolor": p["ink"], "text.color": p["ink"],
            "xtick.color": p["muted"], "ytick.color": p["muted"], "xtick.labelcolor": p["muted"],
            "ytick.labelcolor": p["muted"], "grid.color": p["line"], "legend.facecolor": p["panel"],
            "legend.edgecolor": p["line"], "legend.labelcolor": p["ink"], "savefig.facecolor": p["panel"]}


def figure(**kwargs):
    """A matplotlib Figure that follows the theme (also after a later apply_theme)"""
    fig = Figure(**kwargs)
    _figures.add(fig)
    style_figure(fig)
    return fig


def style_figure(fig, mode=None):
    """Recolour a figure and its axes (incl. colorbars and 3D panes) for a mode"""
    p = palette(mode)
    fig.set_facecolor(p["panel"])
    for axes in fig.axes:
        axes.set_facecolor(p["panel"])
        axes.tick_params(which="both", colors=p["muted"], labelcolor=p["muted"])
        for spine in axes.spines.values():
            spine.set_edgecolor(p["line"])
        axes.title.set_color(p["ink"])
        for axis in (axes.xaxis, axes.yaxis, getattr(axes, "zaxis", None)):
            if axis is None:
                continue
            axis.label.set_color(p["ink"])
            if hasattr(axis, "set_pane_color"):  # 3D
                axis.set_pane_color(matplotlib.colors.to_rgba(p["panel2"]))
        for line in axes.get_xgridlines() + axes.get_ygridlines():
            line.set_color(p["line"])


def apply_theme(root, mode):
    """Theme the whole app (root, its open windows, tracked figures) for "light" or "dark"; returns the mode used"""
    global _mode, _family
    _mode = mode if mode in MODES else "light"
    p = palette()
    family = _family = _configure_fonts(root)
    _style(root, p, family)
    options = _tk_options(p)
    for widget_class, settings in options.items():
        for key, value in settings.items():
            root.option_add(f"*{widget_class}.{key}", value)
    for key, value in options["Listbox"].items():  # the dropdown list of every combobox
        root.option_add(f"*TCombobox*Listbox.{key}", value)
    _restyle_tk(root, options)
    matplotlib.rcParams.update(_rc(p))
    for fig in list(_figures):
        style_figure(fig)
        if fig.canvas is not None:
            fig.canvas.draw_idle()
    return _mode
