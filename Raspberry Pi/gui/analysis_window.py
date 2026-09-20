"""ROI and pressure-distribution plots kept off the main dashboard."""

import tkinter as tk
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from processing.analysis import load_distribution, pressure_distribution, roi_statistics


def _number(value, suffix=""):
    return "-" if value is None else f"{value:.2f}{suffix}"


class AnalysisWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("SMARTMAT analysis")
        self.window.geometry("950x700")

        bar = ttk.Frame(self.window, padding=8)
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="Select ROI: two corners", command=app._begin_roi_selection).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bar, text="Clear ROI", command=app._clear_roi).pack(side=tk.LEFT)

        self.tabs = ttk.Notebook(self.window)
        self.tabs.pack(fill=tk.BOTH, expand=True)
        roi_tab = ttk.Frame(self.tabs)
        distribution_tab = ttk.Frame(self.tabs)
        load_tab = ttk.Frame(self.tabs)
        self.tabs.add(roi_tab, text="ROI")
        self.tabs.add(distribution_tab, text="Distribution")
        self.tabs.add(load_tab, text="Load and symmetry")
        self.tabs.bind("<<NotebookTabChanged>>", lambda _event: self.refresh())

        self.roi_text = tk.StringVar()
        ttk.Label(roi_tab, textvariable=self.roi_text, padding=8, wraplength=900).pack(fill=tk.X)
        self.roi_figure = Figure(figsize=(8, 4))
        self.roi_canvas = FigureCanvasTkAgg(self.roi_figure, master=roi_tab)
        self.roi_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.distribution_text = tk.StringVar()
        ttk.Label(distribution_tab, textvariable=self.distribution_text, padding=8).pack(fill=tk.X)
        self.distribution_figure = Figure(figsize=(9, 5))
        self.distribution_canvas = FigureCanvasTkAgg(self.distribution_figure, master=distribution_tab)
        self.distribution_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.load_text = tk.StringVar()
        ttk.Label(load_tab, textvariable=self.load_text, padding=15, justify=tk.LEFT).pack(anchor="w")
        self.refresh()

    def refresh(self):
        if not self.window.winfo_exists():
            return
        tab = self.tabs.index("current")
        if tab == 0:
            self._refresh_roi()
        elif tab == 1:
            self._refresh_distribution()
        else:
            self._refresh_load()

    def _refresh_roi(self):
        self.roi_figure.clear()
        axes = self.roi_figure.add_subplot()
        if self.app.roi is None or self.app.frame is None:
            self.roi_text.set("Choose two cells on the 2D heatmap to select a rectangular ROI.")
        else:
            grid, unit = self.app._analysis_grid()
            stats = roi_statistics(grid, self.app.roi, unit, self.app.contact_threshold_kpa,
                                   self.app.cell_area_m2)
            row0, row1, col0, col1 = self.app.roi
            area = _number(stats["area_m2"] * 10_000, " cm²") if stats["area_m2"] is not None else "not configured"
            contact = str(stats["contact_cells"]) if stats["contact_cells"] is not None else "requires kPa"
            contact_area = _number(stats["contact_area_m2"] * 10_000, " cm²") if stats["contact_area_m2"] is not None else "-"
            center = (f"x={stats['center_x']:.1f}, y={stats['center_y']:.1f}"
                      if stats["center_x"] is not None else "-")
            self.roi_text.set(
                f"Rows {row0}-{row1}, cols {col0}-{col1} | {stats['sensors']} sensors | ROI area {area}\n"
                f"Mean {_number(stats['mean'], ' ' + unit)} | peak {_number(stats['peak'], ' ' + unit)} | "
                f"min {_number(stats['minimum'], ' ' + unit)} | std {_number(stats['std'], ' ' + unit)}\n"
                f"Force {_number(stats['force_n'], ' N')} | contact {contact} cells ({contact_area}) | "
                f"{'CoP' if unit == 'kPa' else 'Signal center'} {center}"
            )
            if self.app.roi_history:
                start = self.app.roi_history[0]["time"]
                times = [item["time"] - start for item in self.app.roi_history]
                axes.plot(times, [item["mean"] for item in self.app.roi_history], label="Mean")
                axes.plot(times, [item["peak"] for item in self.app.roi_history], label="Peak")
                axes.legend()
            axes.set_ylabel(unit)
        axes.set_xlabel("Time since ROI selection (s)")
        self.roi_figure.tight_layout()
        self.roi_canvas.draw_idle()

    def _refresh_distribution(self):
        self.distribution_figure.clear()
        pressure = None if self.app.frame is None else self.app.frame["pressure"]
        if pressure is None:
            self.distribution_text.set("Complete pressure calibration is required for distribution analysis.")
        else:
            result = pressure_distribution(pressure, self.app.contact_threshold_kpa,
                                           cell_area_m2=self.app.cell_area_m2)
            if not result["values"].size:
                self.distribution_text.set("No cells exceed the current contact threshold.")
            else:
                p = result["percentiles"]
                self.distribution_text.set(
                    f"Contacted cells: {len(result['values'])} | 90% at/below {p[90]:.2f} kPa | "
                    f"95% at/below {p[95]:.2f} kPa | 99% at/below {p[99]:.2f} kPa"
                )
                histogram = self.distribution_figure.add_subplot(221)
                histogram.hist(result["values"], bins=result["bin_edges"], color="green")
                histogram.set_xlabel("Pressure (kPa)")
                histogram.set_ylabel("Contacted cells")

                cumulative = self.distribution_figure.add_subplot(222)
                ordered = np.sort(result["values"])
                cumulative.plot(ordered, np.arange(1, len(ordered) + 1) / len(ordered) * 100)
                cumulative.set_xlabel("Pressure (kPa)")
                cumulative.set_ylabel("Contacted cells below (%)")

                area = self.distribution_figure.add_subplot(212)
                area.plot(result["area_thresholds"], result["area_above"], color="red")
                area.set_xlabel("Pressure threshold (kPa)")
                area.set_ylabel(f"Area above ({result['area_unit']})")
        self.distribution_figure.tight_layout()
        self.distribution_canvas.draw_idle()

    def _refresh_load(self):
        if self.app.frame is None:
            self.load_text.set("Connect a data source to inspect load distribution.")
            return
        pressure = self.app.frame["pressure"]
        if pressure is not None:
            result = load_distribution(pressure, calibrated=True, cell_area_m2=self.app.cell_area_m2)
        else:
            result = load_distribution(self.app.frame["baseline_subtracted"])
        if result is None:
            self.load_text.set("No positive measured load or signal in the current frame.")
            return
        q = result["quadrants"]
        self.load_text.set(
            f"Basis: {result['basis']}\n\n"
            f"Left {result['left']:.1f}%    Right {result['right']:.1f}%\n"
            f"Upper {result['upper']:.1f}%    Lower {result['lower']:.1f}%\n\n"
            f"Upper left {q['upper_left']:.1f}%    Upper right {q['upper_right']:.1f}%\n"
            f"Lower left {q['lower_left']:.1f}%    Lower right {q['lower_right']:.1f}%\n\n"
            f"Left/right imbalance: {result['left_right_imbalance']:+.1f}% (positive = left)\n"
            f"Upper/lower imbalance: {result['upper_lower_imbalance']:+.1f}% (positive = upper)"
        )
