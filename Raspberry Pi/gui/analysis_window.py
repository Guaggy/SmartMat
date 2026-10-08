"""ROI and pressure-distribution plots kept off the main dashboard."""

import tkinter as tk
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from processing.analysis import load_distribution, pressure_distribution



class AnalysisWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("SMARTMAT analysis")
        self.window.geometry("950x700")
        ttk.Label(self.window, text='How pressure is spread over the whole mat, and its left/right and upper/lower balance. Regions are in the ROI window.', wraplength=760, padding=(8, 6)).pack(side=tk.TOP, fill=tk.X)

        self.tabs = ttk.Notebook(self.window)
        self.tabs.pack(fill=tk.BOTH, expand=True)
        distribution_tab = ttk.Frame(self.tabs)
        load_tab = ttk.Frame(self.tabs)
        self.tabs.add(distribution_tab, text="Distribution")
        self.tabs.add(load_tab, text="Load and symmetry")
        self.tabs.bind("<<NotebookTabChanged>>", lambda _event: self.refresh())

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
        if self.tabs.index("current") == 0:
            self._refresh_distribution()
        else:
            self._refresh_load()

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
