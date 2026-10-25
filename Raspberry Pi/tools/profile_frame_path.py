"""Profile the desktop's per-frame work without Tk: processing (as gui/desktop.py _handle_new_frame runs it)
and the plot update (matplotlib Agg standing in for the Tk canvas).

    python tools/profile_frame_path.py                 # timing table
    python tools/profile_frame_path.py --cprofile      # cProfile top of the processing part
    python tools/profile_frame_path.py --repeat 5 --no-plot
"""

import argparse
import cProfile
from pathlib import Path
import pstats
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # the app folder

import config  # noqa: E402
from processing.calibration import Calibration, PressureCalibration  # noqa: E402
from processing.display import interpolate_grid  # noqa: E402
from processing.frames import process_frame  # noqa: E402
from processing.hotspots import HotspotTracker  # noqa: E402
from processing.indices import IndexMonitor, tuned_indices  # noqa: E402
from processing.modes import LiveMode  # noqa: E402
from processing.motion import MotionAnalyzer  # noqa: E402
from processing.occupancy import OccupancyDetector  # noqa: E402
from processing.recording import load_session  # noqa: E402
from processing.sensor_health import SensorHealth  # noqa: E402
from processing.signals import Context  # noqa: E402
from processing.statistics import contact_mask, pressure_statistics, saturated_cells, weighted_center  # noqa: E402
from processing.temporal import TemporalAnalysis  # noqa: E402

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "seat_take1.json"


class Pipeline:
    """The classes _handle_new_frame drives, in the same order, with a per-step timer"""

    def __init__(self, rows, cols, cell_area_m2=None):
        config.TOTAL_ROWS, config.TOTAL_COLS = rows, cols
        self.cell_area = cell_area_m2
        self.mode, self.cal, self.pcal = LiveMode(), Calibration(), PressureCalibration.default()
        self.temporal, self.hotspots, self.motion = TemporalAnalysis(), HotspotTracker(), MotionAnalyzer()
        self.occupancy, self.health = OccupancyDetector(), SensorHealth()
        self.indices = IndexMonitor(tuned_indices(60, 70))
        self.contact = config.CONTACT_THRESHOLD_KPA
        self.times = {}

    def _t(self, name, start):
        self.times[name] = self.times.get(name, 0.0) + time.perf_counter() - start

    def frame(self, grid, timestamp):
        t = time.perf_counter()
        frame = process_frame(grid, self.mode, self.cal, self.pcal)
        self._t("process_frame", t)
        pressure = frame["pressure"]
        t = time.perf_counter()
        self.temporal.update(pressure, timestamp)
        self._t("temporal", t)
        t = time.perf_counter()
        self.hotspots.update(pressure, timestamp, self.temporal, self.cell_area)
        self._t("hotspots", t)
        t = time.perf_counter()
        self.motion.update(pressure, timestamp, self.contact, self.cell_area, self.hotspots.active, self.temporal)
        self._t("motion", t)
        t = time.perf_counter()
        self.occupancy.update(pressure, timestamp, self.contact)
        self._t("occupancy", t)
        t = time.perf_counter()
        context = Context(pressure, timestamp, self.contact, self.temporal, self.hotspots, self.motion, None)
        self.indices.update(context, timestamp, self.occupancy.occupied)
        self._t("indices", t)
        t = time.perf_counter()
        self.health.update(frame["raw"], timestamp, baseline=self.cal.baseline, pressure=pressure,
                           contact_threshold_kpa=self.contact, pressure_calibration=self.pcal)
        self._t("sensor_health", t)
        t = time.perf_counter()
        self.cal.update(frame["display"])
        self._t("calibration.update", t)
        t = time.perf_counter()
        saturated_cells(frame["raw"])
        weighted_center(pressure, self.contact)
        pressure_statistics(pressure, self.contact, self.cell_area)
        self._t("stats", t)
        return frame


class PlotSim:
    """Matplotlib Agg version of DesktopApp._update_plot for the default 2D view (image + hotspot/boundary overlays)"""

    def __init__(self, rows, cols, pipeline):
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
        if "tkinter" not in sys.modules:  # gui.theme imports tkinter at the top; only its pure helpers are used here
            try:
                import tkinter  # noqa: F401
            except ImportError:
                from unittest import mock
                for name in ("tkinter", "tkinter.font", "tkinter.ttk"):
                    sys.modules[name] = mock.MagicMock()
        from gui.theme import heatmap_cmap
        self.rows, self.cols, self.p = rows, cols, pipeline
        self.figure = Figure(figsize=(6, 6), dpi=100)
        self.canvas = FigureCanvasAgg(self.figure)
        self.axes = self.figure.add_subplot()
        self.image = self.axes.imshow(np.zeros((rows, cols)), cmap=heatmap_cmap(), aspect="auto")
        self.figure.colorbar(self.image, ax=self.axes)
        self.labels = []

    def prepare(self, frame):
        """Everything _update_plot does before the canvas draw"""
        grid = frame["pressure"]
        grid = np.where(np.isfinite(grid) & (grid > 0), grid, 0.0)
        finite = grid[np.isfinite(grid)]
        vmax = max(1.0, float(finite.max())) if finite.size else 1.0
        return interpolate_grid(grid, "None", 4), vmax

    def update(self, frame):
        grid, vmax = self.prepare(frame)
        for collection in list(self.axes.collections):
            collection.remove()
        self.image.set_data(grid)
        self.image.set_clim(0, vmax)
        mask = contact_mask(frame["pressure"], self.p.contact)
        if mask.any() and not mask.all():
            self.axes.contour(np.arange(self.cols), np.arange(self.rows), mask.astype(float),
                              levels=[0.5], colors="blue", linewidths=0.8, alpha=0.6)
        for label in self.labels:
            label.remove()
        self.labels = []
        for track in self.p.hotspots.active:
            m = np.zeros((self.rows, self.cols))
            for row, col in track["cells"]:
                m[row, col] = 1
            if not m.all():
                self.axes.contour(np.arange(self.cols), np.arange(self.rows), m, levels=[0.5], colors="red")
            row, col = track["centroid"]
            self.labels.append(self.axes.text(col, row, f"#{track['id']}", fontsize=8))

    def draw(self):
        self.canvas.draw()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", default=str(SAMPLE))
    parser.add_argument("--repeat", type=int, default=3, help="passes over the recording")
    parser.add_argument("--no-plot", action="store_true")
    parser.add_argument("--cprofile", action="store_true")
    args = parser.parse_args()

    frames, timestamps, metadata, _ = load_session(args.file, with_details=True)
    rows, cols = frames[0].shape
    n = len(frames)
    span = timestamps[-1] - timestamps[0]
    print(f"{n} frames {rows}x{cols}, {span:.1f} s recorded ({n / span:.1f} fps)")

    def run_processing():
        pipe = Pipeline(rows, cols, 0.0171 * 0.0179)
        for repeat in range(args.repeat):  # later passes get later timestamps so state keeps evolving
            offset = repeat * (span + 1.0)
            for grid, stamp in zip(frames, timestamps):
                pipe.frame(grid, stamp + offset)
        return pipe

    if args.cprofile:
        profiler = cProfile.Profile()
        profiler.enable()
        run_processing()
        profiler.disable()
        pstats.Stats(profiler).sort_stats("cumulative").print_stats(25)
        return

    start = time.perf_counter()
    pipe = run_processing()
    total = time.perf_counter() - start
    count = n * args.repeat
    print(f"processing: {total / count * 1000:.3f} ms/frame (wall, incl. timer overhead)")
    for name, seconds in sorted(pipe.times.items(), key=lambda item: -item[1]):
        print(f"  {name:20s} {seconds / count * 1000:7.3f} ms/frame  {100 * seconds / total:5.1f}%")

    if not args.no_plot:
        sim = PlotSim(rows, cols, pipe)
        frame = process_frame(frames[len(frames) // 2], pipe.mode, pipe.cal, pipe.pcal)
        sim.draw()
        t = time.perf_counter()
        for _ in range(20):
            sim.update(frame)
        update_ms = (time.perf_counter() - t) / 20 * 1000
        t = time.perf_counter()
        for _ in range(20):
            sim.draw()
        draw_ms = (time.perf_counter() - t) / 20 * 1000
        print(f"plot update (artists, no draw): {update_ms:.2f} ms;  canvas.draw (Agg, full redraw): {draw_ms:.2f} ms")


if __name__ == "__main__":
    main()
