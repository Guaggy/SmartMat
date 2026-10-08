"""Small editor for pressure calibration: per-sensor (Individual) and whole-mat (Uniform)."""

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import ListedColormap
from matplotlib.figure import Figure

import config
from config import CELL_WIDTH_MM, CELL_HEIGHT_MM

# muted tones: this gets looked at for a long time
UNCALIBRATED_COLOR = "#a86a6a"
CALIBRATED_COLOR = "#6f9a76"
MINIGRID_COLORS = ListedColormap([UNCALIBRATED_COLOR, CALIBRATED_COLOR])


def _when(profile, exists):
    """'last changed ...' text for a profile, from its modified_at timestamp"""
    if not exists:
        return "none yet"
    if profile.modified_at is None:
        return "exists, date unknown"
    return "last changed " + datetime.fromtimestamp(profile.modified_at).strftime("%Y-%m-%d %H:%M")


class CalibrationWindow:
    def __init__(self, parent, calibration, raw_grid_getter, on_change):
        self.calibration = calibration  # PressureCalibration holding both profiles
        self.individual = calibration.individual
        self.uniform = calibration.uniform
        self.raw_grid_getter = raw_grid_getter
        self.on_change = on_change
        self.window = tk.Toplevel(parent)
        self.window.title("Pressure calibration")
        self.window.geometry("760x860")
        ttk.Label(self.window, text='Teaches the mat what each sensor reading means in kPa. Needed before pressure values and hotspots can be trusted.', wraplength=760, padding=(8, 6)).pack(side=tk.TOP, fill=tk.X)

        notebook = ttk.Notebook(self.window)
        notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))
        individual = ttk.Frame(notebook)
        whole_grid = ttk.Frame(notebook)
        notebook.add(individual, text="Individual cell")
        notebook.add(whole_grid, text="Whole grid")

        self.row_var = tk.IntVar(value=0)
        self.col_var = tk.IntVar(value=0)
        self.raw_var = tk.StringVar(value="Current value: -")
        self.offset_var = tk.StringVar(value="0")
        self.pressure_var = tk.StringVar()
        self.input_unit_var = tk.StringVar(value="kPa")
        self.model_var = tk.StringVar(value="linear")
        self.individual_date_var = tk.StringVar()
        self.bulk_offset_var = tk.StringVar(value="0")
        self.bulk_pressure_var = tk.StringVar()
        self.bulk_unit_var = tk.StringVar(value="kPa")
        self.bulk_model_var = tk.StringVar(value="linear")
        self.grid_raw_var = tk.StringVar(value="Current grid: -")
        self.uniform_status_var = tk.StringVar()
        self.uniform_offset_var = tk.StringVar(value="0")
        self.uniform_pressure_var = tk.StringVar()
        self.uniform_unit_var = tk.StringVar(value="kPa")
        self.uniform_model_var = tk.StringVar(value="linear")
        self.active_var = tk.StringVar()
        self.status_var = tk.StringVar()

        # ---- Individual tab: controls on the left, calibrated/uncalibrated mini-grid top right
        top = ttk.Frame(individual, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)
        side = ttk.Frame(top)
        side.pack(side=tk.RIGHT, anchor="n")
        self.mini_figure = Figure(figsize=(1.9, 2.0))
        self.mini_axes = self.mini_figure.add_subplot()
        self.mini_canvas = FigureCanvasTkAgg(self.mini_figure, master=side)
        self.mini_canvas.get_tk_widget().pack()
        self.mini_canvas.mpl_connect("button_press_event", self._on_minigrid_click)
        ttk.Label(side, text="green = calibrated, red = not yet\n(click a cell to select it)",
                  justify=tk.CENTER).pack()
        ttk.Label(side, textvariable=self.individual_date_var, justify=tk.CENTER).pack(pady=(4, 0))

        controls = ttk.Frame(top)
        controls.pack(side=tk.LEFT, fill=tk.X)
        ttk.Label(controls, text="Row:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(controls, from_=0, to=config.TOTAL_ROWS - 1, textvariable=self.row_var,
                    width=5, command=self._select_cell).grid(row=0, column=1, sticky="w")
        ttk.Label(controls, text="Column:").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Spinbox(controls, from_=0, to=config.TOTAL_COLS - 1, textvariable=self.col_var,
                    width=5, command=self._select_cell).grid(row=0, column=3, sticky="w")
        ttk.Label(controls, textvariable=self.raw_var).grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.row_var.trace_add("write", lambda *_: self._select_cell())
        self.col_var.trace_add("write", lambda *_: self._select_cell())

        ttk.Label(controls, text="Sensor offset:").grid(row=2, column=0, sticky="w", pady=8)
        ttk.Entry(controls, textvariable=self.offset_var, width=10).grid(row=2, column=1, sticky="w")
        ttk.Button(controls, text="Set offset", command=self._set_offset).grid(row=2, column=2, sticky="w")
        ttk.Button(controls, text="Use current value", command=self._capture_offset).grid(row=2, column=3, sticky="w")

        ttk.Label(controls, text="Known value:").grid(row=3, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.pressure_var, width=10).grid(row=3, column=1, sticky="w")
        ttk.Combobox(controls, textvariable=self.input_unit_var, state="readonly",
                     values=["kPa", "N"], width=5).grid(row=3, column=2, sticky="w")
        ttk.Button(controls, text="Add point at current value", command=self._add_point).grid(
            row=3, column=3, sticky="w")

        ttk.Label(controls, text="Model:").grid(row=4, column=0, sticky="w", pady=8)
        model_menu = ttk.Combobox(controls, textvariable=self.model_var, state="readonly",
                                  values=["linear", "piecewise"], width=10)
        model_menu.grid(row=4, column=1, sticky="w")
        model_menu.bind("<<ComboboxSelected>>", lambda _event: self._update_model())
        ttk.Button(controls, text="Update curve", command=self._update_model).grid(row=4, column=2, sticky="w")
        ttk.Button(controls, text="Copy cell curve to all", command=self._copy_all).grid(
            row=4, column=3, sticky="w")

        self.points_list = tk.Listbox(individual, height=4)
        self.points_list.pack(fill=tk.X, padx=10)
        ttk.Button(individual, text="Remove selected point", command=self._remove_point).pack(
            anchor="w", padx=10, pady=4)

        bulk = ttk.LabelFrame(individual, text="Bulk actions on all individual cells", padding=6)
        bulk.pack(fill=tk.X, padx=10, pady=4)
        ttk.Label(bulk, text="Same offset:").grid(row=0, column=0, sticky="w")
        ttk.Entry(bulk, textvariable=self.bulk_offset_var, width=8).grid(row=0, column=1, sticky="w")
        ttk.Button(bulk, text="Set all offsets", command=self._set_all_offsets).grid(row=0, column=2, padx=4)
        ttk.Button(bulk, text="Capture each cell's current value as zero",
                   command=self._capture_all_offsets).grid(row=0, column=3, padx=4)
        ttk.Label(bulk, text="Uniform kPa / total N:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(bulk, textvariable=self.bulk_pressure_var, width=8).grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Combobox(bulk, textvariable=self.bulk_unit_var, state="readonly",
                     values=["kPa", "N"], width=5).grid(row=1, column=2, padx=4, pady=(6, 0))
        ttk.Button(bulk, text="Add point to every cell from current grid",
                   command=self._add_grid_point).grid(row=1, column=3, padx=4, pady=(6, 0))
        ttk.Label(bulk, text="Model for all cells:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(bulk, textvariable=self.bulk_model_var, state="readonly",
                     values=["linear", "piecewise"], width=10).grid(row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Button(bulk, text="Apply model to all", command=self._update_all_models).grid(
            row=2, column=2, padx=4, pady=(6, 0))

        self.figure = Figure(figsize=(5, 2.6))
        self.axes = self.figure.add_subplot()
        self.canvas = FigureCanvasTkAgg(self.figure, master=individual)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10)

        # ---- Whole grid tab: the Uniform profile (one curve for the entire mat)
        panel = ttk.Frame(whole_grid, padding=12)
        panel.pack(fill=tk.BOTH, expand=True)
        ttk.Label(panel, text=("One shared curve for the whole mat. A capture uses the average "
                               "of all sensor values, so apply the same known pressure to the full mat."),
                  wraplength=700).pack(anchor="w")
        ttk.Label(panel, textvariable=self.uniform_status_var,
                  font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(8, 2))
        ttk.Label(panel, textvariable=self.grid_raw_var).pack(anchor="w", pady=(0, 6))

        row = ttk.Frame(panel)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="Offset:").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.uniform_offset_var, width=10).pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="Set offset", command=self._uniform_set_offset).pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="Use current grid mean as zero",
                   command=self._uniform_capture_offset).pack(side=tk.LEFT, padx=4)
        row = ttk.Frame(panel)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="Known kPa / total N:").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.uniform_pressure_var, width=10).pack(side=tk.LEFT, padx=4)
        ttk.Combobox(row, textvariable=self.uniform_unit_var, state="readonly",
                     values=["kPa", "N"], width=5).pack(side=tk.LEFT)
        ttk.Button(row, text="Add point at current grid mean",
                   command=self._uniform_add_point).pack(side=tk.LEFT, padx=8)
        row = ttk.Frame(panel)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="Model:").pack(side=tk.LEFT)
        uniform_model = ttk.Combobox(row, textvariable=self.uniform_model_var, state="readonly",
                                     values=["linear", "piecewise"], width=10)
        uniform_model.pack(side=tk.LEFT, padx=4)
        uniform_model.bind("<<ComboboxSelected>>", lambda _event: self._uniform_update_model())
        ttk.Button(row, text="Update curve", command=self._uniform_update_model).pack(side=tk.LEFT, padx=4)

        self.uniform_points = tk.Listbox(panel, height=4)
        self.uniform_points.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(panel, text="Remove selected point", command=self._uniform_remove_point).pack(
            anchor="w", pady=4)
        self.uniform_figure = Figure(figsize=(5, 3))
        self.uniform_axes = self.uniform_figure.add_subplot()
        self.uniform_canvas = FigureCanvasTkAgg(self.uniform_figure, master=panel)
        self.uniform_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # ---- bottom: profile switch and save/load
        switch = ttk.Frame(self.window, padding=(10, 8, 10, 0))
        switch.pack(fill=tk.X)
        ttk.Button(switch, text="Use individual calibration",
                   command=lambda: self._use_profile("individual")).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(switch, text="Use uniform calibration",
                   command=lambda: self._use_profile("uniform")).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(switch, textvariable=self.active_var, font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT)
        buttons = ttk.Frame(self.window, padding=10)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Save calibration...", command=self._save).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Load calibration...", command=self._load).pack(side=tk.LEFT)
        ttk.Label(buttons, textvariable=self.status_var).pack(side=tk.LEFT, padx=12)

        self._refresh_all()
        self._refresh_raw()

    # ---- shared helpers

    def _cell(self):
        row, col = self.row_var.get(), self.col_var.get()
        if not (0 <= row < config.TOTAL_ROWS and 0 <= col < config.TOTAL_COLS):
            raise ValueError("Choose a valid sensor row and column")
        return row, col

    def _current_raw(self):
        return float(self._current_grid()[self._cell()])

    def _current_grid(self):
        grid = self.raw_grid_getter()
        if grid is None:
            raise ValueError("Connect a data source before capturing a reading")
        return np.asarray(grid, dtype=float)

    def _refresh_raw(self):
        if not self.window.winfo_exists():
            return
        try:
            grid = self._current_grid()
            self.raw_var.set(f"Current value: {float(grid[self._cell()]):.1f}")
            finite = grid[np.isfinite(grid)]
            if finite.size:
                self.grid_raw_var.set(
                    f"Current grid: mean {finite.mean():.1f}, min {finite.min():.1f}, max {finite.max():.1f}")
            else:
                self.grid_raw_var.set("Current grid: no valid values")
        except (ValueError, tk.TclError):
            self.raw_var.set("Current value: -")
            self.grid_raw_var.set("Current grid: -")
        self.window.after(200, self._refresh_raw)

    def _fail(self, error):
        messagebox.showerror("Pressure calibration", str(error), parent=self.window)

    @staticmethod
    def _pressure_kpa(value, unit, cell_count=1):
        pressure = float(value)
        if unit == "N":
            if not CELL_WIDTH_MM or not CELL_HEIGHT_MM or CELL_WIDTH_MM <= 0 or CELL_HEIGHT_MM <= 0:
                raise ValueError("Set positive cell dimensions in config.py to use newtons")
            pressure = pressure * 1000 / (CELL_WIDTH_MM * CELL_HEIGHT_MM * cell_count)
        return pressure

    def _refresh_all(self):
        self._select_cell()
        self._refresh_uniform()
        names = {"individual": "Individual", "uniform": "Uniform"}
        self.active_var.set(f"Active: {names[self.calibration.active_name]}")
        self.status_var.set(f"{self.calibration.calibrated_count}/{config.TOTAL_ROWS * config.TOTAL_COLS} cells calibrated (active)")

    def _changed(self, kind="calibration_changed"):
        self.on_change(kind)
        self._refresh_all()

    def _use_profile(self, name):
        self.calibration.use(name)
        self._changed()

    # ---- Individual tab

    def _select_cell(self):
        try:
            row, col = self._cell()
        except (ValueError, tk.TclError):
            return
        cell = self.individual.get_cell(row, col)
        self.offset_var.set(str(cell["offset"]))
        self.model_var.set(cell["model"])
        self.points_list.delete(0, tk.END)
        for raw, pressure in cell["points"]:
            self.points_list.insert(tk.END, f"Value {raw:.2f}  ->  {pressure:.2f} kPa")
        self.individual_date_var.set("Individual calibration:\n" + _when(
            self.individual, self.individual.calibrated_count > 0))
        self._draw_curve()
        self._draw_minigrid()
        self._draw_uniform_curve()  # keeps the selected-cell overlay in step

    def _draw_minigrid(self):
        calibrated = np.array([[self.individual.is_calibrated(r, c) for c in range(config.TOTAL_COLS)]
                               for r in range(config.TOTAL_ROWS)], dtype=int)
        self.mini_axes.clear()
        self.mini_axes.imshow(calibrated, cmap=MINIGRID_COLORS, vmin=0, vmax=1, aspect="equal")
        row, col = self._cell()
        self.mini_axes.plot(col, row, marker="s", markersize=6, fillstyle="none",
                            color="#222222", linestyle="None")
        self.mini_axes.set_xticks([])
        self.mini_axes.set_yticks([])
        self.mini_figure.tight_layout(pad=0.3)
        self.mini_canvas.draw_idle()

    def _on_minigrid_click(self, event):
        if event.inaxes != self.mini_axes or event.xdata is None or event.ydata is None:
            return
        row, col = round(event.ydata), round(event.xdata)
        if 0 <= row < config.TOTAL_ROWS and 0 <= col < config.TOTAL_COLS:
            self.row_var.set(row)
            self.col_var.set(col)

    def _set_offset(self):
        try:
            self.individual.set_offset(*self._cell(), float(self.offset_var.get()))
            self._changed()
        except ValueError as error:
            self._fail(error)

    def _capture_offset(self):
        try:
            self.individual.set_offset(*self._cell(), self._current_raw())
            self._changed()
        except ValueError as error:
            self._fail(error)

    def _add_point(self):
        try:
            pressure = self._pressure_kpa(self.pressure_var.get(), self.input_unit_var.get())
            self.individual.add_point(*self._cell(), self._current_raw(), pressure)
            self._changed()
        except ValueError as error:
            self._fail(error)

    def _set_all_offsets(self):
        try:
            self.individual.set_all_offsets(float(self.bulk_offset_var.get()))
            self._changed()
        except ValueError as error:
            self._fail(error)

    def _capture_all_offsets(self):
        try:
            self.individual.capture_offsets(self._current_grid())
            self._changed()
        except ValueError as error:
            self._fail(error)

    def _add_grid_point(self):
        try:
            pressure = self._pressure_kpa(
                self.bulk_pressure_var.get(), self.bulk_unit_var.get(), config.TOTAL_ROWS * config.TOTAL_COLS)
            self.individual.add_grid_point(self._current_grid(), pressure)
            self._changed()
        except ValueError as error:
            self._fail(error)

    def _update_all_models(self):
        try:
            self.individual.set_model_all(self.bulk_model_var.get())
            self._changed()
        except ValueError as error:
            self._fail(error)

    def _remove_point(self):
        selection = self.points_list.curselection()
        if selection:
            self.individual.remove_point(*self._cell(), selection[0])
            self._changed()

    def _update_model(self):
        self.individual.set_model(*self._cell(), self.model_var.get())
        self._changed()

    def _copy_all(self):
        if not messagebox.askyesno("Pressure calibration", "Replace every cell's calibration with this curve?",
                                   parent=self.window):
            return
        try:
            self.individual.copy_cell_to_all(*self._cell())
            self._changed()
        except ValueError as error:
            self._fail(error)

    def _draw_curve(self):
        self.axes.clear()
        row, col = self._cell()
        cell = self.individual.get_cell(row, col)
        points = cell["points"]
        if points:
            self.axes.scatter([point[0] for point in points],
                              [point[1] for point in points], color="red")
        if self.individual.is_calibrated(row, col):
            upper = max([cell["offset"] + 1] + [point[0] for point in points])
            values = np.linspace(cell["offset"], upper, 100)
            pressures = [self.individual.convert_cell(row, col, value) for value in values]
            self.axes.plot(values, pressures, color="green")
        self.axes.set_title(f"Cell ({row}, {col})")
        self.axes.set_xlabel("Received sensor value")
        self.axes.set_ylabel("Pressure (kPa)")
        self.figure.tight_layout()
        self.canvas.draw_idle()

    # ---- Whole grid tab (Uniform profile)

    def _refresh_uniform(self):
        curve = self.uniform.get_curve()
        self.uniform_status_var.set("Uniform calibration: " + _when(self.uniform, self.uniform.exists))
        self.uniform_offset_var.set(str(curve["offset"]))
        self.uniform_model_var.set(curve["model"])
        self.uniform_points.delete(0, tk.END)
        for raw, pressure in curve["points"]:
            self.uniform_points.insert(tk.END, f"Grid mean {raw:.2f}  ->  {pressure:.2f} kPa")
        self._draw_uniform_curve()

    def _draw_uniform_curve(self):
        axes = self.uniform_axes
        axes.clear()
        curve = self.uniform.get_curve()
        points = curve["points"]
        try:
            row, col = self._cell()
            cell = self.individual.get_cell(row, col)
        except (ValueError, tk.TclError):
            cell = None
        highest = max([curve["offset"] + 1] + [point[0] for point in points]
                      + ([cell["offset"] + 1] + [point[0] for point in cell["points"]] if cell else []))
        lowest = min([curve["offset"]] + ([cell["offset"]] if cell else []))
        values = np.linspace(lowest, highest, 100)
        if cell is not None and self.individual.is_calibrated(row, col):
            axes.plot(values, [self.individual.convert_cell(row, col, v) for v in values],
                      color="gray", linestyle="--", label=f"cell ({row}, {col})")
        if points:
            axes.scatter([point[0] for point in points], [point[1] for point in points], color="red")
        if self.uniform.exists:
            axes.plot(values, [self.uniform.convert(v) for v in values], color="green", label="whole grid")
        if axes.get_legend_handles_labels()[0]:
            axes.legend(loc="upper left")
        axes.set_title("Whole-grid curve (selected cell dashed for comparison)")
        axes.set_xlabel("Received sensor value")
        axes.set_ylabel("Pressure (kPa)")
        self.uniform_figure.tight_layout()
        self.uniform_canvas.draw_idle()

    def _uniform_set_offset(self):
        try:
            self.uniform.set_offset(float(self.uniform_offset_var.get()))
            self._changed()
        except ValueError as error:
            self._fail(error)

    def _uniform_capture_offset(self):
        try:
            self.uniform.capture_offset(self._current_grid())
            self._changed()
        except ValueError as error:
            self._fail(error)

    def _uniform_add_point(self):
        try:
            pressure = self._pressure_kpa(self.uniform_pressure_var.get(), self.uniform_unit_var.get(),
                                          config.TOTAL_ROWS * config.TOTAL_COLS)
            self.uniform.add_grid_point(self._current_grid(), pressure)
            self._changed()
        except ValueError as error:
            self._fail(error)

    def _uniform_update_model(self):
        try:
            self.uniform.set_model(self.uniform_model_var.get())
            self._changed()
        except ValueError as error:
            self._fail(error)

    def _uniform_remove_point(self):
        selection = self.uniform_points.curselection()
        if selection:
            self.uniform.remove_point(selection[0])
            self._changed()

    # ---- save / load (acts on the active profile; each profile has its own file format)

    def _save(self):
        name = self.calibration.active_name
        path = filedialog.asksaveasfilename(
            parent=self.window, defaultextension=".json",
            initialfile=("uniform_pressure_calibration.json" if name == "uniform"
                         else "pressure_calibration.json"),
            filetypes=[("JSON calibration", "*.json")])
        if path:
            try:
                self.calibration.save(path)
                self.status_var.set(f"Saved {name} calibration to {Path(path).name}")
            except OSError as error:
                self._fail(error)

    def _load(self):
        path = filedialog.askopenfilename(parent=self.window,
                                          filetypes=[("JSON calibration", "*.json")])
        if path:
            try:
                before = self.calibration.active_name
                self.calibration.load(path)
                self._changed("calibration_loaded")
                after = self.calibration.active_name
                note = "" if before == after else f" ({after} profile, now active)"
                self.status_var.set(f"Loaded {Path(path).name}{note}")
            except (OSError, ValueError, KeyError, TypeError) as error:
                self._fail(error)
