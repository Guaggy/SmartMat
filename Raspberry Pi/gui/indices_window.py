"""Live values of the user-defined indices: a map heatmap or a summary trend."""

import tkinter as tk
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


class IndicesWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Indices")
        self.window.geometry("760x680")
        ttk.Label(self.window, wraplength=740, padding=(8, 6), text=(
            "Indices are weighted combinations of signals that you define under Engineering > Indices. "
            "They are engineering indices, not validated scores: 1.0 means every signal is at the "
            "reference value you chose.")).pack(side=tk.TOP, fill=tk.X)
        columns = ("layer", "value", "threshold", "state")
        self.list = ttk.Treeview(self.window, columns=columns, show="tree headings", height=5)
        self.list.heading("#0", text="Index")
        self.list.column("#0", width=260)
        for column in columns:
            self.list.heading(column, text=column.capitalize())
            self.list.column(column, width=100, anchor="center")
        self.list.pack(fill=tk.X, padx=8, pady=4)
        self.list.bind("<<TreeviewSelect>>", lambda _event: self.refresh())
        self.figure = Figure(figsize=(6, 4.5))
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.window)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.refresh()

    def refresh(self):
        if not self.window.winfo_exists():
            return
        monitor = self.app.indices
        names = [definition["name"] for definition in monitor.definitions]
        selected = self.list.selection()
        selected = selected[0] if selected and selected[0] in names else (names[0] if names else None)
        if list(self.list.get_children()) != names:
            self.list.delete(*self.list.get_children())
            for name in names:
                self.list.insert("", tk.END, iid=name, text=name)
        for definition in monitor.definitions:
            value = monitor.compared(definition["name"])
            self.list.item(definition["name"], values=(
                definition["layer"], "-" if value is None else f"{value:.2f}",
                f"{definition['threshold']:g}", monitor.states[definition["name"]]))
        if selected is not None and self.list.selection() != (selected,):
            self.list.selection_set(selected)
        self._draw(next((d for d in monitor.definitions if d["name"] == selected), None))

    def _draw(self, definition):
        self.figure.clear()
        axes = self.figure.add_subplot()
        if definition is None:
            axes.set_title("No indices defined")
        elif definition["layer"] == "map":
            self._draw_map(axes, definition)
        else:
            self._draw_trend(axes, definition)
        self.canvas.draw_idle()

    def _draw_map(self, axes, definition):
        grid = self.app.indices.values[definition["name"]]
        if grid is None:
            axes.set_title(f"{definition['name']}: no pressure data")
            return
        finite = grid[np.isfinite(grid)]
        top = max(definition["threshold"], float(finite.max()) if finite.size else 0.0)
        image = axes.imshow(grid, cmap="viridis", vmin=0, vmax=top, aspect="auto")
        self.figure.colorbar(image, ax=axes, label="Index value")
        if finite.size and finite.min() < definition["threshold"] <= finite.max():
            axes.contour(np.where(np.isfinite(grid), grid, 0.0), levels=[definition["threshold"]],
                         colors="white", linewidths=1.0, linestyles="dashed")
        axes.set_title(f"{definition['name']} (dashed line: threshold {definition['threshold']:g})")

    def _draw_trend(self, axes, definition):
        history = self.app.index_history.get(definition["name"], ())
        if history:
            start = history[0][0]
            axes.plot([time - start for time, _value in history], [value for _time, value in history],
                      color="green")
        threshold = definition["threshold"]
        axes.axhline(threshold, color="#bd5555", linestyle="dashed", label="Threshold")
        axes.axhline(threshold * definition["near_fraction"], color="#e8b04e", linestyle="dotted",
                     label="Near")
        axes.set_ylim(bottom=0)
        axes.set_xlabel("Time (s)")
        axes.set_ylabel("Index value")
        axes.set_title(definition["name"] if history else f"{definition['name']}: no values yet")
        axes.legend(loc="upper left", fontsize=8)
