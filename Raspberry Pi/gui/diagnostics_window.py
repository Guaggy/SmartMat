"""Sensor-health heatmaps and selected-cell readings."""

import tkinter as tk
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import ListedColormap
from matplotlib.figure import Figure

import config
from processing.sensor_health import HEALTH_STATES

HEALTH_COLORS = ListedColormap([
    "#5b9d61", "#e8b04e", "#9a77bb", "#db7950",
    "#bd5555", "#777777", "#303030", "#9da7b1",
])


def _value(value):
    return "-" if not np.isfinite(value) else f"{value:.2f}"


class DiagnosticsWindow:
    def __init__(self, parent, health, selected_cell_getter, on_select, quality_getter=None):
        self.health = health
        self.selected_cell_getter = selected_cell_getter
        self.on_select = on_select
        self.quality_getter = quality_getter
        self.window = tk.Toplevel(parent)
        self.window.title("Sensor diagnostics")
        self.window.geometry("760x650")
        ttk.Label(self.window, text='Checks that the mat itself is working properly: shows which sensors look faulty, stuck or drifting.', wraplength=760, padding=(8, 6)).pack(side=tk.TOP, fill=tk.X)

        bar = ttk.Frame(self.window, padding=8)
        bar.pack(fill=tk.X)
        ttk.Label(bar, text="View:").pack(side=tk.LEFT)
        self.view_var = tk.StringVar(value="Health state")
        menu = ttk.Combobox(bar, textvariable=self.view_var, state="readonly",
                            values=["Health state", "Noise", "Drift"], width=15)
        menu.pack(side=tk.LEFT, padx=6)
        menu.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Label(bar, text="Received values; noise and drift use unloaded samples").pack(side=tk.LEFT, padx=8)

        self.figure = Figure(figsize=(6, 5))
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.window)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.mpl_connect("button_press_event", self._on_click)

        self.summary_var = tk.StringVar()
        self.source_var = tk.StringVar()
        ttk.Label(self.window, textvariable=self.source_var, wraplength=730, padding=8).pack(fill=tk.X)
        self.detail_var = tk.StringVar()
        ttk.Label(self.window, textvariable=self.summary_var, wraplength=730, padding=8).pack(fill=tk.X)
        ttk.Label(self.window, textvariable=self.detail_var, wraplength=730, padding=8).pack(fill=tk.X)
        self.refresh()

    def _on_click(self, event):
        if event.inaxes != self.axes or event.xdata is None or event.ydata is None:
            return
        row, col = round(event.ydata), round(event.xdata)
        if 0 <= row < config.TOTAL_ROWS and 0 <= col < config.TOTAL_COLS:
            self.on_select(row, col)
            self.refresh()

    def refresh(self):
        if not self.window.winfo_exists():
            return
        quality = self.quality_getter() if self.quality_getter is not None else None
        if quality is not None:
            age = quality["age_s"]
            self.source_var.set(
                f"Source: {quality['received']} received, {quality['valid']} valid, "
                f"{quality['malformed']} malformed, {quality['dropped']} dropped | "
                f"grid size {quality['unexpected_grid_size']}, range {quality['out_of_range']}, "
                f"no source timestamp {quality['missing_timestamps']} | "
                f"{quality['rate_hz']:.1f} frames/s, last valid {'-' if age is None else f'{age:.1f}s ago'}")
        view = self.view_var.get()
        self.figure.clear()
        self.axes = self.figure.add_subplot()
        if view == "Health state":
            grid = self.health.states
            image = self.axes.imshow(grid, cmap=HEALTH_COLORS, vmin=-0.5, vmax=7.5, aspect="auto")
            bar = self.figure.colorbar(image, ax=self.axes, ticks=range(len(HEALTH_STATES)))
            bar.ax.set_yticklabels(HEALTH_STATES)
        else:
            grid = self.health.noise if view == "Noise" else self.health.drift
            finite = grid[np.isfinite(grid)]
            limit = max(1.0, float(np.max(np.abs(finite)))) if finite.size else 1.0
            if view == "Noise":
                image = self.axes.imshow(grid, cmap="viridis", vmin=0, vmax=limit, aspect="auto")
                self.figure.colorbar(image, ax=self.axes, label="Raw rolling std")
            else:
                image = self.axes.imshow(grid, cmap="coolwarm", vmin=-limit, vmax=limit, aspect="auto")
                self.figure.colorbar(image, ax=self.axes, label="Drift vs initial unloaded reading")
        selected = self.selected_cell_getter()
        if selected is not None:
            self.axes.plot(selected[1], selected[0], marker="s", markersize=13,
                           fillstyle="none", color="blue", linestyle="None")
            cell = self.health.cell(*selected)
            self.detail_var.set(
                f"Row {selected[0]}, col {selected[1]}: {cell['state']} | received {_value(cell['current'])} | "
                f"mean {_value(cell['mean'])} | variance {_value(cell['variance'])} | "
                f"noise {_value(cell['noise'])} | tare/reference {_value(cell['baseline_offset'])} | "
                f"drift {_value(cell['drift'])} | calibrated {'yes' if cell['calibrated'] else 'no'}"
            )
        else:
            self.detail_var.set("Click a cell to inspect its diagnostic values")
        counts = np.bincount(self.health.states.flatten(), minlength=len(HEALTH_STATES))
        self.summary_var.set(" | ".join(f"{label}: {count}" for label, count in zip(HEALTH_STATES, counts) if count))
        self.axes.set_xlabel("Column")
        self.axes.set_ylabel("Row")
        self.figure.tight_layout()
        self.canvas.draw_idle()
