"""Small editor for per-sensor pressure calibration."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from config import TOTAL_ROWS, TOTAL_COLS, CELL_WIDTH_MM, CELL_HEIGHT_MM


class CalibrationWindow:
    def __init__(self, parent, calibration, raw_grid_getter, on_change):
        self.calibration = calibration
        self.raw_grid_getter = raw_grid_getter
        self.on_change = on_change
        self.window = tk.Toplevel(parent)
        self.window.title("Pressure calibration")
        self.window.geometry("660x620")

        controls = ttk.Frame(self.window, padding=10)
        controls.pack(side=tk.TOP, fill=tk.X)

        self.row_var = tk.IntVar(value=0)
        self.col_var = tk.IntVar(value=0)
        self.raw_var = tk.StringVar(value="Current raw: -")
        self.offset_var = tk.StringVar(value="0")
        self.pressure_var = tk.StringVar()
        self.input_unit_var = tk.StringVar(value="kPa")
        self.model_var = tk.StringVar(value="linear")
        self.status_var = tk.StringVar()

        ttk.Label(controls, text="Row:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(controls, from_=0, to=TOTAL_ROWS - 1, textvariable=self.row_var,
                    width=5, command=self._select_cell).grid(row=0, column=1, sticky="w")
        ttk.Label(controls, text="Column:").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Spinbox(controls, from_=0, to=TOTAL_COLS - 1, textvariable=self.col_var,
                    width=5, command=self._select_cell).grid(row=0, column=3, sticky="w")
        ttk.Label(controls, textvariable=self.raw_var).grid(row=0, column=4, sticky="w", padx=12)
        self.row_var.trace_add("write", lambda *_: self._select_cell())
        self.col_var.trace_add("write", lambda *_: self._select_cell())

        ttk.Label(controls, text="Sensor offset:").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(controls, textvariable=self.offset_var, width=10).grid(row=1, column=1, sticky="w")
        ttk.Button(controls, text="Set offset", command=self._set_offset).grid(row=1, column=2, sticky="w")
        ttk.Button(controls, text="Use current raw", command=self._capture_offset).grid(row=1, column=3, columnspan=2, sticky="w")

        ttk.Label(controls, text="Known value:").grid(row=2, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.pressure_var, width=10).grid(row=2, column=1, sticky="w")
        ttk.Combobox(controls, textvariable=self.input_unit_var, state="readonly",
                     values=["kPa", "N"], width=5).grid(row=2, column=2, sticky="w")
        ttk.Button(controls, text="Add point at current raw", command=self._add_point).grid(
            row=2, column=3, columnspan=2, sticky="w")

        ttk.Label(controls, text="Model:").grid(row=3, column=0, sticky="w", pady=8)
        model_menu = ttk.Combobox(controls, textvariable=self.model_var, state="readonly",
                                  values=["linear", "piecewise"], width=10)
        model_menu.grid(row=3, column=1, sticky="w")
        model_menu.bind("<<ComboboxSelected>>", lambda _event: self._update_model())
        ttk.Button(controls, text="Update curve", command=self._update_model).grid(row=3, column=2, sticky="w")
        ttk.Button(controls, text="Copy cell curve to all", command=self._copy_all).grid(
            row=3, column=3, columnspan=2, sticky="w")

        self.points_list = tk.Listbox(self.window, height=5)
        self.points_list.pack(fill=tk.X, padx=10)
        ttk.Button(self.window, text="Remove selected point", command=self._remove_point).pack(anchor="w", padx=10, pady=4)

        self.figure = Figure(figsize=(5, 3))
        self.axes = self.figure.add_subplot()
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.window)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10)

        buttons = ttk.Frame(self.window, padding=10)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Save calibration...", command=self._save).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Load calibration...", command=self._load).pack(side=tk.LEFT)
        ttk.Label(buttons, textvariable=self.status_var).pack(side=tk.LEFT, padx=12)

        self._select_cell()
        self._refresh_raw()

    def _cell(self):
        row, col = self.row_var.get(), self.col_var.get()
        if not (0 <= row < TOTAL_ROWS and 0 <= col < TOTAL_COLS):
            raise ValueError("Choose a valid sensor row and column")
        return row, col

    def _current_raw(self):
        grid = self.raw_grid_getter()
        if grid is None:
            raise ValueError("Connect a data source before capturing a reading")
        return float(grid[self._cell()])

    def _refresh_raw(self):
        if not self.window.winfo_exists():
            return
        try:
            self.raw_var.set(f"Current raw: {self._current_raw():.1f}")
        except (ValueError, tk.TclError):
            self.raw_var.set("Current raw: -")
        self.window.after(200, self._refresh_raw)

    def _select_cell(self):
        try:
            row, col = self._cell()
        except (ValueError, tk.TclError):
            return
        cell = self.calibration.get_cell(row, col)
        self.offset_var.set(str(cell["offset"]))
        self.model_var.set(cell["model"])
        self.points_list.delete(0, tk.END)
        for raw, pressure in cell["points"]:
            self.points_list.insert(tk.END, f"Raw {raw:.2f}  ->  {pressure:.2f} kPa")
        self._draw_curve()

    def _changed(self, kind="calibration_changed"):
        self.on_change(kind)
        self._select_cell()
        self.status_var.set(f"{self.calibration.calibrated_count}/{TOTAL_ROWS * TOTAL_COLS} cells calibrated")

    def _set_offset(self):
        try:
            self.calibration.set_offset(*self._cell(), float(self.offset_var.get()))
            self._changed()
        except ValueError as error:
            messagebox.showerror("Pressure calibration", str(error), parent=self.window)

    def _capture_offset(self):
        try:
            self.calibration.set_offset(*self._cell(), self._current_raw())
            self._changed()
        except ValueError as error:
            messagebox.showerror("Pressure calibration", str(error), parent=self.window)

    def _add_point(self):
        try:
            pressure = float(self.pressure_var.get())
            if self.input_unit_var.get() == "N":
                if not CELL_WIDTH_MM or not CELL_HEIGHT_MM or CELL_WIDTH_MM <= 0 or CELL_HEIGHT_MM <= 0:
                    raise ValueError("Set positive cell dimensions in config.py to use newtons")
                pressure = pressure * 1000 / (CELL_WIDTH_MM * CELL_HEIGHT_MM)
            self.calibration.add_point(*self._cell(), self._current_raw(), pressure)
            self._changed()
        except ValueError as error:
            messagebox.showerror("Pressure calibration", str(error), parent=self.window)

    def _remove_point(self):
        selection = self.points_list.curselection()
        if selection:
            self.calibration.remove_point(*self._cell(), selection[0])
            self._changed()

    def _update_model(self):
        self.calibration.set_model(*self._cell(), self.model_var.get())
        self._changed()

    def _copy_all(self):
        if not messagebox.askyesno("Pressure calibration", "Replace every cell's calibration with this curve?",
                                   parent=self.window):
            return
        try:
            self.calibration.copy_cell_to_all(*self._cell())
            self._changed()
        except ValueError as error:
            messagebox.showerror("Pressure calibration", str(error), parent=self.window)

    def _draw_curve(self):
        self.axes.clear()
        row, col = self._cell()
        cell = self.calibration.get_cell(row, col)
        points = cell["points"]
        if points:
            self.axes.scatter([point[0] for point in points],
                              [point[1] for point in points], color="red")
        if self.calibration.is_calibrated(row, col):
            upper = max([cell["offset"] + 1] + [point[0] for point in points])
            values = np.linspace(cell["offset"], upper, 100)
            pressures = [self.calibration.convert_cell(row, col, value) for value in values]
            self.axes.plot(values, pressures, color="green")
        self.axes.set_xlabel("Received sensor value")
        self.axes.set_ylabel("Pressure (kPa)")
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def _save(self):
        path = filedialog.asksaveasfilename(parent=self.window, defaultextension=".json",
                                            initialfile="pressure_calibration.json",
                                            filetypes=[("JSON calibration", "*.json")])
        if path:
            try:
                self.calibration.save(path)
                self.status_var.set(f"Saved {Path(path).name}")
            except OSError as error:
                messagebox.showerror("Pressure calibration", str(error), parent=self.window)

    def _load(self):
        path = filedialog.askopenfilename(parent=self.window,
                                          filetypes=[("JSON calibration", "*.json")])
        if path:
            try:
                self.calibration.load(path)
                self._changed("calibration_loaded")
                self.status_var.set(f"Loaded {Path(path).name}")
            except (OSError, ValueError, KeyError, TypeError) as error:
                messagebox.showerror("Pressure calibration", str(error), parent=self.window)
