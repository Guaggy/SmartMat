"""Pick a region of interest (box, polygon or paint) and see its pressure, balance and history."""

import tkinter as tk
from collections import deque
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import ListedColormap
from matplotlib.figure import Figure

import config
from processing.analysis import roi_statistics
from processing.roi import cells_mask, polygon_mask, rectangle_mask, roi_balance, stroke_cells

MODES = ("2 corners", "Polygon", "Paint")
UNDO_STEPS = 20
TRAIL_SAMPLES = 60
SELECTED_COLORS = ListedColormap(["#b8b8b8", "#5b9d61"])  # unselected grey, selected green


def _show(value, suffix="", digits=2):
    return "-" if value is None or not np.isfinite(value) else f"{value:.{digits}f}{suffix}"


class RoiWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("ROI")
        self.window.geometry("1100x760")
        ttk.Label(self.window, wraplength=1060, padding=(8, 6), text=(
            "Pick a region on the frozen snapshot, then Apply. Left/right and upper/lower mean as drawn "
            "on screen - the app does not know which way the mat lies under the person.")).pack(fill=tk.X)

        bar = ttk.Frame(self.window, padding=(8, 0))
        bar.pack(fill=tk.X)
        self.mode_var = tk.StringVar(value=MODES[0])
        self.mode_var.trace_add("write", lambda *_: self.cancel())
        for mode in MODES:
            ttk.Radiobutton(bar, text=mode, value=mode, variable=self.mode_var).pack(side=tk.LEFT)
        self.remove_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Remove (instead of add)", variable=self.remove_var).pack(side=tk.LEFT, padx=12)
        for text, command in (("Undo", self.undo), ("Clear", self.clear), ("Invert", self.invert),
                              ("New snapshot", self.new_snapshot), ("Apply", self.apply)):
            ttk.Button(bar, text=text, command=command).pack(side=tk.LEFT, padx=3)
        self.hint_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.hint_var).pack(side=tk.LEFT, padx=12)

        body = ttk.Frame(self.window)
        body.pack(fill=tk.BOTH, expand=True)
        self.select_figure = Figure(figsize=(5, 5))
        self.select_axes = self.select_figure.add_subplot()
        self.select_canvas = FigureCanvasTkAgg(self.select_figure, master=body)
        self.select_canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.select_canvas.mpl_connect("button_press_event",
                                       lambda event: self.press(self._cell(event), double=event.dblclick))
        self.select_canvas.mpl_connect("motion_notify_event", lambda event: self.drag(self._cell(event)))
        self.select_canvas.mpl_connect("button_release_event", lambda _event: self.release())
        self.window.bind("<Escape>", lambda _event: self.cancel())

        side = ttk.Frame(body)
        side.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.summary_var = tk.StringVar()
        ttk.Label(side, textvariable=self.summary_var, justify=tk.LEFT, wraplength=520,
                  padding=6).pack(fill=tk.X)
        self.output_figure = Figure(figsize=(5.4, 5.2))
        self.output_canvas = FigureCanvasTkAgg(self.output_figure, master=side)
        self.output_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.trail = deque(maxlen=TRAIL_SAMPLES)  # recent balance points of the live ROI
        self.reset()

    # ---- working selection

    @staticmethod
    def _shape():
        return config.TOTAL_ROWS, config.TOTAL_COLS

    def reset(self):
        """Start over from the live ROI (also called when the mat's grid size changes)"""
        live = self.app.roi
        self.selection = live.copy() if live is not None else np.zeros(self._shape(), dtype=bool)
        self._undo = deque(maxlen=UNDO_STEPS)
        self.pending = []     # corners placed so far (box: first corner; polygon: all corners)
        self._stroke = None   # cells of the paint stroke in progress
        self._hover = None
        self.trail.clear()
        self.new_snapshot()
        self.refresh()

    def new_snapshot(self):
        """Freeze the grid the main window is showing, to select against"""
        self.snapshot = None if self.app.frame is None else np.array(self.app._analysis_grid()[0], dtype=float)
        if self.snapshot is not None and self.snapshot.shape != self._shape():
            self.snapshot = None
        self._draw_selection()

    def _cell(self, event):
        if event.inaxes != self.select_axes or event.xdata is None or event.ydata is None:
            return None
        row, col = round(event.ydata), round(event.xdata)
        rows, cols = self._shape()
        return (row, col) if 0 <= row < rows and 0 <= col < cols else None

    def _commit(self, mask):
        self._undo.append(self.selection.copy())
        self.selection = self.selection & ~mask if self.remove_var.get() else self.selection | mask

    def press(self, cell, double=False):
        mode = self.mode_var.get()
        if mode == "Polygon" and double:
            if len(self.pending) >= 3:
                self._commit(polygon_mask(self._shape(), self.pending))
                self.pending = []
        elif cell is None:
            return
        elif mode == "Paint":
            self._stroke = [cell]
        elif mode == "2 corners":
            if not self.pending:
                self.pending = [cell]
            else:
                self._commit(rectangle_mask(self._shape(), self.pending[0], cell))
                self.pending = []
        elif len(self.pending) >= 3 and cell == self.pending[0]:
            self._commit(polygon_mask(self._shape(), self.pending))  # clicked the first corner again
            self.pending = []
        elif not self.pending or cell != self.pending[-1]:
            self.pending.append(cell)
        self._draw_selection()

    def drag(self, cell):
        if cell is None:
            return
        if self._stroke is not None:
            self._stroke.extend(stroke_cells(self._stroke[-1], cell)[1:])
        elif not self.pending or cell == self._hover:
            return
        self._hover = cell
        self._draw_selection()

    def release(self):
        if self._stroke is not None:
            self._commit(cells_mask(self._shape(), self._stroke))
            self._stroke = None
            self._draw_selection()

    def cancel(self):
        self.pending = []
        self._stroke = None
        self._draw_selection()

    def undo(self):
        if self._undo:
            self.selection = self._undo.pop()
            self._draw_selection()

    def clear(self):
        self._undo.append(self.selection.copy())
        self.selection = np.zeros(self._shape(), dtype=bool)
        self._draw_selection()

    def invert(self):
        self._undo.append(self.selection.copy())
        self.selection = ~self.selection
        self._draw_selection()

    def apply(self):
        """Make the working selection the live ROI (an empty one clears it)"""
        self.trail.clear()
        self.app.set_roi(self.selection)
        self.refresh()

    def _draw_selection(self):
        axes = self.select_axes
        axes.clear()
        rows, cols = self._shape()
        background = np.zeros((rows, cols)) if self.snapshot is None else np.nan_to_num(self.snapshot)
        axes.imshow(background, cmap="Greys", aspect="auto", vmin=0, vmax=max(1.0, float(background.max())))
        shown = self.selection.copy()
        if self._stroke is not None:
            stroke = cells_mask((rows, cols), self._stroke)
            shown = shown & ~stroke if self.remove_var.get() else shown | stroke
        axes.imshow(np.ma.masked_where(~shown, shown), cmap=ListedColormap(["#5b9d61"]), alpha=0.55,
                    aspect="auto", vmin=0, vmax=1)
        axes.set_xticks(np.arange(-0.5, cols), minor=True)
        axes.set_yticks(np.arange(-0.5, rows), minor=True)
        axes.grid(which="minor", color="#cccccc", linewidth=0.4)
        axes.tick_params(which="minor", length=0)
        if self.pending:
            corners = self.pending + ([self._hover] if self._hover is not None else [])
            if self.mode_var.get() == "2 corners" and len(corners) == 2:
                (row0, col0), (row1, col1) = corners
                corners = [(row0, col0), (row0, col1), (row1, col1), (row1, col0), (row0, col0)]
            axes.plot([col for _row, col in corners], [row for row, _col in corners],
                      color="blue", marker="o", markersize=4, linewidth=1)
        axes.set_xlim(-0.5, cols - 0.5)
        axes.set_ylim(rows - 0.5, -0.5)
        axes.set_title("Snapshot" if self.snapshot is not None else "No data yet - you can still select cells",
                       fontsize=9)
        changed = self.app.roi is None and self.selection.any() or (
            self.app.roi is not None and not np.array_equal(self.app.roi, self.selection))
        self.hint_var.set(f"{int(self.selection.sum())} cells selected" + (" - not applied" if changed else ""))
        self.select_canvas.draw_idle()

    # ---- output for the live ROI

    def refresh(self):
        if not self.window.winfo_exists():
            return
        if self.selection.shape != self._shape():
            self.reset()
            return
        self.output_figure.clear()
        roi = self.app.roi
        if roi is None or self.app.frame is None:
            self.summary_var.set("No ROI applied. Select cells on the snapshot and press Apply."
                                 if roi is None else "Waiting for data.")
            self.output_canvas.draw_idle()
            return
        grid, unit = self.app._analysis_grid()
        stats = roi_statistics(grid, roi, unit, self.app.contact_threshold_kpa, self.app.cell_area_m2)
        temporal = self.app.temporal.roi(roi)
        balance = roi_balance(grid, roi)
        cells = {(int(row), int(col)) for row, col in np.argwhere(roi)}
        hotspots = sum(1 for track in self.app.hotspots.active if cells & track["cells"])
        if balance is not None:
            self.trail.append((balance["x"], balance["y"]))
        self.summary_var.set(self._summary(stats, temporal, hotspots, unit))

        layout = self.output_figure.add_gridspec(2, 2, height_ratios=(3, 2))
        mini = self.output_figure.add_subplot(layout[0, 0])
        mini.imshow(roi.astype(int), cmap=SELECTED_COLORS, vmin=0, vmax=1, aspect="auto")
        if stats["center_x"] is not None:
            mini.plot([stats["center_x"]], [stats["center_y"]], marker="+", color="black",
                      markersize=12, markeredgewidth=2)
        mini.set_title("Selected cells (+ = centre of pressure)", fontsize=9)
        mini.set_xticks([])
        mini.set_yticks([])
        self._draw_balance(self.output_figure.add_subplot(layout[0, 1]), balance)
        history = self.output_figure.add_subplot(layout[1, :])
        if self.app.roi_history:
            start = self.app.roi_history[0]["time"]
            times = [item["time"] - start for item in self.app.roi_history]
            history.plot(times, [item["mean"] for item in self.app.roi_history], label="Mean")
            history.plot(times, [item["peak"] for item in self.app.roi_history], label="Peak")
            history.legend(fontsize=8)
        history.set_xlabel("Time since Apply (s)")
        history.set_ylabel(unit)
        self.output_figure.tight_layout()
        self.output_canvas.draw_idle()

    def _draw_balance(self, axes, balance):
        axes.set_xlim(-1, 1)
        axes.set_ylim(-1, 1)
        axes.set_aspect("equal")
        axes.axhline(0, color="#999999", linewidth=0.8)
        axes.axvline(0, color="#999999", linewidth=0.8)
        axes.set_xlabel("left  <-  load  ->  right", fontsize=8)
        axes.set_ylabel("lower  <-  load  ->  upper", fontsize=8)
        if balance is None:
            axes.set_title("No load in this region", fontsize=9)
            return
        axes.set_title("Balance within the region", fontsize=9)
        if len(self.trail) > 1:
            axes.plot([x for x, _y in self.trail], [y for _x, y in self.trail], color="#9da7b1", linewidth=1)
        axes.plot([balance["x"]], [balance["y"]], marker="o", color="#5b9d61", markersize=9)
        quadrants = balance["quadrants"]
        for key, x, y, horizontal, vertical in (("upper_left", -0.95, 0.95, "left", "top"),
                                                ("upper_right", 0.95, 0.95, "right", "top"),
                                                ("lower_left", -0.95, -0.95, "left", "bottom"),
                                                ("lower_right", 0.95, -0.95, "right", "bottom")):
            axes.text(x, y, f"{quadrants[key]:.0f}%", ha=horizontal, va=vertical, fontsize=9)

    def _summary(self, stats, temporal, hotspots, unit):
        area = _show(None if stats["area_m2"] is None else stats["area_m2"] * 10_000, " cm²", 1)
        contact = "needs kPa" if stats["contact_cells"] is None else str(stats["contact_cells"])
        contact_area = _show(None if stats["contact_area_m2"] is None else stats["contact_area_m2"] * 10_000,
                             " cm²", 1)
        centre = ("-" if stats["center_x"] is None else
                  f"x={stats['center_x']:.1f}, y={stats['center_y']:.1f} "
                  f"(offset from region centre {stats['centre_offset_x']:+.1f}, {stats['centre_offset_y']:+.1f} cells)")
        since = temporal["since_relief_s"]
        return (
            f"{stats['sensors']} cells | area {area}\n"
            f"Mean {_show(stats['mean'], ' ' + unit)} | peak {_show(stats['peak'], ' ' + unit)} | "
            f"min {_show(stats['minimum'], ' ' + unit)} | std {_show(stats['std'], ' ' + unit)}\n"
            f"Force {_show(stats['force_n'], ' N')} | contact {contact} cells ({contact_area})\n"
            f"{'Centre of pressure' if unit == 'kPa' else 'Signal centre'}: {centre}\n"
            f"Since region last relieved: {_show(since / 60, ' min', 1)} | loaded "
            f"{100 * temporal['loaded_fraction']:.0f}% | relieved {100 * temporal['relieved_fraction']:.0f}%\n"
            f"Exposure mean/max {temporal['mean_exposure']:.2f}/{temporal['max_exposure']:.2f} kPa·min | "
            f"burden mean/max {temporal['mean_burden']:.2f}/{temporal['max_burden']:.2f}\n"
            f"Active hotspots overlapping: {hotspots}")
