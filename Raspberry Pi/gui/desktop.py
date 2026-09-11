"""The Tkinter desktop app"""

import socket
import time
import tkinter as tk
from tkinter import simpledialog, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 - registers the 3D projection

from config import (
    TOTAL_ROWS, TOTAL_COLS, VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT,
    BAUD_RATE, WEB_PORT, STALE_AFTER_S, RECONNECT_INTERVAL_S,
)
from processing.calibration import Calibration
from processing.modes import MODES
from processing.recording import RECORDINGS_DIR, Recorder, load_session
from sources.mqtt_source import MqttSource
from sources.serial_source import SerialSource, list_ports
from sources.simulated_source import SCENARIOS, SimulatedSource
from gui import web

POLL_INTERVAL_MS = 50  # how often the GUI checks for a new frame
DRAW_INTERVAL_S = 0.1  # cap the redraw rate - drawing is the expensive part

HEATMAP_COLORS = LinearSegmentedColormap.from_list(
    "relative_pressure", ["white", "green", "red"]
)


def _get_local_ip():
    """Machine's LAN IP, so another device can reach the local web server"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))  # no packet sent, just picks the outbound interface
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


class DesktopApp:
    """Owns the window, the active data source, and the current grid"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SmartMat")
        self.root.geometry("1150x750")

        self.source = None
        self.recorder = None
        self.web_server = None
        self.calibration = Calibration()
        self.current_grid = None       # post mode + baseline
        self.pre_baseline_grid = None  # post mode, pre baseline - so recalibrating doesn't compound
        self.cell_labels = None

        self.modes_by_label = {mode.label: mode for mode in MODES}
        self.active_mode = MODES[0]

        self.last_frame_time = None
        self.last_reconnect_attempt = 0.0
        self._last_draw_time = 0.0
        self._fps_frame_count = 0
        self._fps_last_check = time.time()

        self._build_connection_bar()
        self._build_actions_bar()
        self._build_options_bar()
        self.status_var = tk.StringVar(value="Not connected")
        ttk.Label(self.root, textvariable=self.status_var, padding=4).pack(side=tk.BOTTOM, fill=tk.X)
        self._refresh_devices()

        self.content = ttk.Frame(self.root)
        self.content.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._build_about_panel()
        self._build_plot()
        self._poll()

    # ---- window layout

    def _build_connection_bar(self):
        bar = ttk.Frame(self.root, padding=(8, 8, 8, 0))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(bar, text="Source:").pack(side=tk.LEFT)
        self.source_var = tk.StringVar(value="Simulated")
        source_menu = ttk.Combobox(
            bar, textvariable=self.source_var, state="readonly",
            values=["Serial", "MQTT", "Simulated"], width=10,
        )
        source_menu.pack(side=tk.LEFT, padx=(0, 8))
        source_menu.bind("<<ComboboxSelected>>", lambda _event: self._refresh_devices())

        ttk.Label(bar, text="Device:").pack(side=tk.LEFT)
        self.device_var = tk.StringVar()
        self.device_menu = ttk.Combobox(bar, textvariable=self.device_var, state="readonly", width=22)
        self.device_menu.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(bar, text="Connect", command=self._connect).pack(side=tk.LEFT, padx=(0, 12))

        self.connection_var = tk.StringVar(value="Not connected")
        ttk.Label(bar, textvariable=self.connection_var).pack(side=tk.LEFT)

    def _build_actions_bar(self):
        bar = ttk.Frame(self.root, padding=8)
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(bar, text="Plot:").pack(side=tk.LEFT)
        self.plot_type_var = tk.StringVar(value="2D Heatmap")
        plot_menu = ttk.Combobox(
            bar, textvariable=self.plot_type_var, state="readonly",
            values=["2D Heatmap", "3D Surface"], width=12,
        )
        plot_menu.pack(side=tk.LEFT, padx=(0, 12))
        plot_menu.bind("<<ComboboxSelected>>", lambda _event: self._build_plot())

        ttk.Label(bar, text="Mode:").pack(side=tk.LEFT)
        self.mode_var = tk.StringVar(value=self.active_mode.label)
        mode_menu = ttk.Combobox(
            bar, textvariable=self.mode_var, state="readonly",
            values=[mode.label for mode in MODES], width=16,
        )
        mode_menu.pack(side=tk.LEFT, padx=(0, 4))
        mode_menu.bind("<<ComboboxSelected>>", lambda _event: self._select_mode())

        self.mode_param_label_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.mode_param_label_var).pack(side=tk.LEFT)
        self.mode_param_var = tk.StringVar()
        self.mode_param_entry = ttk.Entry(bar, textvariable=self.mode_param_var, width=6)
        self.mode_param_entry.pack(side=tk.LEFT, padx=(0, 12))
        self.mode_param_entry.bind("<Return>", lambda _event: self._apply_mode_param())
        self.mode_param_entry.bind("<FocusOut>", lambda _event: self._apply_mode_param())
        self._select_mode()

        ttk.Button(bar, text="Reset", command=self._reset).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bar, text="Calibrate", command=self._capture_baseline).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bar, text="View calibration", command=self._view_baseline).pack(side=tk.LEFT, padx=(0, 12))

        self.record_button = ttk.Button(bar, text="Record", command=self._toggle_recording)
        self.record_button.pack(side=tk.LEFT)

    def _build_options_bar(self):
        """On/off checkboxes, separate from the action buttons above"""
        bar = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bar.pack(side=tk.TOP, fill=tk.X)

        self.auto_scale_var = self._checkbox(bar, "Auto-scale", self._toggle_calibration)
        self.paused_var = self._checkbox(bar, "Pause", self._toggle_pause)
        self.numbers_var = self._checkbox(bar, "Show numbers", self._toggle_numbers)
        self.auto_reconnect_var = self._checkbox(bar, "Auto-reconnect")
        self.web_ui_var = self._checkbox(bar, "Web UI", self._toggle_web_ui)
        self.share_live_var = self._checkbox(bar, "Share live data", self._toggle_share_live)

    @staticmethod
    def _checkbox(parent, text, command=None):
        """Add one checkbox to parent, return its BooleanVar"""
        var = tk.BooleanVar(value=False)
        kwargs = {"command": command} if command else {}
        ttk.Checkbutton(parent, text=text, variable=var, **kwargs).pack(side=tk.LEFT, padx=(0, 8))
        return var

    def _build_about_panel(self):
        """FPS and a few general facts"""
        panel = ttk.LabelFrame(self.content, text="About", padding=8)
        panel.pack(side=tk.RIGHT, fill=tk.Y)

        self.fps_var = tk.StringVar(value="FPS: -")
        ttk.Label(panel, textvariable=self.fps_var).pack(anchor="w", pady=(0, 8))

        self._info_line(panel, "ESP32", header=True)
        self._info_line(panel, f"Grid: {TOTAL_ROWS} x {TOTAL_COLS}")
        self._info_line(panel, f"Baud rate: {BAUD_RATE}")
        self._info_line(panel, f"Value range: {VALUE_MIN_DEFAULT}-{VALUE_MAX_DEFAULT}")

        self._info_line(panel, "App", header=True, top_pad=8)
        self._info_line(panel, f"Host IP: {_get_local_ip()}")
        self._info_line(panel, f"Web UI port: {WEB_PORT}")
        self._info_line(panel, f"Stale after: {STALE_AFTER_S}s")
        self._info_line(panel, f"Reconnect every: {RECONNECT_INTERVAL_S}s")

    @staticmethod
    def _info_line(parent, text, header=False, top_pad=0):
        kwargs = {"font": ("", 9, "bold")} if header else {}
        ttk.Label(parent, text=text, **kwargs).pack(anchor="w", pady=(top_pad, 0))

    def _refresh_devices(self):
        """Repopulate the device dropdown, keeping the current selection if still valid"""
        source = self.source_var.get()
        previous = self.device_var.get()

        if source == "Serial":
            values = [port.device for port in list_ports()]
            default = values[0] if values else ""
        elif source == "MQTT":
            values = ["(configured broker)"]
            default = values[0]
        else:
            values = [f"Synthetic: {name}" for name in SCENARIOS]
            if RECORDINGS_DIR.exists():
                values += [path.name for path in RECORDINGS_DIR.glob("*.csv")]
            default = values[0]

        self.device_menu.configure(values=values)
        self.device_var.set(previous if previous in values else default)

    def _build_plot(self):
        """Build the matplotlib figure for the currently selected plot type"""
        if hasattr(self, "canvas"):
            self.canvas.get_tk_widget().destroy()

        self.cell_labels = None
        self.figure = Figure(figsize=(6, 6))
        if self.plot_type_var.get() == "3D Surface":
            self.axes = self.figure.add_subplot(projection="3d")
        else:
            self.axes = self.figure.add_subplot()
            self.image = self.axes.imshow(
                np.zeros((TOTAL_ROWS, TOTAL_COLS)),
                cmap=HEATMAP_COLORS, vmin=VALUE_MIN_DEFAULT, vmax=VALUE_MAX_DEFAULT,
                aspect="auto",
            )
            self.figure.colorbar(self.image, ax=self.axes, label="Relative sensor value")

            # numbers only apply to 2D
            if self.numbers_var.get():
                self.cell_labels = [
                    [self.axes.text(col, row, "0", ha="center", va="center", fontsize=6)
                     for col in range(TOTAL_COLS)]
                    for row in range(TOTAL_ROWS)
                ]

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.content)
        self.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        if self.current_grid is not None:
            self._update_plot()

    # ---- source lifecycle

    def _connect(self):
        """Stop the current source and start the selected one"""
        if self.source is not None:
            self.source.stop()
            self.source = None

        source_name = self.source_var.get()
        device = self.device_var.get()

        try:
            if source_name == "Serial":
                self.source = SerialSource(device)
            elif source_name == "MQTT":
                self.source = MqttSource()
            elif device.startswith("Synthetic:"):
                self.source = SimulatedSource(scenario=device.split(":", 1)[1].strip())
            elif not device:
                self.source = SimulatedSource()
            else:
                self.source = SimulatedSource(playback_frames=load_session(RECORDINGS_DIR / device))

            self.source.start()
            self.last_frame_time = time.time()
            self.status_var.set(f"Connected via {source_name} ({device})")
        except Exception as error:
            self.source = None
            self.status_var.set(f"Could not connect: {error}")

    # ---- mode / calibration / pause / numbers

    def _select_mode(self):
        self.active_mode = self.modes_by_label[self.mode_var.get()]
        self.active_mode.reset()
        if self.active_mode.param_label:
            self.mode_param_label_var.set(self.active_mode.param_label + ":")
            self.mode_param_var.set(str(self.active_mode.param_default))
            self.mode_param_entry.configure(state="normal")
        else:
            self.mode_param_label_var.set("")
            self.mode_param_var.set("")
            self.mode_param_entry.configure(state="disabled")

    def _apply_mode_param(self):
        if not self.active_mode.param_label:
            return
        try:
            self.active_mode.set_param(float(self.mode_param_var.get()))
        except ValueError:
            pass  # bad input, keep the previous value

    def _toggle_calibration(self):
        self.calibration.toggle_auto()

    def _capture_baseline(self):
        if self.pre_baseline_grid is None:
            self.status_var.set("No frame yet - can't calibrate")
            return
        self.calibration.capture_baseline(self.pre_baseline_grid)
        self.status_var.set("Calibrated: current reading set as the new baseline")

    def _view_baseline(self):
        if self.calibration.baseline is None:
            self.status_var.set("No calibration baseline captured yet")
            return
        window = tk.Toplevel(self.root)
        window.title("Calibration baseline")
        figure = Figure(figsize=(5, 5))
        axes = figure.add_subplot()
        image = axes.imshow(self.calibration.baseline, cmap=HEATMAP_COLORS, aspect="auto")
        figure.colorbar(image, ax=axes, label="Baseline value")
        FigureCanvasTkAgg(figure, master=window).get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _reset(self):
        self.calibration.reset()
        self.auto_scale_var.set(False)

    def _toggle_pause(self):
        """Live jumps to current on resume; a recording resumes at the next frame"""
        paused = self.paused_var.get()
        if self.source is not None and hasattr(self.source, "pause"):
            if paused:
                self.source.pause()
            else:
                self.source.resume()
        if not paused and self.current_grid is not None:
            self._update_plot()

    def _toggle_numbers(self):
        self._build_plot()

    # ---- recording

    def _toggle_recording(self):
        if self.recorder is None:
            name = simpledialog.askstring("Record session", "Session name:", parent=self.root)
            if not name:
                return
            self.recorder = Recorder(name)
            self.record_button.configure(text="Stop recording")
        else:
            frame_count = self.recorder.frame_count
            try:
                path = self.recorder.save()
                self.status_var.set(f"Saved {frame_count} frames to {path}")
                self._refresh_devices()  # so the new recording shows up as a device
            except OSError as error:
                self.status_var.set(f"Failed to save recording: {error}")
            finally:
                self.recorder = None
                self.record_button.configure(text="Record")

    # ---- local web server

    def _toggle_web_ui(self):
        if self.web_ui_var.get():
            self.web_server = web.WebServer()
            self.web_server.start()
            self.status_var.set(f"Web UI running at http://localhost:{web.WEB_PORT}")
        elif self.web_server is not None:
            self.web_server.stop()
            self.web_server = None

    def _toggle_share_live(self):
        web.set_sharing(self.share_live_var.get())

    # ---- per-frame update

    def _poll(self):
        """Check for a new frame and update everything, then reschedule"""
        if self.source is not None:
            grid = self.source.latest.take()
            if grid is not None:
                self._handle_new_frame(grid)
            self._check_connection_health()
        self._update_fps()
        self.root.after(POLL_INTERVAL_MS, self._poll)

    def _handle_new_frame(self, grid):
        self.last_frame_time = time.time()
        self._fps_frame_count += 1

        self.pre_baseline_grid = self.active_mode.apply(grid)
        self.current_grid = self.calibration.apply_baseline(self.pre_baseline_grid)

        self.calibration.update(self.current_grid)
        if self.recorder is not None:
            self.recorder.add_frame(self.current_grid)
        web.update_grid(self.current_grid)

        # drawing is expensive (esp. with numbers on) - cap the rate
        now = time.time()
        if not self.paused_var.get() and now - self._last_draw_time >= DRAW_INTERVAL_S:
            self._last_draw_time = now
            self._update_plot()

    def _update_fps(self):
        now = time.time()
        if now - self._fps_last_check >= 1.0:
            self.fps_var.set(f"FPS: {self._fps_frame_count / (now - self._fps_last_check):.1f}")
            self._fps_frame_count = 0
            self._fps_last_check = now

    def _check_connection_health(self):
        """Flag a stale connection, and optionally auto-reconnect"""
        if self.last_frame_time is None:
            return
        stale_for = time.time() - self.last_frame_time
        if stale_for < STALE_AFTER_S:
            self.connection_var.set("Connected")
            return

        self.connection_var.set(f"No data for {stale_for:.0f}s")
        if self.auto_reconnect_var.get() and time.time() - self.last_reconnect_attempt >= RECONNECT_INTERVAL_S:
            self.last_reconnect_attempt = time.time()
            self.connection_var.set(f"No data for {stale_for:.0f}s - reconnecting...")
            self._connect()

    def _update_plot(self):
        grid = self.current_grid
        if self.plot_type_var.get() == "3D Surface":
            self.axes.clear()
            cols, rows = np.meshgrid(range(TOTAL_COLS), range(TOTAL_ROWS))
            self.axes.plot_surface(
                cols, rows, grid, cmap=HEATMAP_COLORS,
                vmin=self.calibration.vmin, vmax=self.calibration.vmax,
            )
            self.axes.set_zlim(self.calibration.vmin, self.calibration.vmax)
        else:
            self.image.set_data(grid)
            self.image.set_clim(self.calibration.vmin, self.calibration.vmax)
            if self.cell_labels is not None:
                label_values = (grid / 10).astype(int)
                for row in range(TOTAL_ROWS):
                    for col in range(TOTAL_COLS):
                        self.cell_labels[row][col].set_text(str(label_values[row, col]))
        self.canvas.draw_idle()

        if self.recorder is not None:
            elapsed = time.time() - self.recorder.started_at
            prefix = f"Recording '{self.recorder.name}' - {elapsed:.0f}s, {self.recorder.frame_count} frames   "
        else:
            prefix = ""
        self.status_var.set(
            f"{prefix}avg {grid.mean():.0f}   max {grid.max():.0f}   min {grid.min():.0f}"
        )

    # ---- lifecycle

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self.source is not None:
            self.source.stop()
        if self.web_server is not None:
            self.web_server.stop()
        self.root.destroy()
