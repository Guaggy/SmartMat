"""Compact controls and views for pressure-time experiments."""

import tkinter as tk
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from processing.temporal import WINDOWS_MIN

VIEWS = ("Current pressure", "Cumulative exposure", "Experimental burden",
         "Time since full relief", "Relief percentage", "Current relief state")
HISTORY = ("Pressure", "Exposure", "Burden", "Relief state")


class TemporalWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Temporal analysis")
        self.window.geometry("850x760")
        ttk.Label(self.window, text='Shows how long each area of the body has been under pressure, and how long since it last got relief.', wraplength=760, padding=(8, 6)).pack(side=tk.TOP, fill=tk.X)
        controls = ttk.Frame(self.window, padding=8)
        controls.pack(fill=tk.X)
        ttk.Label(controls, text="Map:").pack(side=tk.LEFT)
        self.view_var = tk.StringVar(value=VIEWS[0])
        view = ttk.Combobox(controls, textvariable=self.view_var, values=VIEWS,
                            state="readonly", width=23)
        view.pack(side=tk.LEFT, padx=4)
        view.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Label(controls, text="Window:").pack(side=tk.LEFT, padx=(12, 0))
        self.window_var = tk.StringVar(value="Session")
        window = ttk.Combobox(controls, textvariable=self.window_var, state="readonly",
                              values=["Session"] + [f"{minute} min" for minute in WINDOWS_MIN], width=9)
        window.pack(side=tk.LEFT, padx=4)
        window.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Button(controls, text="Reset exposure", command=self._reset_exposure).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Reset burden", command=self._reset_burden).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Reset all", command=self._reset_all).pack(side=tk.LEFT, padx=4)

        settings = ttk.LabelFrame(self.window, text="Analysis parameters", padding=6)
        settings.pack(fill=tk.X, padx=8)
        self.mode_var = tk.StringVar(value=app.temporal.exposure_mode)
        ttk.Combobox(settings, textvariable=self.mode_var, state="readonly", width=17,
                     values=["Full pressure", "Above threshold"]).grid(row=0, column=0, padx=3)
        parameters = (
            ("Exposure > kPa", "exposure_threshold_kpa"),
            ("Burden load > kPa", "burden_load_threshold_kpa"),
            ("Burden rate", "burden_accumulation_rate"),
            ("Recovery s", "burden_recovery_time_s"),
            ("Partial ratio", "relief_partial_ratio"),
            ("Full ratio", "relief_full_ratio"),
            ("Min relief s", "relief_min_duration_s"),
            ("ROI relief fraction", "roi_relief_fraction"),
        )
        self.parameter_vars = {}
        for index, (label, key) in enumerate(parameters):
            row, column = divmod(index, 4)
            column *= 2
            ttk.Label(settings, text=label).grid(row=row + 1, column=column, padx=3)
            variable = tk.StringVar(value=str(getattr(app.temporal, key)))
            ttk.Entry(settings, textvariable=variable, width=7).grid(row=row + 1, column=column + 1, padx=3)
            self.parameter_vars[key] = variable
        ttk.Button(settings, text="Apply", command=self._apply).grid(row=0, column=1, padx=5)

        self.figure = Figure(figsize=(7, 4))
        self.axes = self.figure.add_subplot()
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.window)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.summary_var = tk.StringVar()
        ttk.Label(self.window, textvariable=self.summary_var, wraplength=820, padding=7).pack(fill=tk.X)

        history_bar = ttk.Frame(self.window, padding=(8, 0))
        history_bar.pack(fill=tk.X)
        ttk.Label(history_bar, text="History:").pack(side=tk.LEFT)
        self.target_var = tk.StringVar(value="Cell")
        target = ttk.Combobox(history_bar, textvariable=self.target_var, values=["Cell", "ROI"],
                              state="readonly", width=6)
        target.pack(side=tk.LEFT, padx=4)
        target.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        self.history_var = tk.StringVar(value=HISTORY[0])
        history = ttk.Combobox(history_bar, textvariable=self.history_var, values=HISTORY,
                               state="readonly", width=15)
        history.pack(side=tk.LEFT, padx=4)
        history.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Button(history_bar, text="Add marker...", command=self._marker).pack(side=tk.RIGHT)
        self.history_figure = Figure(figsize=(7, 1.7))
        self.history_axes = self.history_figure.add_subplot()
        self.history_canvas = FigureCanvasTkAgg(self.history_figure, master=self.window)
        self.history_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.events_var = tk.StringVar()
        ttk.Label(self.window, textvariable=self.events_var, wraplength=820, padding=6).pack(fill=tk.X)
        self.refresh()

    def _minutes(self):
        return None if self.window_var.get() == "Session" else int(self.window_var.get().split()[0])

    def _apply(self):
        try:
            values = {key: float(variable.get()) for key, variable in self.parameter_vars.items()}
            if any(not np.isfinite(value) or value < 0 for value in values.values()):
                raise ValueError("Parameters must be finite and nonnegative")
            if not 0 <= values["relief_full_ratio"] < values["relief_partial_ratio"] < 1:
                raise ValueError("Require 0 ≤ full ratio < partial ratio < 1")
            if not 0 < values["roi_relief_fraction"] <= 1:
                raise ValueError("ROI relief fraction must be within (0, 1]")
            if values["burden_recovery_time_s"] <= 0:
                raise ValueError("Recovery time must be positive")
        except ValueError as error:
            self.app.status_var.set(f"Temporal settings: {error}")
            return
        for key, value in values.items():
            setattr(self.app.temporal, key, value)
        self.app.temporal.exposure_mode = self.mode_var.get()
        self.app.temporal.invalidate()
        if self.app.recorder is not None:
            self.app.add_event("temporal_parameters_changed", payload={
                "temporal": self.app.temporal.settings()})
        self.app.status_var.set("Temporal parameters applied; accumulated values retained")
        self.refresh()

    def _reset_exposure(self):
        self.app.temporal.reset_exposure()
        self.app.add_event("exposure_reset")
        self.refresh()

    def _reset_burden(self):
        self.app.temporal.reset_burden()
        self.app.add_event("burden_reset")
        self.refresh()

    def _reset_all(self):
        self.app.temporal.reset_all()
        self.app.add_event("temporal_reset")
        self.refresh()

    def _marker(self):
        self.app._open_annotation()

    def refresh(self):
        if not self.window.winfo_exists():
            return
        temporal = self.app.temporal
        view = self.view_var.get()
        exposure, _, _ = temporal.rolling(self._minutes())
        pressure = None if self.app.frame is None else self.app.frame["pressure"]
        maps = {
            "Current pressure": (pressure, "kPa"),
            "Cumulative exposure": (exposure, "kPa·min"),
            "Experimental burden": (temporal.burden, "experimental kPa·min"),
            "Time since full relief": (temporal.time_since_relief() / 60, "min"),
            "Relief percentage": (temporal.relief_percent(self._minutes()), "% valid time"),
            "Current relief state": (temporal.state, "0 unknown · 1 loaded · 2 partial · 3 full"),
        }
        grid, unit = maps[view]
        self.figure.clear()
        self.axes = self.figure.add_subplot()
        if grid is None:
            grid = np.full_like(temporal.exposure, np.nan)
            self.summary_var.set("Calibrated pressure required for temporal analysis")
        else:
            self._summary()
            if pressure is None:
                self.summary_var.set("Calibrated pressure required; accumulated values shown from earlier valid samples")
        image = self.axes.imshow(grid, cmap="viridis", aspect="auto", vmin=0,
                                 vmax=3 if view == "Current relief state" else None)
        self.figure.colorbar(image, ax=self.axes, label=unit)
        self.axes.set_title(view + (" (" + self.window_var.get() + ")" if view == "Cumulative exposure" else ""))
        self.axes.set_xlabel("Column")
        self.axes.set_ylabel("Row")
        self.figure.tight_layout()
        self.canvas.draw_idle()
        self._history()
        recent = self.app.timeline.events[-3:]
        self.events_var.set("Recent events: " + " | ".join(
            f"{event['kind']} {event['note']}" for event in recent))

    def _summary(self):
        temporal = self.app.temporal
        parts = [f"Valid intervals {temporal.valid_intervals}; skipped gaps {temporal.skipped_intervals}"]
        if self.app.selected_cell is not None:
            row, col = self.app.selected_cell
            cell = temporal.cell(row, col)
            parts.append(f"Cell ({row},{col}): exposure {cell['exposure']:.2f} kPa·min, "
                         f"burden {cell['burden']:.2f}, {cell['state']}, "
                         f"since relief {cell['since_relief_s'] / 60:.1f} min, "
                         f"current relief {cell['current_relief_s'] / 60:.1f} min, "
                         f"loaded {cell['loaded_s'] / 60:.1f} min, relieved {cell['relieved_s'] / 60:.1f} min, "
                         f"relieved {cell['relief_percent']:.0f}%")
        if self.app.roi is not None:
            roi = temporal.roi(self.app.roi)
            parts.append(f"ROI: exposure mean/max {roi['mean_exposure']:.2f}/{roi['max_exposure']:.2f} kPa·min, "
                         f"burden mean/max {roi['mean_burden']:.2f}/{roi['max_burden']:.2f}, "
                         f"valid {100 * roi['valid_fraction']:.0f}%, loaded {100 * roi['loaded_fraction']:.0f}%, "
                         f"relieved {100 * roi['relieved_fraction']:.0f}%, "
                         f"since relief {roi['since_relief_s'] / 60:.1f} min")
        self.summary_var.set("\n".join(parts))

    def _history(self):
        metric = self.history_var.get()
        key = {"Pressure": "pressure", "Exposure": "exposure",
               "Burden": "burden", "Relief state": "relief_state"}[metric]
        self.history_axes.clear()
        if self.target_var.get() == "Cell" and self.app.selected_cell is not None:
            samples = [sample for sample in self.app.cell_history if sample.get(key) is not None]
            title = "Selected cell"
        else:
            roi_key = {"pressure": "pressure_mean", "exposure": "exposure_mean",
                       "burden": "burden_mean", "relief_state": "relieved_fraction"}[key]
            samples = [sample for sample in self.app.roi_history if sample.get(roi_key) is not None]
            key = roi_key
            title = "Selected ROI"
        if samples:
            start = samples[0]["time"]
            self.history_axes.plot([sample["time"] - start for sample in samples],
                                   [sample[key] for sample in samples], color="green")
        self.history_axes.set_title(f"{title}: {metric}")
        self.history_axes.set_xlabel("Time since selection (s)")
        self.history_figure.tight_layout()
        self.history_canvas.draw_idle()
