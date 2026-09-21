"""The Tkinter desktop app"""

import socket
import time
import tkinter as tk
from collections import deque
from tkinter import simpledialog, ttk

import numpy as np
import config as app_config
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 - registers the 3D projection

from config import (
    TOTAL_ROWS, TOTAL_COLS, VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT,
    BAUD_RATE, WEB_PORT, STALE_AFTER_S, RECONNECT_INTERVAL_S,
    CELL_WIDTH_MM, CELL_HEIGHT_MM, CONTACT_THRESHOLD_KPA,
    PRESSURE_DISPLAY_MAX_KPA, HISTORY_MAX_FRAMES,
    DISPLAY_SCALE, PRESSURE_CONTOUR_LEVELS_KPA, RELATIVE_CONTOUR_LEVELS,
    VALIDATION_MATCH_WINDOW_S,
)
from processing.calibration import Calibration, PressureCalibration
from processing.session_events import STATE_EVENTS, apply_state_event, event_is_due
from processing.session_state import initial_session_state
from processing.settings import apply_settings, capture_settings, default_settings
from processing.display import interpolate_grid
from processing.frames import process_frame, update_pressure
from processing.modes import MODES
from processing.recording import RECORDINGS_DIR, Recorder, load_session
from processing.sensor_health import SensorHealth
from processing.hotspots import HotspotTracker
from processing.motion import MotionAnalyzer
from processing.temporal import TemporalAnalysis
from processing.timeline import EventTimeline
from processing.statistics import contact_mask, pressure_statistics, weighted_center
from sources.mqtt_source import MqttSource
from sources.serial_source import SerialSource, list_ports
from sources.simulated_source import SCENARIOS, SimulatedSource
from gui import web
from gui.calibration_window import CalibrationWindow
from gui.analysis_window import AnalysisWindow
from gui.diagnostics_window import DiagnosticsWindow
from gui.temporal_window import TemporalWindow
from gui.hotspot_window import HotspotWindow
from gui.motion_window import MotionWindow
from gui.annotation_window import AnnotationWindow
from gui.engineering_window import EngineeringWindow
from gui.help_window import HelpWindow
from processing.validation import compare_hotspot_roi

POLL_INTERVAL_MS = 50  # how often the GUI checks for a new frame
DRAW_INTERVAL_S = 0.1  # cap the redraw rate - drawing is the expensive part
DATA_MODES = {
    "Raw / received": "raw",
    "Processed": "filtered",
    "Baseline subtracted": "baseline_subtracted",
    "Calibrated pressure": "pressure",
}

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
        self.pressure_calibration = PressureCalibration.default()
        self.sensor_health = SensorHealth()
        self.temporal = TemporalAnalysis()
        self.hotspots = HotspotTracker()
        self.motion = MotionAnalyzer()
        self.hotspot_window = None
        self.motion_window = None
        self._last_feature_draw = 0.0
        self._live_state = None
        self._playback_metadata = None
        self._recorded_state_events = []
        self._next_state_event = 0
        self._playback_frame_index = 0
        self._applying_playback_event = False
        self.session_state = None
        self.experiment_info = {}
        self.preset_name = "Default"
        self.validation_match_window_s = VALIDATION_MATCH_WINDOW_S
        self.show_hotspot_threshold = False
        self.engineering_window = None
        self.help_window = None
        self._current_analysis_settings = None
        self._replay_policy = "Reproduce recording"
        self.timeline = EventTimeline()
        self.temporal_window = None
        self._source_was_stale = False
        self._last_malformed = 0
        self._last_dropped = 0
        self.contact_threshold_kpa = CONTACT_THRESHOLD_KPA
        self.signal_noise_threshold = float(getattr(app_config, "SIGNAL_NOISE_THRESHOLD", 0.0))
        self.cell_area_m2 = None
        if CELL_WIDTH_MM and CELL_HEIGHT_MM and CELL_WIDTH_MM > 0 and CELL_HEIGHT_MM > 0:
            self.cell_area_m2 = CELL_WIDTH_MM * CELL_HEIGHT_MM / 1_000_000
        self.frame = None
        self.raw_grid = None
        self.current_grid = None
        self.pre_baseline_grid = None
        self.cell_labels = None
        self.selected_cell = None
        self.cell_history = deque(maxlen=HISTORY_MAX_FRAMES)
        self.cop_history = deque(maxlen=HISTORY_MAX_FRAMES)
        self.roi = None
        self.roi_corner = None
        self.selecting_roi = False
        self.roi_history = deque(maxlen=HISTORY_MAX_FRAMES)
        self.history_window = None
        self.analysis_window = None
        self.calibration_windows = []
        self.diagnostics_window = None
        self.plot_options_window = None
        self._last_history_draw = 0.0
        self._last_analysis_draw = 0.0
        self._last_diagnostics_draw = 0.0
        self._last_temporal_draw = 0.0
        self.stats = None
        self.display_cop = (None, None)
        self.interpolation_method = "None"
        self.display_scale = DISPLAY_SCALE
        self.show_contours = False
        self.show_boundary = False
        self.pressure_contour_levels = PRESSURE_CONTOUR_LEVELS_KPA
        self.relative_contour_levels = RELATIVE_CONTOUR_LEVELS
        self.reference_grid = None
        self.comparison_grid = None
        self.reference_mode = None
        self.difference_var = tk.BooleanVar(value=False)

        self.modes_by_label = {mode.label: mode for mode in MODES}
        self.active_mode = MODES[0]

        self.last_frame_time = None
        self.frame_timestamp = None
        self.last_reconnect_attempt = 0.0
        self._last_draw_time = 0.0
        self._fps_frame_count = 0
        self._fps_last_check = time.time()

        self._build_connection_bar()
        self._build_actions_bar()
        self._build_data_bar()
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
        ttk.Button(bar, text="Disconnect", command=self._disconnect).pack(side=tk.LEFT, padx=(0, 12))

        self.playback_speed_label = ttk.Label(bar, text="Playback:")
        self.playback_speed_var = tk.StringVar(value="1x")
        self.playback_speed_menu = ttk.Combobox(
            bar, textvariable=self.playback_speed_var, state="readonly",
            values=["0.25x", "0.5x", "1x", "2x", "5x"], width=6,
        )
        self.playback_speed_menu.bind("<<ComboboxSelected>>", lambda _event: self._set_playback_speed())
        self.replay_settings_var = tk.StringVar(value="Reproduce recording")
        self.replay_settings_menu = ttk.Combobox(
            bar, textvariable=self.replay_settings_var, state="readonly", width=22,
            values=["Reproduce recording", "Re-analyze with current settings"])
        self.replay_settings_menu.bind("<<ComboboxSelected>>", lambda _event: self._connect())

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
        ttk.Button(bar, text="Tare", command=self._capture_baseline).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bar, text="View tare", command=self._view_baseline).pack(side=tk.LEFT, padx=(0, 12))

        self.record_button = ttk.Button(bar, text="Record", command=self._toggle_recording)
        self.record_button.pack(side=tk.LEFT)

    def _build_data_bar(self):
        bar = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(bar, text="Data:").pack(side=tk.LEFT)
        self.data_mode_var = tk.StringVar(value="Baseline subtracted")
        data_menu = ttk.Combobox(bar, textvariable=self.data_mode_var, state="readonly",
                                 values=list(DATA_MODES), width=21)
        data_menu.pack(side=tk.LEFT, padx=(0, 12))
        data_menu.bind("<<ComboboxSelected>>", lambda _event: self._change_data_mode())

        ttk.Label(bar, text="Contact >").pack(side=tk.LEFT)
        self.threshold_var = tk.StringVar(value=str(self.contact_threshold_kpa))
        threshold_entry = ttk.Entry(bar, textvariable=self.threshold_var, width=6)
        threshold_entry.pack(side=tk.LEFT, padx=(2, 2))
        threshold_entry.bind("<Return>", lambda _event: self._apply_contact_threshold())
        threshold_entry.bind("<FocusOut>", lambda _event: self._apply_contact_threshold())
        ttk.Label(bar, text="kPa").pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(bar, text="Ignore signal <=").pack(side=tk.LEFT)
        self.noise_threshold_var = tk.StringVar(value=str(self.signal_noise_threshold))
        noise_entry = ttk.Entry(bar, textvariable=self.noise_threshold_var, width=6)
        noise_entry.pack(side=tk.LEFT, padx=(2, 8))
        noise_entry.bind("<Return>", lambda _event: self._apply_noise_threshold())
        noise_entry.bind("<FocusOut>", lambda _event: self._apply_noise_threshold())

        self.cop_var = self._checkbox(bar, "Show CoP", self._update_plot)
        ttk.Button(bar, text="Pressure calibration...", command=self._open_calibration).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bar, text="Plot options...", command=self._open_plot_options).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bar, text="Analysis...", command=self._open_analysis).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bar, text="Diagnostics...", command=self._open_diagnostics).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bar, text="Temporal...", command=self._open_temporal).pack(side=tk.LEFT)

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
        self.show_hotspots_var = self._checkbox(bar, "Show hotspots", self._toggle_hotspots)
        ttk.Button(bar, text="Hotspots...", command=self._open_hotspots).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Movement...", command=self._open_motion).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Engineering...", command=self._open_engineering).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Help", command=self._open_help).pack(side=tk.LEFT, padx=4)

    @staticmethod
    def _checkbox(parent, text, command=None):
        """Add one checkbox to parent, return its BooleanVar"""
        var = tk.BooleanVar(value=False)
        kwargs = {"command": command} if command else {}
        ttk.Checkbutton(parent, text=text, variable=var, **kwargs).pack(side=tk.LEFT, padx=(0, 8))
        return var

    def _build_about_panel(self):
        """FPS and a few general facts"""
        sidebar = ttk.Frame(self.content)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y)

        stats_panel = ttk.LabelFrame(sidebar, text="Live pressure", padding=8)
        stats_panel.pack(side=tk.TOP, fill=tk.X)
        self.pressure_status_var = tk.StringVar(value="Default pressure calibration active")
        ttk.Label(stats_panel, textvariable=self.pressure_status_var, wraplength=190).pack(anchor="w")
        self.peak_var = tk.StringVar(value="Peak: -")
        self.mean_var = tk.StringVar(value="Mean contact: -")
        self.area_var = tk.StringVar(value="Contact area: -")
        self.force_var = tk.StringVar(value="Force: -")
        self.cop_text_var = tk.StringVar(value="CoP: -")
        self.selected_cell_var = tk.StringVar(value="Cell: click the 2D plot")
        for variable in (self.peak_var, self.mean_var, self.area_var,
                         self.force_var, self.cop_text_var, self.selected_cell_var):
            ttk.Label(stats_panel, textvariable=variable).pack(anchor="w")

        panel = ttk.LabelFrame(sidebar, text="About", padding=8)
        panel.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))

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
        if self.cell_area_m2 is None:
            self._info_line(panel, "Cell area: not configured")
        else:
            self._info_line(panel, f"Cell: {CELL_WIDTH_MM} x {CELL_HEIGHT_MM} mm")

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
                values += [path.name for path in RECORDINGS_DIR.iterdir()
                           if path.suffix in (".csv", ".json")]
            default = values[0]

        self.device_menu.configure(values=values)
        self.device_var.set(previous if previous in values else default)

    def _build_plot(self):
        """Build the matplotlib figure for the currently selected plot type"""
        if hasattr(self, "canvas"):
            self.canvas.get_tk_widget().destroy()

        self.cell_labels = None
        self.cop_marker = None
        self.selected_marker = None
        self.roi_patch = None
        self.hotspot_labels = []
        self.figure = Figure(figsize=(6, 6))
        if self.plot_type_var.get() == "3D Surface":
            self.axes = self.figure.add_subplot(projection="3d")
        else:
            self.axes = self.figure.add_subplot()
            self.image = self.axes.imshow(
                np.zeros((TOTAL_ROWS, TOTAL_COLS)),
                cmap="coolwarm" if self.difference_var.get() else HEATMAP_COLORS,
                vmin=VALUE_MIN_DEFAULT, vmax=VALUE_MAX_DEFAULT,
                aspect="auto",
            )
            unit = "Pressure (kPa)" if self.data_mode_var.get() == "Calibrated pressure" else "Relative sensor value"
            label = f"Difference in {unit}" if self.difference_var.get() else unit
            self.figure.colorbar(self.image, ax=self.axes, label=label)
            self.cop_marker, = self.axes.plot([], [], marker="+", color="blue", markersize=13,
                                              markeredgewidth=2, linestyle="None")
            self.selected_marker, = self.axes.plot([], [], marker="s", color="blue",
                                                   markersize=13, fillstyle="none", linestyle="None")

            # numbers only apply to 2D
            if self.numbers_var.get():
                self.cell_labels = [
                    [self.axes.text(col, row, "0", ha="center", va="center", fontsize=6)
                     for col in range(TOTAL_COLS)]
                    for row in range(TOTAL_ROWS)
                ]

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.content)
        self.canvas.mpl_connect("button_press_event", self._on_plot_click)
        self.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        if self.frame is not None:
            self._update_plot()

    # ---- source lifecycle

    def _connect(self):
        """Stop the current source and start the selected one"""
        self._close_calibration_windows()
        previous_analysis_settings = self._current_analysis_settings
        if self.source is not None:
            self.source.stop()
            self.source = None
        self._restore_live_state()
        self.connection_var.set("Not connected")
        self.last_frame_time = None
        self.frame_timestamp = None
        self._source_was_stale = False
        self._last_malformed = 0
        self._last_dropped = 0
        self.temporal.reset_all()
        self.hotspots.reset()
        self.motion.reset()
        self.session_state = None
        self.timeline = EventTimeline()
        self.playback_speed_label.pack_forget()
        self.playback_speed_menu.pack_forget()
        self.replay_settings_menu.pack_forget()

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
                frames, timestamps, metadata, events = load_session(
                    RECORDINGS_DIR / device, with_timestamps=True, with_details=True)
                self.source = SimulatedSource(playback_frames=frames, playback_timestamps=timestamps)
                self.timeline = EventTimeline(events)
                self._live_state = (self.calibration, self.pressure_calibration, self.temporal,
                                    self.hotspots, self.motion,
                                    self.active_mode.label, self.mode_param_var.get(),
                                    self.contact_threshold_kpa, self.preset_name,
                                    self.experiment_info.copy())
                self._current_analysis_settings = capture_settings(
                    self.contact_threshold_kpa, self.temporal, self.hotspots, self.motion)
                self._replay_policy = self.replay_settings_var.get()
                if self._replay_policy == "Re-analyze with current settings" and previous_analysis_settings:
                    self._current_analysis_settings = previous_analysis_settings
                self._playback_metadata = metadata
                self._recorded_state_events = [event for event in events if event.get("kind") in STATE_EVENTS]
                self._reset_playback_state()

            if getattr(self.source, "is_playback", False):
                self.source.set_playback_speed(float(self.playback_speed_var.get().rstrip("x")))
                self.playback_speed_label.pack(side=tk.LEFT, padx=(0, 3))
                self.playback_speed_menu.pack(side=tk.LEFT, padx=(0, 12))
                self.replay_settings_menu.pack(side=tk.LEFT, padx=(0, 12))
            else:
                self.playback_speed_label.pack_forget()
                self.playback_speed_menu.pack_forget()
                self.replay_settings_menu.pack_forget()

            self.active_mode.reset()
            self.cell_history.clear()
            self.cop_history.clear()
            self.roi_history.clear()
            self.sensor_health.reset()
            self.source.start()
            self.last_frame_time = time.time()
            replay_label = f" | {self._replay_policy}" if getattr(self.source, "is_playback", False) else ""
            self.status_var.set(f"Connected via {source_name} ({device}){replay_label}")
        except Exception as error:
            self.source = None
            self._restore_live_state()
            self._applying_playback_event = False
            self.status_var.set(f"Could not connect: {error}")

    def _disconnect(self):
        self._close_calibration_windows()
        if self.source is not None:
            self.source.stop()
            self.add_event("source_disconnected")
            self.source = None
        self._restore_live_state()
        self.frame = None
        self.session_state = None
        self.raw_grid = None
        self.current_grid = None
        self.last_frame_time = None
        self.playback_speed_label.pack_forget()
        self.playback_speed_menu.pack_forget()
        self.replay_settings_menu.pack_forget()
        self.connection_var.set("Not connected")
        self.status_var.set("Disconnected")
        self._update_stats()
        self._build_plot()

    def _close_calibration_windows(self):
        for editor in self.calibration_windows:
            if editor.window.winfo_exists():
                editor.window.destroy()
        self.calibration_windows.clear()

    def _restore_live_state(self):
        if self._live_state is None:
            return
        (self.calibration, self.pressure_calibration, self.temporal,
         self.hotspots, self.motion,
         label, parameter, self.contact_threshold_kpa, self.preset_name,
         self.experiment_info) = self._live_state
        self._live_state = None
        self._playback_metadata = None
        self._recorded_state_events = []
        self._current_analysis_settings = None
        self.mode_var.set(label)
        self._select_mode()
        if parameter and self.active_mode.param_label:
            self.mode_param_var.set(parameter)
            self._apply_mode_param()
        self.threshold_var.set(str(self.contact_threshold_kpa))

    def _reset_playback_state(self):
        metadata = self._playback_metadata or {}
        self.session_state = None
        self._applying_playback_event = True
        self.calibration = Calibration()
        self.pressure_calibration = PressureCalibration()
        self.temporal = TemporalAnalysis()
        self.hotspots = HotspotTracker()
        self.motion = MotionAnalyzer()
        if metadata.get("pressure_calibration"):
            self.pressure_calibration.load_dict(metadata["pressure_calibration"])
        if metadata.get("baseline_processed") is not None:
            self.calibration.baseline = np.asarray(metadata["baseline_processed"], dtype=float)
        if self._replay_policy == "Re-analyze with current settings":
            settings = self._current_analysis_settings
            self.preset_name = self._live_state[8]
        else:
            settings = default_settings()
            settings["contact_threshold_kpa"] = metadata.get("contact_threshold_kpa", CONTACT_THRESHOLD_KPA)
            for group, key in (("temporal", "temporal"), ("hotspots", "hotspots"),
                               ("movement", "movement")):
                settings[group].update(metadata.get(key, {}))
            self.preset_name = metadata.get("preset", "Recorded")
        self.experiment_info = metadata.get("experiment", {}).copy()
        self.contact_threshold_kpa = apply_settings(settings, self.temporal, self.hotspots, self.motion)
        self.threshold_var.set(str(self.contact_threshold_kpa))
        label = (self._live_state[5] if self._replay_policy == "Re-analyze with current settings"
                 else metadata.get("processing_mode", MODES[0].label))
        self.mode_var.set(label if label in self.modes_by_label else MODES[0].label)
        self._select_mode()
        parameter = (self._live_state[6] if self._replay_policy == "Re-analyze with current settings"
                     else metadata.get("processing_parameter"))
        if parameter is not None and self.active_mode.param_label:
            self.mode_param_var.set(str(parameter))
            self._apply_mode_param()
        self._applying_playback_event = False
        self._next_state_event = 0
        self._playback_frame_index = 0

    def _apply_playback_state_events(self, timestamp):
        self._applying_playback_event = True
        try:
            while self._next_state_event < len(self._recorded_state_events):
                event = self._recorded_state_events[self._next_state_event]
                if not event_is_due(event, self._playback_frame_index, timestamp):
                    break
                if (self._replay_policy == "Re-analyze with current settings" and
                        event["kind"] in ("algorithm_settings_changed", "temporal_parameters_changed",
                                          "processing_mode_changed", "contact_threshold_changed")):
                    self._next_state_event += 1
                    continue
                threshold = apply_state_event(event, self.calibration,
                                              self.pressure_calibration, self.temporal,
                                              self.hotspots, self.motion)
                if threshold is not None:
                    self.contact_threshold_kpa = threshold
                    self.threshold_var.set(str(threshold))
                if event["kind"] == "processing_mode_changed":
                    payload = event["payload"]
                    self.mode_var.set(payload["mode"])
                    self._select_mode()
                    if payload.get("parameter") is not None and self.active_mode.param_label:
                        self.mode_param_var.set(str(payload["parameter"]))
                        self._apply_mode_param()
                self.temporal.invalidate()
                self.hotspots.invalidate()
                self.motion.invalidate()
                self._next_state_event += 1
        finally:
            self._applying_playback_event = False

    def _set_playback_speed(self):
        if self.source is not None and getattr(self.source, "is_playback", False):
            self.source.set_playback_speed(float(self.playback_speed_var.get().rstrip("x")))

    # ---- mode / calibration / pause / numbers

    def _select_mode(self):
        self.active_mode = self.modes_by_label[self.mode_var.get()]
        self.active_mode.reset()
        self.temporal.invalidate()
        self.hotspots.invalidate()
        self.motion.invalidate()
        self.cell_history.clear()
        self.roi_history.clear()
        if self.active_mode.param_label:
            self.mode_param_label_var.set(self.active_mode.param_label + ":")
            self.mode_param_var.set(str(self.active_mode.param_default))
            self.active_mode.set_param(self.active_mode.param_default)
            self.mode_param_entry.configure(state="normal")
        else:
            self.mode_param_label_var.set("")
            self.mode_param_var.set("")
            self.mode_param_entry.configure(state="disabled")
        if self.recorder is not None and not self._applying_playback_event:
            self.add_event("processing_mode_changed", payload={
                "mode": self.active_mode.label,
                "parameter": self.mode_param_var.get() if self.active_mode.param_label else None})

    def _apply_mode_param(self):
        if not self.active_mode.param_label:
            return
        try:
            value = float(self.mode_param_var.get())
            if not np.isfinite(value):
                raise ValueError
            if self.active_mode.label == "Exponential average" and not 0 <= value <= 1:
                raise ValueError
            if self.active_mode.label == "Average" and value < 1:
                raise ValueError
            self.active_mode.set_param(value)
            self.temporal.invalidate()
            self.hotspots.invalidate()
            self.motion.invalidate()
            self.cell_history.clear()
            self.roi_history.clear()
            if self.recorder is not None and not self._applying_playback_event:
                self.add_event("processing_mode_changed", payload={
                    "mode": self.active_mode.label, "parameter": value})
        except (ValueError, OverflowError):
            self.status_var.set("Enter a valid processing mode parameter")

    def _toggle_calibration(self):
        self.calibration.toggle_auto()

    def _change_data_mode(self):
        if self.difference_var.get() and DATA_MODES[self.data_mode_var.get()] != self.reference_mode:
            self.difference_var.set(False)
        self.roi_history.clear()
        self._update_stats()
        if self.frame is not None:
            self._build_plot()
        self._update_history_plot()
        self._refresh_analysis()

    def _apply_contact_threshold(self):
        try:
            value = float(self.threshold_var.get())
            if not np.isfinite(value) or value < 0:
                raise ValueError
            self.contact_threshold_kpa = value
            self.motion.invalidate()
            if self.recorder is not None and not self._applying_playback_event:
                self.add_event("contact_threshold_changed", payload={"threshold_kpa": value})
            self._update_stats()
            self._update_plot()
        except ValueError:
            self.threshold_var.set(str(self.contact_threshold_kpa))
            self.status_var.set("Contact threshold must be a nonnegative number")

    def _apply_noise_threshold(self):
        try:
            value = float(self.noise_threshold_var.get())
            if not np.isfinite(value) or value < 0:
                raise ValueError
            self.signal_noise_threshold = value
            self.cop_history.clear()
            self._update_stats()
            self._update_plot()
        except ValueError:
            self.noise_threshold_var.set(str(self.signal_noise_threshold))
            self.status_var.set("Signal noise threshold must be a nonnegative number")

    def _open_calibration(self):
        editor = CalibrationWindow(self.root, self.pressure_calibration,
                                   lambda: self.raw_grid, self._refresh_calibration)
        self.calibration_windows.append(editor)

    def _open_plot_options(self):
        if self.plot_options_window is not None and self.plot_options_window.winfo_exists():
            self.plot_options_window.lift()
            return
        window = tk.Toplevel(self.root)
        window.title("Plot options")
        window.geometry("430x320")
        self.plot_options_window = window
        panel = ttk.Frame(window, padding=12)
        panel.pack(fill=tk.BOTH, expand=True)

        ttk.Label(panel, text="Interpolation:").grid(row=0, column=0, sticky="w")
        self.interpolation_var = tk.StringVar(value=self.interpolation_method)
        method_menu = ttk.Combobox(panel, textvariable=self.interpolation_var, state="readonly",
                                   values=["None", "Nearest", "Linear"], width=12)
        method_menu.grid(row=0, column=1, sticky="w")
        method_menu.bind("<<ComboboxSelected>>", lambda _event: self._apply_plot_options())
        ttk.Label(panel, text="Display scale:").grid(row=1, column=0, sticky="w", pady=8)
        self.display_scale_var = tk.StringVar(value=str(self.display_scale))
        scale_entry = ttk.Entry(panel, textvariable=self.display_scale_var, width=7)
        scale_entry.grid(row=1, column=1, sticky="w")
        scale_entry.bind("<Return>", lambda _event: self._apply_plot_options())
        scale_entry.bind("<FocusOut>", lambda _event: self._apply_plot_options())

        self.contours_var = tk.BooleanVar(value=self.show_contours)
        ttk.Checkbutton(panel, text="Show contours", variable=self.contours_var,
                        command=self._apply_plot_options).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(panel, text="Pressure levels (kPa):").grid(row=3, column=0, sticky="w", pady=5)
        self.pressure_levels_var = tk.StringVar(value=", ".join(map(str, self.pressure_contour_levels)))
        ttk.Entry(panel, textvariable=self.pressure_levels_var, width=25).grid(row=3, column=1, sticky="w")
        ttk.Label(panel, text="Relative levels:").grid(row=4, column=0, sticky="w", pady=5)
        self.relative_levels_var = tk.StringVar(value=", ".join(map(str, self.relative_contour_levels)))
        ttk.Entry(panel, textvariable=self.relative_levels_var, width=25).grid(row=4, column=1, sticky="w")
        ttk.Button(panel, text="Apply levels", command=self._apply_plot_options).grid(row=5, column=1, sticky="w")

        self.boundary_var = tk.BooleanVar(value=self.show_boundary)
        ttk.Checkbutton(panel, text="Show contact boundary", variable=self.boundary_var,
                        command=self._apply_plot_options).grid(row=6, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Button(panel, text="Capture reference", command=self._capture_reference).grid(row=7, column=0, sticky="w")
        ttk.Button(panel, text="Clear reference", command=self._clear_reference).grid(row=7, column=1, sticky="w")
        ttk.Checkbutton(panel, text="Show difference", variable=self.difference_var,
                        command=self._toggle_difference).grid(row=8, column=0, columnspan=2, sticky="w", pady=8)

    def _apply_plot_options(self):
        try:
            scale = int(self.display_scale_var.get())
            if not 1 <= scale <= 10:
                raise ValueError
            pressure_levels = tuple(float(item.strip()) for item in self.pressure_levels_var.get().split(","))
            relative_levels = tuple(float(item.strip()) for item in self.relative_levels_var.get().split(","))
            if not pressure_levels or not relative_levels:
                raise ValueError
            if any(not np.isfinite(value) or value < 0 for value in pressure_levels + relative_levels):
                raise ValueError
            self.display_scale = scale
            self.pressure_contour_levels = tuple(sorted(set(pressure_levels)))
            self.relative_contour_levels = tuple(sorted(set(relative_levels)))
            self.interpolation_method = self.interpolation_var.get()
            self.show_contours = self.contours_var.get()
            self.show_boundary = self.boundary_var.get()
            self._update_plot()
        except ValueError:
            self.status_var.set("Plot scale must be 1-10; contour levels must be nonnegative numbers")

    def _capture_reference(self):
        if self.frame is None:
            self.status_var.set("Connect a source before capturing a reference")
            return
        key = DATA_MODES[self.data_mode_var.get()]
        grid = self.frame[key]
        if grid is None:
            self.status_var.set("This data mode is unavailable for a reference")
            return
        self.reference_grid = grid.copy()
        self.comparison_grid = None
        self.reference_mode = key
        self.difference_var.set(True)
        self._build_plot()

    def _clear_reference(self):
        self.reference_grid = None
        self.comparison_grid = None
        self.reference_mode = None
        self.difference_var.set(False)
        self._build_plot()

    def _toggle_difference(self):
        if self.difference_var.get() and (self.reference_grid is None or
                                          self.reference_mode != DATA_MODES[self.data_mode_var.get()]):
            self.difference_var.set(False)
            self.status_var.set("Capture a reference in the selected data mode first")
        else:
            self._build_plot()

    def _open_analysis(self):
        if self.analysis_window is not None and self.analysis_window.window.winfo_exists():
            self.analysis_window.window.lift()
        else:
            self.analysis_window = AnalysisWindow(self.root, self)

    def _open_diagnostics(self):
        if self.diagnostics_window is not None and self.diagnostics_window.window.winfo_exists():
            self.diagnostics_window.window.lift()
        else:
            self.diagnostics_window = DiagnosticsWindow(
                self.root, self.sensor_health, lambda: self.selected_cell, self._select_cell,
                lambda: self.source.quality.snapshot() if self.source is not None else None)

    def _open_temporal(self):
        if self.temporal_window is not None and self.temporal_window.window.winfo_exists():
            self.temporal_window.window.lift()
        else:
            self.temporal_window = TemporalWindow(self.root, self)

    def _open_hotspots(self):
        if self.hotspot_window is not None and self.hotspot_window.window.winfo_exists():
            self.hotspot_window.window.lift()
        else:
            self.hotspot_window = HotspotWindow(self.root, self)

    def _open_motion(self):
        if self.motion_window is not None and self.motion_window.window.winfo_exists():
            self.motion_window.window.lift()
        else:
            self.motion_window = MotionWindow(self.root, self)

    def _open_annotation(self, initial_type="Note"):
        AnnotationWindow(self.root, self, initial_type)

    def _open_engineering(self):
        if self.engineering_window is not None and self.engineering_window.window.winfo_exists():
            self.engineering_window.window.lift()
        else:
            self.engineering_window = EngineeringWindow(self.root, self)

    def _open_help(self):
        if self.help_window is not None and self.help_window.window.winfo_exists():
            self.help_window.window.lift()
        else:
            self.help_window = HelpWindow(self.root)

    def current_settings(self):
        return capture_settings(self.contact_threshold_kpa, self.temporal,
                                self.hotspots, self.motion)

    def apply_engineering_settings(self, settings, preset_name=None):
        self.contact_threshold_kpa = apply_settings(
            settings, self.temporal, self.hotspots, self.motion)
        self.threshold_var.set(str(self.contact_threshold_kpa))
        if preset_name is not None:
            self.preset_name = preset_name
        if self._playback_metadata is not None:
            self._current_analysis_settings = self.current_settings()
        if self.recorder is not None:
            self.add_event("algorithm_settings_changed", payload={
                "settings": self.current_settings(), "preset": self.preset_name})
        self._update_stats()
        self._update_plot()

    def add_annotation(self, annotation_type, note="", before_note="", after_note=""):
        payload = {"type": annotation_type, "before_note": before_note,
                   "after_note": after_note}
        if annotation_type == "Known hotspot" and self.roi is not None:
            payload["roi"] = list(self.roi)
            payload["comparison"] = compare_hotspot_roi(self.roi, self.hotspots.active)
        return self.add_event("annotation", note, payload)

    def show_reposition_difference(self, record):
        self.plot_type_var.set("2D Heatmap")
        self.data_mode_var.set("Calibrated pressure")
        self.reference_grid = record["before"]["grid"].copy()
        self.comparison_grid = record["after"]["grid"].copy()
        self.reference_mode = "pressure"
        self.difference_var.set(True)
        self._build_plot()

    def add_event(self, kind, note="", payload=None):
        playback = self.source is not None and getattr(self.source, "is_playback", False)
        timestamp = (self.frame_timestamp if playback and self.frame_timestamp is not None
                     else time.time())
        frame_index = self.recorder.frame_count if self.recorder is not None else None
        event = self.timeline.add(timestamp, kind, note, payload, frame_index)
        if self.recorder is not None:
            self.recorder.events.append(event)
        return event

    def _recording_initial_state(self):
        if self.frame is None or self.raw_grid is None:
            return None
        state = initial_session_state(
            self.frame_timestamp, self.source_var.get(), self.raw_grid,
            self.frame["pressure"], self.pressure_calibration,
            self.calibration.baseline, self.contact_threshold_kpa, self.hotspots)
        state["initial_hotspots"] = [
            {"id": track["id"], "observed_before_recording_s": track["total_active_s"],
             "started_before_recording": True, "true_duration_s": None}
            for track in self.hotspots.active]
        return state

    def _analysis_grid(self):
        key = DATA_MODES[self.data_mode_var.get()]
        grid = self.frame[key]
        if grid is None:
            return self.frame["baseline_subtracted"], "relative sensor value"
        return grid, "kPa" if key == "pressure" else "relative sensor value"

    def _begin_roi_selection(self):
        if self.plot_type_var.get() != "2D Heatmap":
            self.plot_type_var.set("2D Heatmap")
            self._build_plot()
        self.selecting_roi = True
        self.roi_corner = None
        self.status_var.set("Select the first ROI corner on the 2D heatmap")

    def _clear_roi(self):
        self.roi = None
        self.temporal.clear_roi()
        self.roi_corner = None
        self.selecting_roi = False
        self.roi_history.clear()
        self._update_plot()
        self._refresh_analysis()

    def _refresh_analysis(self):
        if self.analysis_window is not None and self.analysis_window.window.winfo_exists():
            self.analysis_window.refresh()

    def _refresh_calibration(self, kind=None):
        self.temporal.invalidate()
        self.hotspots.invalidate()
        self.motion.invalidate()
        if kind is not None and self.recorder is not None:
            self.add_event(kind, payload={"calibration": self.pressure_calibration.to_dict()})
        self.cell_history.clear()
        self.roi_history.clear()
        if self.frame is not None:
            update_pressure(self.frame, self.calibration, self.pressure_calibration)
        self._update_stats()
        self._update_plot()
        self._refresh_analysis()

    def _capture_baseline(self):
        if self.pre_baseline_grid is None:
            self.status_var.set("No frame yet - can't calibrate")
            return
        if not np.all(np.isfinite(self.pre_baseline_grid)):
            self.status_var.set("Cannot capture tare while a sensor value is missing or invalid")
            return
        self.calibration.capture_baseline(self.pre_baseline_grid)
        self.temporal.invalidate()
        self.hotspots.invalidate()
        self.motion.invalidate()
        if self.recorder is not None:
            self.add_event("tare_captured", payload={"baseline": self.calibration.baseline.tolist()})
        self.frame["baseline_subtracted"] = self.calibration.apply_baseline(self.pre_baseline_grid)
        self.frame["display"] = self.frame["baseline_subtracted"].copy()
        self.current_grid = self.frame["display"]
        self._refresh_calibration()
        self.status_var.set("Tare captured: current reading set as zero")

    def _view_baseline(self):
        if self.calibration.baseline is None:
            self.status_var.set("No tare baseline captured yet")
            return
        window = tk.Toplevel(self.root)
        window.title("Tare baseline")
        figure = Figure(figsize=(5, 5))
        axes = figure.add_subplot()
        image = axes.imshow(self.calibration.baseline, cmap=HEATMAP_COLORS, aspect="auto")
        figure.colorbar(image, ax=axes, label="Baseline value")
        FigureCanvasTkAgg(figure, master=window).get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _reset(self):
        had_baseline = self.calibration.baseline is not None
        self.calibration.reset()
        if had_baseline:
            self.temporal.invalidate()
            self.hotspots.invalidate()
            self.motion.invalidate()
        if had_baseline and self.recorder is not None:
            self.add_event("baseline_cleared")
        self.auto_scale_var.set(False)
        if self.frame is not None:
            self.frame["baseline_subtracted"] = self.frame["filtered"].copy()
            self.frame["display"] = self.frame["baseline_subtracted"].copy()
            self.current_grid = self.frame["display"]
        self._refresh_calibration()

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

    def _toggle_hotspots(self):
        if self.show_hotspots_var.get():
            if not self.pressure_calibration.is_complete:
                self.status_var.set("Complete pressure calibration to show hotspots")
            else:
                self.data_mode_var.set("Calibrated pressure")
                self._change_data_mode()
        self._update_plot()

    # ---- recording

    def _toggle_recording(self):
        if self.recorder is None:
            name = simpledialog.askstring("Record session", "Session name:", parent=self.root)
            if not name:
                return
            source_name = f"{self.source_var.get()} ({self.device_var.get()})"
            metadata = {
                "pressure_units": "kPa",
                "pressure_calibration": self.pressure_calibration.to_dict(),
                "calibration_file": str(self.pressure_calibration.path) if self.pressure_calibration.path else None,
                "baseline_processed": self.calibration.baseline.tolist() if self.calibration.baseline is not None else None,
                "processing_mode": self.active_mode.label,
                "processing_parameter": self.mode_param_var.get() if self.active_mode.param_label else None,
                "contact_threshold_kpa": self.contact_threshold_kpa,
                "cell_width_mm": CELL_WIDTH_MM,
                "cell_height_mm": CELL_HEIGHT_MM,
                "temporal": self.temporal.settings(),
                "hotspots": self.hotspots.settings(),
                "movement": self.motion.settings(),
                "state_events_version": 1,
                "application_config_version": 6,
                "preset": self.preset_name,
                "experiment": self.experiment_info.copy(),
                "validation_match_window_s": self.validation_match_window_s,
                "session_initial": self.session_state,
                "recording_initial": self._recording_initial_state(),
            }
            self.recorder = Recorder(name, source=source_name, metadata=metadata)
            self.add_event("recording_started")
            self.record_button.configure(text="Stop recording")
        else:
            frame_count = self.recorder.frame_count
            self.add_event("recording_stopped")
            self.recorder.metadata["temporal_final"] = self.temporal.settings()
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
            quality = self.source.quality.snapshot()
            if quality["malformed"] > self._last_malformed:
                self.temporal.invalidate()
                self.hotspots.invalidate()
                self.motion.invalidate()
                self.add_event("malformed_data_period", str(quality["malformed"] - self._last_malformed))
                self._last_malformed = quality["malformed"]
            if quality["dropped"] > self._last_dropped:
                self.temporal.invalidate()
                self.hotspots.invalidate()
                self.motion.invalidate()
                self._last_dropped = quality["dropped"]
            if hasattr(self.source.latest, "take_all"):
                grids = self.source.latest.take_all()
            else:
                grid = self.source.latest.take()
                grids = [] if grid is None else [grid]
            for item in grids:
                grid, sample_time = item if isinstance(item, tuple) else (item, None)
                self._handle_new_frame(grid, sample_time)
            self._check_connection_health()
            if (self.diagnostics_window is not None and self.diagnostics_window.window.winfo_exists()
                    and time.time() - self._last_diagnostics_draw >= 0.5):
                self._last_diagnostics_draw = time.time()
                self.diagnostics_window.refresh()
            if (self.temporal_window is not None and self.temporal_window.window.winfo_exists()
                    and time.time() - self._last_temporal_draw >= 0.5):
                self._last_temporal_draw = time.time()
                self.temporal_window.refresh()
            if time.time() - self._last_feature_draw >= 0.5:
                self._last_feature_draw = time.time()
                if self.hotspot_window is not None and self.hotspot_window.window.winfo_exists():
                    self.hotspot_window.refresh()
                if self.motion_window is not None and self.motion_window.window.winfo_exists():
                    self.motion_window.refresh()
        self._update_fps()
        self.root.after(POLL_INTERVAL_MS, self._poll)

    def _handle_new_frame(self, grid, sample_time=None):
        self.last_frame_time = time.time()
        if sample_time is not None and self.frame_timestamp is not None and sample_time <= self.frame_timestamp:
            self.cell_history.clear()
            self.cop_history.clear()
            self.roi_history.clear()
            self.sensor_health.reset()
            if self._playback_metadata is not None:
                self._reset_playback_state()
            else:
                self.temporal.reset_all()
                self.hotspots.reset()
                self.motion.reset()
            self.add_event("playback_loop_reset")
        self.frame_timestamp = self.last_frame_time if sample_time is None else sample_time
        if self._playback_metadata is not None:
            self._apply_playback_state_events(self.frame_timestamp)
        self._fps_frame_count += 1

        frame = process_frame(grid, self.active_mode, self.calibration, self.pressure_calibration)
        self.frame = frame
        self.raw_grid = frame["raw"]
        self.pre_baseline_grid = frame["filtered"]
        self.current_grid = frame["display"]
        self.temporal.update(frame["pressure"], self.frame_timestamp)
        if self.temporal.last_event is not None:
            self.add_event(self.temporal.last_event)
        hotspot_events = self.hotspots.update(frame["pressure"], self.frame_timestamp,
                                              self.temporal, self.cell_area_m2)
        for kind, track_id in hotspot_events:
            self.add_event(kind, f"Hotspot {track_id}")
        motion_events = self.motion.update(frame["pressure"], self.frame_timestamp,
                                           self.contact_threshold_kpa, self.cell_area_m2,
                                           self.hotspots.active, self.temporal)
        for kind, payload in motion_events:
            self.add_event(kind, payload=payload)
        if self.session_state is None:
            self.session_state = initial_session_state(
                self.frame_timestamp, self.source_var.get(), self.raw_grid,
                frame["pressure"], self.pressure_calibration,
                self.calibration.baseline, self.contact_threshold_kpa, self.hotspots)

        self.sensor_health.update(self.raw_grid, self.frame_timestamp,
                                  baseline=self.calibration.baseline, pressure=frame["pressure"],
                                  contact_threshold_kpa=self.contact_threshold_kpa,
                                  pressure_calibration=self.pressure_calibration)
        self.calibration.update(self.current_grid)
        self._update_stats()
        if self.display_cop[0] is not None:
            self.cop_history.append((self.frame_timestamp, *self.display_cop))
        self._add_history_sample()
        self._add_roi_history_sample()
        if self.recorder is not None:
            if self.recorder.metadata.get("recording_initial") is None:
                self.recorder.metadata["recording_initial"] = self._recording_initial_state()
            self.recorder.add_frame(self.raw_grid, timestamp=self.frame_timestamp)
        if self._playback_metadata is not None:
            self._playback_frame_index += 1
        web.update_grid(self.current_grid)

        # drawing is expensive (esp. with numbers on) - cap the rate
        now = time.time()
        if not self.paused_var.get() and now - self._last_draw_time >= DRAW_INTERVAL_S:
            self._last_draw_time = now
            self._update_plot()
        if now - self._last_analysis_draw >= 0.5:
            self._last_analysis_draw = now
            self._refresh_analysis()

    def _update_fps(self):
        now = time.time()
        if now - self._fps_last_check >= 1.0:
            self.fps_var.set(f"FPS: {self._fps_frame_count / (now - self._fps_last_check):.1f}")
            self._fps_frame_count = 0
            self._fps_last_check = now

    def _check_connection_health(self):
        """Flag a stale connection, and optionally auto-reconnect"""
        if getattr(self.source, "is_playback", False) and self.source.paused:
            self.connection_var.set("Playback paused")
            return
        if self.last_frame_time is None:
            return
        stale_for = time.time() - self.last_frame_time
        if stale_for < STALE_AFTER_S:
            if self._source_was_stale:
                self.add_event("source_reconnected")
                self._source_was_stale = False
            self.connection_var.set("Connected")
            return

        self.connection_var.set(f"No data for {stale_for:.0f}s")
        if not self._source_was_stale:
            self.add_event("source_disconnected")
            self._source_was_stale = True
            self.temporal.invalidate()
            self.hotspots.invalidate()
            self.motion.invalidate()
        if self.auto_reconnect_var.get() and time.time() - self.last_reconnect_attempt >= RECONNECT_INTERVAL_S:
            self.last_reconnect_attempt = time.time()
            self.connection_var.set(f"No data for {stale_for:.0f}s - reconnecting...")
            self._connect()

    def _update_plot(self):
        if self.frame is None:
            return
        key = DATA_MODES[self.data_mode_var.get()]
        grid = self.frame[key]
        pressure_unavailable = grid is None
        if pressure_unavailable:
            grid = np.zeros((TOTAL_ROWS, TOTAL_COLS))
        elif key != "pressure":
            grid = np.where(np.isfinite(grid) & (grid > self.signal_noise_threshold), grid, 0.0)
        finite_values = grid[np.isfinite(grid)]
        difference = (self.difference_var.get() and self.reference_grid is not None
                      and self.reference_mode == key and not pressure_unavailable)
        if difference:
            comparison = self.comparison_grid if self.comparison_grid is not None else grid
            reference = self.reference_grid
            if key != "pressure":
                comparison = np.where(
                    np.isfinite(comparison) & (comparison > self.signal_noise_threshold), comparison, 0.0)
                reference = np.where(
                    np.isfinite(reference) & (reference > self.signal_noise_threshold), reference, 0.0)
            grid = comparison - reference
            finite_difference = grid[np.isfinite(grid)]
            limit = max(1.0, float(np.max(np.abs(finite_difference)))) if finite_difference.size else 1.0
            vmin, vmax = -limit, limit
        elif key == "pressure":
            vmin = 0.0
            vmax = (max(1.0, float(finite_values.max())) if finite_values.size else 1.0
                    ) if self.calibration.auto else PRESSURE_DISPLAY_MAX_KPA
        else:
            vmin, vmax = self.calibration.vmin, self.calibration.vmax
        plot_grid = interpolate_grid(grid, self.interpolation_method, self.display_scale)

        if self.plot_type_var.get() == "3D Surface":
            self.axes.clear()
            cols, rows = np.meshgrid(np.linspace(0, TOTAL_COLS - 1, plot_grid.shape[1]),
                                     np.linspace(0, TOTAL_ROWS - 1, plot_grid.shape[0]))
            self.axes.plot_surface(
                cols, rows, -plot_grid,
                cmap="coolwarm_r" if difference else HEATMAP_COLORS.reversed(),
                vmin=-vmax, vmax=-vmin,
            )
            self.axes.set_zlim(-vmax, -vmin)
            self.axes.set_zlabel("-kPa" if key == "pressure" else "Negative sensor value")
        else:
            for collection in list(self.axes.collections):
                collection.remove()
            self.image.set_data(plot_grid)
            self.image.set_extent((-0.5, TOTAL_COLS - 0.5, TOTAL_ROWS - 0.5, -0.5))
            self.image.set_clim(vmin, vmax)
            self.image.set_cmap("coolwarm" if difference else HEATMAP_COLORS)
            self.axes.set_xlim(-0.5, TOTAL_COLS - 0.5)
            self.axes.set_ylim(TOTAL_ROWS - 0.5, -0.5)
            if self.show_contours and not pressure_unavailable and not difference:
                configured = self.pressure_contour_levels if key == "pressure" else self.relative_contour_levels
                levels = ([level for level in configured if finite_values.min() < level < finite_values.max()]
                          if finite_values.size else [])
                if levels:
                    x = np.linspace(0, TOTAL_COLS - 1, plot_grid.shape[1])
                    y = np.linspace(0, TOTAL_ROWS - 1, plot_grid.shape[0])
                    self.axes.contour(x, y, plot_grid, levels=levels, colors="#333333",
                                      linewidths=0.6, alpha=0.6)
            if (self.show_hotspot_threshold and key == "pressure" and not difference and
                    finite_values.size and finite_values.min() < self.hotspots.activate_kpa < finite_values.max()):
                x = np.linspace(0, TOTAL_COLS - 1, plot_grid.shape[1])
                y = np.linspace(0, TOTAL_ROWS - 1, plot_grid.shape[0])
                self.axes.contour(x, y, plot_grid, levels=[self.hotspots.activate_kpa],
                                  colors="purple", linewidths=0.8, linestyles="dashed")
            if self.show_boundary and self.frame["pressure"] is not None:
                mask = contact_mask(self.frame["pressure"], self.contact_threshold_kpa)
                if mask.any() and not mask.all():
                    self.axes.contour(np.arange(TOTAL_COLS), np.arange(TOTAL_ROWS), mask.astype(float),
                                      levels=[0.5], colors="blue", linewidths=0.8, alpha=0.6)
            for label in self.hotspot_labels:
                label.remove()
            self.hotspot_labels = []
            if self.show_hotspots_var.get() and self.hotspots.data_valid and not difference and key == "pressure":
                for track in self.hotspots.active:
                    mask = np.zeros((TOTAL_ROWS, TOTAL_COLS), dtype=float)
                    for row, col in track["cells"]:
                        mask[row, col] = 1
                    if not mask.all():
                        self.axes.contour(np.arange(TOTAL_COLS), np.arange(TOTAL_ROWS), mask,
                                          levels=[0.5], colors="red" if track["persistent"] else "orange",
                                          linewidths=1.3)
                    row, col = track["centroid"]
                    label = self.axes.text(col, row, f"#{track['id']} {track['active_s']:.0f}s",
                                           color="black", fontsize=8, ha="center", va="center",
                                           bbox={"facecolor": "white", "alpha": 0.65, "edgecolor": "none"})
                    self.hotspot_labels.append(label)
            if self.roi_patch is not None:
                self.roi_patch.remove()
                self.roi_patch = None
            if self.roi is not None:
                row0, row1, col0, col1 = self.roi
                self.roi_patch = Rectangle((col0 - 0.5, row0 - 0.5), col1 - col0 + 1,
                                           row1 - row0 + 1, fill=False, edgecolor="blue", linewidth=1.5)
                self.axes.add_patch(self.roi_patch)
            if self.selected_cell is not None:
                self.selected_marker.set_data([self.selected_cell[1]], [self.selected_cell[0]])
            if self.cop_var.get() and self.display_cop[0] is not None:
                self.cop_marker.set_data([self.display_cop[0]], [self.display_cop[1]])
            else:
                self.cop_marker.set_data([], [])
            if self.cell_labels is not None:
                for row in range(TOTAL_ROWS):
                    for col in range(TOTAL_COLS):
                        value = grid[row, col]
                        self.cell_labels[row][col].set_text(f"{value:.1f}" if key == "pressure" else f"{value:.0f}")
        self.canvas.draw_idle()

        if self.recorder is not None:
            elapsed = time.time() - self.recorder.started_at
            prefix = f"Recording '{self.recorder.name}' - {elapsed:.0f}s, {self.recorder.frame_count} frames   "
        else:
            prefix = ""
        if pressure_unavailable:
            status = f"Pressure calibration incomplete ({self.pressure_calibration.calibrated_count}/{TOTAL_ROWS * TOTAL_COLS} cells)"
        else:
            unit = " kPa" if key == "pressure" else ""
            valid = grid[np.isfinite(grid)]
            status = (f"avg {valid.mean():.1f}{unit}   max {valid.max():.1f}{unit}   min {valid.min():.1f}{unit}"
                      if valid.size else "No valid sensor values")
        self.status_var.set(prefix + ("Difference vs reference | " if difference else "") + status)

    def _update_stats(self):
        if self.frame is None:
            self.display_cop = (None, None)
            return

        key = DATA_MODES[self.data_mode_var.get()]
        selected_grid = self.frame[key]
        if selected_grid is None:
            self.display_cop = (None, None)
        elif key == "pressure":
            self.display_cop = weighted_center(selected_grid, self.contact_threshold_kpa)
        else:
            self.display_cop = weighted_center(selected_grid, self.signal_noise_threshold)

        if self.frame is None or self.frame["pressure"] is None:
            count = self.pressure_calibration.calibrated_count
            self.pressure_status_var.set(f"Calibrate {TOTAL_ROWS * TOTAL_COLS - count} more cells for pressure statistics")
            self.peak_var.set("Peak: -")
            self.mean_var.set("Mean contact: -")
            self.area_var.set("Contact area: -")
            self.force_var.set("Force: -")
            x, y = self.display_cop
            self.cop_text_var.set(
                f"CoP (relative): x={x:.1f}, y={y:.1f} cells" if x is not None else "CoP (relative): -")
            self.stats = None
            return

        self.stats = pressure_statistics(self.frame["pressure"], self.contact_threshold_kpa,
                                         self.cell_area_m2)
        self.pressure_status_var.set("Calibrated pressure")
        self.peak_var.set(f"Peak: {self.stats['peak_kpa']:.1f} kPa")
        mean = self.stats["mean_kpa"]
        self.mean_var.set(f"Mean contact: {mean:.1f} kPa" if mean is not None else "Mean contact: -")
        count = self.stats["contact_cells"]
        area = self.stats["contact_area_m2"]
        self.area_var.set(f"Contact area: {area * 10_000:.1f} cm² ({count} cells)" if area is not None
                          else f"Contact area: {count} cells")
        force = self.stats["force_n"]
        self.force_var.set(f"Force: {force:.1f} N" if force is not None else "Force: set cell dimensions")
        x, y = self.display_cop
        label = "CoP" if key == "pressure" else "CoP (relative)"
        self.cop_text_var.set(f"{label}: x={x:.1f}, y={y:.1f} cells" if x is not None else f"{label}: -")

    def _on_plot_click(self, event):
        if self.plot_type_var.get() != "2D Heatmap" or event.inaxes != self.axes:
            return
        if event.xdata is None or event.ydata is None:
            return
        row, col = round(event.ydata), round(event.xdata)
        if not (0 <= row < TOTAL_ROWS and 0 <= col < TOTAL_COLS):
            return
        if self.selecting_roi:
            if self.roi_corner is None:
                self.roi_corner = (row, col)
                self.status_var.set("Select the opposite ROI corner")
            else:
                first_row, first_col = self.roi_corner
                self.roi = (min(first_row, row), max(first_row, row),
                            min(first_col, col), max(first_col, col))
                self.roi_corner = None
                self.selecting_roi = False
                self.roi_history.clear()
                self._add_roi_history_sample()
                self._refresh_analysis()
                self._update_plot()
            return
        self._select_cell(row, col)

    def _select_cell(self, row, col):
        self.selected_cell = (row, col)
        self.selected_cell_var.set(f"Cell: row {row}, column {col}")
        self.cell_history.clear()
        self._add_history_sample()
        self._open_history()
        self._update_plot()

    def _add_history_sample(self):
        if self.selected_cell is None or self.frame is None:
            return
        row, col = self.selected_cell
        sample = {"time": self.frame_timestamp}
        for key in DATA_MODES.values():
            grid = self.frame[key]
            sample[key] = None if grid is None else float(grid[row, col])
        if self.frame["pressure"] is not None:
            cell = self.temporal.cell(row, col)
            sample.update(exposure=cell["exposure"], burden=cell["burden"],
                          relief_state=cell["state_code"])
        self.cell_history.append(sample)
        self._update_selected_details()
        if time.time() - self._last_history_draw >= 0.2:
            self._update_history_plot()

    def _add_roi_history_sample(self):
        if self.roi is None or self.frame is None:
            return
        grid, _unit = self._analysis_grid()
        row0, row1, col0, col1 = self.roi
        values = grid[row0:row1 + 1, col0:col1 + 1]
        valid = values[np.isfinite(values)]
        if valid.size:
            self.roi_history.append({"time": self.frame_timestamp,
                                     "mean": float(valid.mean()), "peak": float(valid.max()),
                                     "pressure_mean": None if self.frame["pressure"] is None else float(np.nanmean(self.frame["pressure"][row0:row1 + 1, col0:col1 + 1])),
                                     "exposure_mean": self.temporal.roi(self.roi)["mean_exposure"],
                                     "burden_mean": self.temporal.roi(self.roi)["mean_burden"],
                                     "relieved_fraction": self.temporal.roi(self.roi)["relieved_fraction"]})

    def _update_selected_details(self):
        if self.history_window is None or not self.history_window.winfo_exists():
            return
        if self.selected_cell is None or self.frame is None:
            self.history_detail_var.set("Select a cell on the 2D heatmap")
            return
        row, col = self.selected_cell
        health = self.sensor_health.cell(row, col)
        baseline = None if self.calibration.baseline is None else self.calibration.baseline[row, col]
        pressure = self.frame["pressure"]

        def show(value):
            return "-" if value is None or not np.isfinite(value) else f"{value:.2f}"

        self.history_detail_var.set(
            f"Received {show(self.frame['raw'][row, col])} | processed {show(self.frame['filtered'][row, col])} | "
            f"tare {show(baseline)} | baseline-subtracted {show(self.frame['baseline_subtracted'][row, col])} | "
            f"pressure {show(None if pressure is None else pressure[row, col])} kPa\n"
            f"Recent raw mean {show(health['mean'])} | variance {show(health['variance'])} | "
            f"noise {show(health['noise'])} | drift {show(health['drift'])} | "
            f"calibrated {'yes' if health['calibrated'] else 'no'} | {health['state']}"
        )

    def _open_history(self):
        if self.history_window is not None and self.history_window.winfo_exists():
            self.history_window.lift()
            self._update_history_plot()
            return
        self.history_window = tk.Toplevel(self.root)
        self.history_window.title("Selected cell history")
        self.history_window.geometry("700x420")
        self.history_detail_var = tk.StringVar()
        ttk.Label(self.history_window, textvariable=self.history_detail_var,
                  wraplength=680, padding=8).pack(fill=tk.X)
        self.history_figure = Figure(figsize=(6, 3))
        self.history_axes = self.history_figure.add_subplot()
        self.history_canvas = FigureCanvasTkAgg(self.history_figure, master=self.history_window)
        self.history_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._update_selected_details()
        self._update_history_plot()

    def _update_history_plot(self):
        if self.history_window is None or not self.history_window.winfo_exists():
            return
        key = DATA_MODES[self.data_mode_var.get()]
        samples = [item for item in self.cell_history if item[key] is not None]
        self.history_axes.clear()
        if samples:
            start = samples[0]["time"]
            self.history_axes.plot([item["time"] - start for item in samples],
                                   [item[key] for item in samples], color="green")
        self.history_axes.set_xlabel("Time since selection (s)")
        self.history_axes.set_ylabel("Pressure (kPa)" if key == "pressure" else "Relative sensor value")
        if self.selected_cell is not None:
            self.history_axes.set_title(f"Row {self.selected_cell[0]}, column {self.selected_cell[1]}")
        self.history_figure.tight_layout()
        self.history_canvas.draw_idle()
        self._last_history_draw = time.time()

    # ---- lifecycle

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self.recorder is not None:
            self.add_event("recording_stopped")
            self.recorder.metadata["temporal_final"] = self.temporal.settings()
            self.recorder.save()
        if self.source is not None:
            self.source.stop()
        if self.web_server is not None:
            self.web_server.stop()
        self.root.destroy()
