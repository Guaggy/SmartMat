"""One reposition: the pressure map before and after, with a toggle, stats and a legend."""

import tkinter as tk
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# (label, key in the before/after snapshot, unit)
STATS = (
    ("Peak pressure", "peak_kpa", "kPa"),
    ("Mean contact pressure", "mean_kpa", "kPa"),
    ("Contact cells", "contact_cells", "cells"),
    ("Contact area", "contact_area_m2", "m²"),
    ("High-pressure cells", "high_pressure_cells", "cells"),
    ("Hotspots", "hotspot_count", ""),
    ("Persistent hotspots", "persistent_count", ""),
    ("Max burden", "max_burden", ""),
    ("Exposure", "exposure", "kPa·min"),
    ("Hotspot exposure rate", "hotspot_exposure_rate", "kPa"),
    ("Left-side load", "left_percent", "%"),
    ("Upper-side load", "upper_percent", "%"),
)


def _fmt(value, unit):
    return "-" if value is None else f"{value:.1f} {unit}".strip()


class RepositionWindow:
    def __init__(self, parent, record, time_label, cmap):
        self.cmap = cmap
        self.record = record
        self.showing = "before"
        self.window = tk.Toplevel(parent)
        self.window.title(f"Reposition at {time_label}: before / after")
        self.window.geometry("820x600")

        bar = ttk.Frame(self.window, padding=8)
        bar.pack(fill=tk.X)
        ttk.Label(bar, text="Compare the mat's pressure just before and just after the person moved.").pack(side=tk.LEFT)
        self.toggle_button = ttk.Button(bar, command=self._toggle)
        self.toggle_button.pack(side=tk.RIGHT)

        body = ttk.Frame(self.window)
        body.pack(fill=tk.BOTH, expand=True)
        self.figure = Figure(figsize=(5, 5))
        self.canvas = FigureCanvasTkAgg(self.figure, master=body)
        self.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        side = ttk.Frame(body, padding=8)
        side.pack(side=tk.RIGHT, fill=tk.Y)
        self.stat_labels = {}
        for row, text in enumerate(("", "Before", "After")):
            ttk.Label(side, text=text, font=("TkDefaultFont", 9, "bold")).grid(row=0, column=row, padx=4, sticky="w")
        for row, (label, key, unit) in enumerate(STATS, start=1):
            ttk.Label(side, text=label).grid(row=row, column=0, sticky="w", padx=4)
            for column, which in ((1, "before"), (2, "after")):
                ttk.Label(side, text=_fmt(record[which][key], unit)).grid(row=row, column=column, sticky="w", padx=4)
        travel = record["cop_displacement_cells"]
        ttk.Label(side, text="Centre of pressure moved").grid(row=len(STATS) + 1, column=0, sticky="w", padx=4, pady=(6, 0))
        ttk.Label(side, text="-" if travel is None else f"{travel:.1f} cells").grid(
            row=len(STATS) + 1, column=1, columnspan=2, sticky="w", padx=4, pady=(6, 0))

        ttk.Label(self.window, padding=8, wraplength=780,
                  text="Legend: colour = pressure (kPa), same scale for both views. "
                       "Blue + = centre of pressure. Values in the table are before → after.").pack(fill=tk.X)
        self._draw()

    def _toggle(self):
        self.showing = "after" if self.showing == "before" else "before"
        self._draw()

    def _draw(self):
        other = "after" if self.showing == "before" else "before"
        self.toggle_button.configure(text=f"Showing {self.showing.upper()} - click for {other.upper()}")
        self.figure.clear()
        axes = self.figure.add_subplot()
        snapshot = self.record[self.showing]
        grids = [self.record[name].get("grid") for name in ("before", "after")]
        if snapshot.get("grid") is None:
            axes.text(0.5, 0.5, "Map not available for this reposition", ha="center", va="center")
        else:
            top = max([float(np.nanmax(g)) for g in grids if g is not None] + [1.0])
            image = axes.imshow(snapshot["grid"], cmap=self.cmap, vmin=0, vmax=top, aspect="auto")
            self.figure.colorbar(image, ax=axes, label="Pressure (kPa)")
            if snapshot["cop_x"] is not None and snapshot["cop_y"] is not None:
                axes.plot(snapshot["cop_x"], snapshot["cop_y"], marker="+", color="blue",
                          markersize=13, markeredgewidth=2, linestyle="None")
        axes.set_title(self.showing.capitalize())
        axes.set_xlabel("Column")
        axes.set_ylabel("Row")
        self.figure.tight_layout()
        self.canvas.draw_idle()
