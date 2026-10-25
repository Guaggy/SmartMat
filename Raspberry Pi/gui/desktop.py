"""The Tkinter desktop app"""

import copy
import threading
import time
import webbrowser
from pathlib import Path
import tkinter as tk
from collections import deque
from tkinter import filedialog, simpledialog, ttk

import numpy as np
import config as app_config
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 - registers the 3D projection

import app_settings
from branding import COMPANY_NAME, CONTACT_EMAIL, DISCLAIMER, PRODUCT_NAME, VERSION, WEBSITE_URL
from paths import resource_path
from config import (
    VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT,
    STALE_AFTER_S, RECONNECT_INTERVAL_S,
    CONTACT_THRESHOLD_KPA,
    PRESSURE_DISPLAY_MAX_KPA, HISTORY_MAX_FRAMES,
    DISPLAY_SCALE, PRESSURE_CONTOUR_LEVELS_KPA, RELATIVE_CONTOUR_LEVELS,
    VALIDATION_MATCH_WINDOW_S, INDEX_UPDATE_INTERVAL_S,
)
from general import load_mat_names, mat_labels, save_mat_names
from processing.calibration import (Calibration, IndividualCalibration, PressureCalibration, UniformCalibration,
                                    apply_profile, cell_size_mm, configured_mat_size, load_profile,
                                    parse_mat_size, profile_roi, profile_size_mm, save_profile)
from processing.session_events import STATE_EVENTS, apply_state_event, event_is_due
from processing.session_state import initial_session_state
from processing.settings import apply_settings, capture_settings, default_settings
from processing.display import interpolate_grid
from processing.export import write_snapshot_csv
from processing.frames import orient_grid, process_frame, update_pressure
from processing.modes import MODES
from processing.recording import RECORDINGS_DIR, Recorder, load_session
from processing.sensor_health import SensorHealth
from processing.hotspots import HotspotTracker
from processing.motion import MotionAnalyzer
from processing.occupancy import OccupancyDetector
from processing.roi import mask_to_cells
from processing.indices import NEAR, OK, OVER, IndexMonitor
from processing.signals import SIGNALS, Context, read_signal
from processing.temporal import TemporalAnalysis
from processing.timeline import EventTimeline
from processing.statistics import (contact_mask, load_estimate_text, pressure_statistics, saturated_cells,
                                    weighted_center)
from sources.mqtt_source import MqttSource
from sources.serial_source import PROFILES, RAW_CAPTURE_S, TEXT_PROFILE, SerialSource, list_ports
from sources.simulated_source import SCENARIOS, SimulatedSource

DEMO_DEVICE = "Demo: seat take 1"  # entry in the Simulated device list, played from the bundled sample
DEMO_RECORDING = "samples/seat_take1.json"
from gui import theme
from gui.blit import Blitter
from gui.calibration_window import CalibrationWindow
from gui.analysis_window import AnalysisWindow
from gui.diagnostics_window import DiagnosticsWindow
from gui.temporal_window import TemporalWindow
from gui.hotspot_window import HotspotWindow
from gui.motion_window import MotionWindow
from gui.expression_window import ExpressionWindow
from gui.indices_window import IndicesWindow
from gui.roi_window import RoiWindow
from gui.page import Page, is_shown, tab_actions
from gui.annotation_window import AnnotationWindow
from gui.engineering_window import EngineeringWindow
from gui.help_window import HelpWindow
from processing.validation import compare_hotspot_roi



def _ui_number(name, default, low):
    """A numeric UI knob from config.py (an older config.py may not have it; a bad value falls back to the default)"""
    try:
        value = float(getattr(app_config, name, default))
    except (TypeError, ValueError):
        return default
    return value if value >= low else default


POLL_INTERVAL_MS = 50  # how often the GUI checks for a new frame
UI_IDLE_POLL_MS = int(_ui_number("UI_IDLE_POLL_MS", 250, 50))  # poll rate with no source connected
UI_MAX_FPS = _ui_number("UI_MAX_FPS", 5, 0.5)  # cap the heatmap redraw rate - drawing is the expensive part
DRAW_INTERVAL_S = 1 / UI_MAX_FPS
TOOL_REFRESH_S = _ui_number("UI_TOOL_REFRESH_S", 1.0, 0.1)  # how often the open tool tabs (analysis, temporal...) redraw
UI_BLIT = bool(getattr(app_config, "UI_BLIT", True))  # redraw only the heatmap, not axes/ticks/colorbar (gui/blit.py)
DATA_MODES = {
    "Raw / received": "raw",
    "Processed": "filtered",
    "Baseline subtracted": "baseline_subtracted",
    "Calibrated pressure": "pressure",
}
# DesktopApp.data_modes adds the cell signals ("signal:<name>") and map indices ("index:<name>") to these

# Status cells: text and the palette token of the cell colour. Muted: these sit on screen all day
OCCUPANCY_LABELS = {
    True: ("Patient detected", "ok"),
    False: ("No patient", "idle"),
    None: ("Patient: unknown", "line"),
}

INDEX_CHIP_COLORS = {"inactive": "line", OK: "idle", NEAR: "warn", OVER: "bad"}
INDEX_EVENTS = {OK: "index_cleared", NEAR: "index_near_threshold", OVER: "index_over_threshold"}
INDEX_OUTLINE_COLOR = "#8a4f9e"  # distinct from hotspot red/orange and the blue contact boundary

READOUT_NAME_WIDTH = 15  # characters: the readout names line up in one column
READOUT_VALUE_WRAP = 140  # pixels
READOUT_WRAP = 230        # pixels, a full-width line in the readouts column
DEFAULT_SHAPE = (app_config.TOTAL_ROWS, app_config.TOTAL_COLS)  # config.py's own size, used by Serial/Simulated


class DesktopApp:
    """Owns the window, the active data source, and the current grid"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"{PRODUCT_NAME} {VERSION}")
        self.root.geometry("1150x750")
        self.theme_var = tk.StringVar(value=theme.apply_theme(self.root, app_settings.theme()))

        self.source = None
        self._rotation = 0                 # degrees, as last applied (rotation_var is the control)
        self._grid_rotation = 0            # the rotation the current grid was shaped with (cell_size_mm's axes)
        self._shown_capture = None         # last raw capture result reported in the status line
        self.recorder = None
        self.mat_names = load_mat_names()  # chip id -> nickname
        self._mats = {}                    # chip id -> (rows, cols), as last shown in the device list
        self._mat_ids = {}                 # device-list label -> chip id
        self._status = {}                  # chip id -> "online" / "offline", as last shown in the device list
        self._discovery = None             # MqttSource that only listens for mats' metadata
        self._discovery_error = None       # its last connection problem already shown in the status bar
        self.calibration = Calibration()
        self.pressure_calibration = PressureCalibration.default()
        self.sensor_health = SensorHealth()
        self.temporal = TemporalAnalysis()
        self.hotspots = HotspotTracker()
        self.motion = MotionAnalyzer()
        self.occupancy = OccupancyDetector()
        self.indices = IndexMonitor()
        self.index_history = {}      # summary index name -> recent (time, value) for its trend
        self.index_chips = {}        # index name -> status-bar label
        self.indices_window = None
        self.expression_window = None
        self._live_indices = None    # live definitions kept aside while a recording plays
        self._last_index_update = 0.0
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
        self.reposition_window = None
        self.calibration_window = None
        self.help_window = None
        self.about_window = None
        self._current_analysis_settings = None
        self._replay_policy = "Reproduce recording"
        self._demo_playback = False        # the bundled demo recording is playing (labelled DEMO)
        self.timeline = EventTimeline()
        self.temporal_window = None
        self._source_was_stale = False
        self._last_malformed = 0
        self._last_dropped = 0
        self.contact_threshold_kpa = CONTACT_THRESHOLD_KPA
        self.signal_noise_threshold = float(getattr(app_config, "SIGNAL_NOISE_THRESHOLD", 0.0))
        self.mat_size_mm = configured_mat_size()  # (width, height) sensing size of the connected mat, or None
        self._user_size_mm = None  # the part of mat_size_mm that is the user's (typed or from the profile): the only part saved
        self._pending_mat_size = None  # entered while no real mat was connected; the next Connect applies it
        self.frame = None
        self.raw_grid = None
        self.current_grid = None
        self.pre_baseline_grid = None
        self.cell_labels = None
        self.selected_cell = None
        self.cell_history = deque(maxlen=HISTORY_MAX_FRAMES)
        self.cop_history = deque(maxlen=HISTORY_MAX_FRAMES)
        self.roi = None  # boolean mask of the selected cells, or None
        self.roi_history = deque(maxlen=HISTORY_MAX_FRAMES)
        self.history_window = None
        self.analysis_window = None
        self.roi_window = None
        self.calibration_windows = []
        self.diagnostics_window = None
        self.plot_options_window = None
        self._last_history_draw = 0.0
        self._last_analysis_draw = 0.0
        self._last_diagnostics_draw = 0.0
        self._last_temporal_draw = 0.0
        self.stats = None
        self.display_cop = (None, None)
        self.interpolation_method = "Linear"
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
        self._reconnect_since = None  # time the source went stale while auto-reconnect keeps retrying
        self._last_draw_time = 0.0
        self._capture_enabled = None   # last state given to the capture button
        self._occupancy_shown = None   # (text, colour) last put on the patient chip
        self.blitter = None            # set by _build_plot for the 2D heatmap
        self._fps_frame_count = 0
        self._fps_last_check = time.time()

        self._advanced = set()  # widgets hidden in Simple view (see _apply_view)
        self._rows = []         # (parent, [(widget, pack options)]) in pack order, to put hidden widgets back
        self._build_header()
        # Layout B toolbar: rows of labelled groups (Source / Calibrate, Record / Display / Tools / Options)
        self.toolbar = ttk.Frame(self.root, padding=(8, 4, 8, 6))
        self.toolbar.pack(side=tk.TOP, fill=tk.X)
        ttk.Separator(self.root).pack(side=tk.TOP, fill=tk.X)
        self._build_connection_bar()
        self._build_actions_bar()
        self._build_data_bar()
        self._build_options_bar()
        self._remember_rows(self.root)
        self._remember_tree(self.toolbar)
        self._build_status_bar()
        self._refresh_devices()

        # Layout B: the live view is the first tab; the tool windows open as closable tabs after it (gui/page.py)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", lambda _event: self._tab_changed())
        self.tab_actions = tab_actions(self.notebook, self._pop_out)  # Pop out / Close at the strip's end
        self.content = ttk.Frame(self.notebook)
        self.notebook.add(self.content, text="Live")
        self._advanced_tab = None  # the tab that was selected when Simple view hid the tab strip
        self._tools = {}           # window attribute -> factory(parent), for Pop out

        self._build_about_panel()
        self._build_plot_area()
        self._build_plot()
        self._apply_view()
        self._poll()

    # ---- window layout

    def _build_header(self):
        """Brand bar: logo lockup, the Simple / Advanced switch (Simple hides what _adv registered), the
        Light / Dark switch and About"""
        self.header = ttk.Frame(self.root, style="Header.TFrame", padding=(8, 4))
        self.header.pack(side=tk.TOP, fill=tk.X)
        try:
            self.root.iconphoto(True, tk.PhotoImage(file=str(resource_path("assets/icon_256.png"))))
        except tk.TclError:
            pass  # no icon file: default window icon
        self._header_logos = {}
        for mode in theme.MODES:
            try:
                self._header_logos[mode] = tk.PhotoImage(
                    file=str(resource_path(f"assets/logo_lockup_{mode}.png"))).subsample(2)
            except tk.TclError:  # no logo file: text header
                pass
        self.header_logo = ttk.Label(self.header, style="Header.TLabel", font=theme.font("title", "bold"),
                                     text=f"{PRODUCT_NAME} - by {COMPANY_NAME}")
        self.header_logo.pack(side=tk.LEFT)
        self._show_header_logo()

        switch = ttk.Frame(self.header, style="Header.TFrame")
        switch.pack(side=tk.RIGHT)
        ttk.Label(switch, text="View", style="HeaderMuted.TLabel").pack(side=tk.LEFT, padx=(0, 2))
        self.view_var = tk.StringVar(
            value="Simple" if getattr(app_config, "START_IN_SIMPLE_MODE", True) else "Advanced")
        for label in ("Simple", "Advanced"):
            ttk.Radiobutton(switch, text=label, value=label, variable=self.view_var, style="Header.Toolbutton",
                            command=self._apply_view).pack(side=tk.LEFT)
        ttk.Separator(switch, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=4)
        for mode in theme.MODES:
            ttk.Radiobutton(switch, text=mode.title(), value=mode, variable=self.theme_var,
                            style="Header.Toolbutton", command=self._set_theme).pack(side=tk.LEFT)
        ttk.Separator(switch, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=4)
        ttk.Button(switch, text="About", command=self._open_about, style="Header.TButton").pack(side=tk.LEFT)

    def _show_header_logo(self):
        logo = self._header_logos.get(self.theme_var.get())
        self.header_logo.configure(image=logo or "", compound="image" if logo else "none")

    def _set_theme(self):
        """Light / Dark switch: restyle everything that is open now, and remember the choice"""
        mode = theme.apply_theme(self.root, self.theme_var.get())
        self._show_header_logo()
        self._update_occupancy(force=True)
        self._update_index_chips()
        # the heatmap ramp fades into the theme's own background (the figure itself was restyled in place;
        # rebuilding it here would leave the new canvas at the wrong size until the next window resize)
        if self.frame is not None:
            self._update_plot()
        elif self.plot_type_var.get() == "2D Heatmap":
            self.image.set_cmap(theme.heatmap_cmap())
        try:
            app_settings.save_theme(mode)
        except OSError as error:
            self.status_var.set(f"Could not save the theme: {error}")

    def _open_about(self):
        if self.about_window is not None and self.about_window.winfo_exists():
            self.about_window.lift()
            return
        window = self.about_window = tk.Toplevel(self.root)
        window.title(f"About {PRODUCT_NAME}")
        window.resizable(False, False)
        frame = ttk.Frame(window, padding=16)
        frame.pack()
        ttk.Label(frame, text=PRODUCT_NAME, font=theme.font("big", "bold")).pack(anchor="w")
        ttk.Label(frame, text=f"Version {VERSION}").pack(anchor="w")
        ttk.Label(frame, text=f"by {COMPANY_NAME}").pack(anchor="w", pady=(0, 8))
        for text, url in ((WEBSITE_URL, WEBSITE_URL), (CONTACT_EMAIL, f"mailto:{CONTACT_EMAIL}")):
            self._link(frame, text, url)
        ttk.Label(frame, text=DISCLAIMER, wraplength=340).pack(anchor="w", pady=(12, 0))

    @staticmethod
    def _link(parent, text, url, **options):
        """A label that opens url in the browser when clicked, styled as a link"""
        link = ttk.Label(parent, text=text, style="Link.TLabel", cursor="hand2", **options)
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda _event: webbrowser.open(url))
        return link

    def _adv(self, widget):
        """Mark a widget as Advanced-only (hidden in Simple view); returns it"""
        self._advanced.add(widget)
        return widget

    def _remember_rows(self, parent):
        """Record parent's packed children in order, so _apply_view can put hidden ones back in place"""
        self._rows.append((parent, [(child, {key: value for key, value in child.pack_info().items() if key != "in"})
                                    for child in parent.pack_slaves()]))

    def _apply_view(self):
        """Show or hide the Advanced-only widgets. Only geometry changes: no variable, source or calibration is touched"""
        simple = self.view_var.get() == "Simple"
        for parent, order in self._rows:
            for index, (widget, options) in enumerate(order):
                if widget not in self._advanced:
                    continue
                if simple:
                    widget.pack_forget()
                elif not widget.winfo_manager():
                    later = next((w for w, _ in order[index + 1:] if w not in self._advanced), None)
                    if later is not None:
                        where = {"before": later}
                    elif index:
                        where = {"after": order[index - 1][0]}
                    else:
                        where = {"before": parent.pack_slaves()[0]}  # still packed siblings (e.g. the plot)
                    widget.pack(**options, **where)
        if simple:  # Live only: the open tabs stay, just out of sight
            if str(self.notebook.cget("style")) != "Bare.TNotebook":
                self._advanced_tab = self.notebook.select()
            self.notebook.configure(style="Bare.TNotebook")
            self.notebook.select(self.content)
        else:
            self.notebook.configure(style="TNotebook")
            if self._advanced_tab in self.notebook.tabs():
                self.notebook.select(self._advanced_tab)
        self._place_capture_button()

    def _place_capture_button(self):
        """Serial only, and only in Advanced view"""
        if self.source_var.get() == "Serial" and self.view_var.get() != "Simple":
            self.capture_button.pack(side=tk.LEFT, padx=(0, 4), after=self.export_button)
        else:
            self.capture_button.pack_forget()

    def _remember_tree(self, widget):
        """_remember_rows for widget and every frame inside it (the toolbar nests rows and groups)"""
        self._remember_rows(widget)
        for child in widget.winfo_children():
            if child.winfo_class() == "TFrame":
                self._remember_tree(child)

    def _toolbar_row(self, advanced=False):
        row = ttk.Frame(self.toolbar)
        row.pack(side=tk.TOP, fill=tk.X, pady=1)
        return self._adv(row) if advanced else row

    def _group(self, row, title):
        """A labelled group of controls in a toolbar row, after a hairline when it is not the first; returns
        the frame to put the controls in"""
        if row.pack_slaves():
            ttk.Separator(row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)
        ttk.Label(row, text=title, style="Muted.TLabel", width=9).pack(side=tk.LEFT)
        group = ttk.Frame(row)
        group.pack(side=tk.LEFT)
        return group

    def _build_connection_bar(self):
        self.source_row = self._toolbar_row()
        bar = self._group(self.source_row, "Source")
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
        # the brand bar names the selected mat
        ttk.Label(self.header, textvariable=self.device_var, style="HeaderMuted.TLabel").pack(side=tk.LEFT,
                                                                                             padx=(16, 0))
        # Serial only: shown by _refresh_devices, packed between the device menu and Rename
        self.protocol_label = ttk.Label(bar, text="Protocol:")
        self.protocol_var = tk.StringVar(value=TEXT_PROFILE)
        self.protocol_menu = ttk.Combobox(bar, textvariable=self.protocol_var, state="readonly",
                                          values=list(PROFILES), width=22)
        self.protocol_menu.bind("<<ComboboxSelected>>", lambda _event: self.baud_var.set(self._baud_text()))
        self.rename_button = ttk.Button(bar, text="Rename...", command=self._rename_mat)
        self.rename_button.pack(side=tk.LEFT, padx=(0, 8))
        self._adv(self.rename_button)

        ttk.Button(bar, text="Connect", command=self._connect, style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bar, text="Disconnect", command=self._disconnect).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bar, text="Load demo recording", command=self._load_demo).pack(side=tk.LEFT, padx=(0, 12))

        # Own row, shown by _show_playback only while a recording plays (it does not fit next to the source)
        self.playback_row = ttk.Frame(self.toolbar)
        bar = self._group(self.playback_row, "Playback")
        self.playback_speed_label = ttk.Label(bar, text="Speed:")
        self.playback_speed_label.pack(side=tk.LEFT, padx=(0, 3))
        self.playback_speed_var = tk.StringVar(value="1x")
        self.playback_speed_menu = ttk.Combobox(
            bar, textvariable=self.playback_speed_var, state="readonly",
            values=["0.25x", "0.5x", "1x", "2x", "5x"], width=6,
        )
        self.playback_speed_menu.pack(side=tk.LEFT, padx=(0, 12))
        self.playback_speed_menu.bind("<<ComboboxSelected>>", lambda _event: self._set_playback_speed())
        self.replay_settings_var = tk.StringVar(value="Reproduce recording")
        self.replay_settings_menu = ttk.Combobox(
            bar, textvariable=self.replay_settings_var, state="readonly", width=30,
            values=["Reproduce recording", "Re-analyze with current settings"])
        self.replay_settings_menu.pack(side=tk.LEFT, padx=(0, 12))
        self.replay_settings_menu.bind("<<ComboboxSelected>>", lambda _event: self._connect())

        self.connection_var = tk.StringVar(value="Not connected")  # source health, shown in the status bar

    def _show_playback(self, show):
        if show:
            self.playback_row.pack(side=tk.TOP, fill=tk.X, pady=1, after=self.source_row)
        else:
            self.playback_row.pack_forget()

    def _build_actions_bar(self):
        row = self._toolbar_row()
        bar = self._group(row, "Calibrate")
        self._adv(ttk.Button(bar, text="Reset", command=self._reset)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bar, text="Tare", command=self._capture_baseline).pack(side=tk.LEFT, padx=(0, 4))
        self._adv(ttk.Button(bar, text="View tare", command=self._view_baseline)).pack(side=tk.LEFT, padx=(0, 4))
        self.mat_size_button = ttk.Button(bar, text="Mat size...", command=self._set_mat_size)
        self.mat_size_button.pack(side=tk.LEFT, padx=(0, 12))

        # Orientation of live data, applied at ingest (not to recordings, which are saved already oriented)
        self._adv(ttk.Label(bar, text="Rotate:")).pack(side=tk.LEFT)
        self.rotation_var = tk.StringVar(value="0")
        rotation_menu = ttk.Combobox(bar, textvariable=self.rotation_var, state="readonly",
                                     values=["0", "90", "180", "270"], width=4)
        self._adv(rotation_menu).pack(side=tk.LEFT, padx=(0, 8))
        rotation_menu.bind("<<ComboboxSelected>>", lambda _event: self._orientation_changed())
        self.mirror_h_var = self._checkbox(bar, "Mirror H", self._orientation_changed, advanced=True)
        self.mirror_v_var = self._checkbox(bar, "Mirror V", self._orientation_changed, advanced=True)

        bar = self._group(row, "Record")
        self.record_button = ttk.Button(bar, text="Record", command=self._toggle_recording, style="Accent.TButton")
        self.record_button.pack(side=tk.LEFT, padx=(0, 4))
        self.export_button = ttk.Button(bar, text="Export snapshot...", command=self._export_snapshot)
        self.export_button.pack(side=tk.LEFT, padx=(0, 4))
        # Serial only, Advanced only: placed by _place_capture_button
        self.capture_button = ttk.Button(bar, text="Capture raw (5 s)", command=self._capture_raw, state="disabled")

    def _build_data_bar(self):
        bar = self._group(self._toolbar_row(), "Display")
        ttk.Label(bar, text="Plot:").pack(side=tk.LEFT)
        self.plot_type_var = tk.StringVar(value="2D Heatmap")
        plot_menu = ttk.Combobox(
            bar, textvariable=self.plot_type_var, state="readonly",
            values=["2D Heatmap", "3D Surface"], width=12,
        )
        plot_menu.pack(side=tk.LEFT, padx=(0, 12))
        plot_menu.bind("<<ComboboxSelected>>", lambda _event: self._build_plot())

        ttk.Label(bar, text="Data:").pack(side=tk.LEFT)
        self.data_mode_var = tk.StringVar(value="Baseline subtracted")
        self._data_mode_shown = "Baseline subtracted"  # last mode actually applied (to fall back to)
        self.data_modes = self._build_data_modes()
        self.data_menu = ttk.Combobox(bar, textvariable=self.data_mode_var, state="readonly",
                                      values=list(self.data_modes), width=21)
        self.data_menu.pack(side=tk.LEFT, padx=(0, 12))
        self.data_menu.bind("<<ComboboxSelected>>", lambda _event: self._change_data_mode())

        self.threshold_var = tk.StringVar(value=str(self.contact_threshold_kpa))

        self._adv(ttk.Label(bar, text="Mode:")).pack(side=tk.LEFT)
        self.mode_var = tk.StringVar(value=self.active_mode.label)
        mode_menu = ttk.Combobox(
            bar, textvariable=self.mode_var, state="readonly",
            values=[mode.label for mode in MODES], width=16,
        )
        self._adv(mode_menu).pack(side=tk.LEFT, padx=(0, 4))
        mode_menu.bind("<<ComboboxSelected>>", lambda _event: self._select_mode())

        self.mode_param_label_var = tk.StringVar(value="")
        self._adv(ttk.Label(bar, textvariable=self.mode_param_label_var)).pack(side=tk.LEFT)
        self.mode_param_var = tk.StringVar()
        self.mode_param_entry = ttk.Entry(bar, textvariable=self.mode_param_var, width=6)
        self._adv(self.mode_param_entry).pack(side=tk.LEFT, padx=(0, 12))
        self.mode_param_entry.bind("<Return>", lambda _event: self._apply_mode_param())
        self.mode_param_entry.bind("<FocusOut>", lambda _event: self._apply_mode_param())
        self._select_mode()

        self._adv(ttk.Label(bar, text="Ignore signal <=")).pack(side=tk.LEFT)
        self.noise_threshold_var = tk.StringVar(value=str(self.signal_noise_threshold))
        noise_entry = ttk.Entry(bar, textvariable=self.noise_threshold_var, width=6)
        self._adv(noise_entry).pack(side=tk.LEFT, padx=(2, 12))
        noise_entry.bind("<Return>", lambda _event: self._apply_noise_threshold())
        noise_entry.bind("<FocusOut>", lambda _event: self._apply_noise_threshold())

        self.cop_var = self._checkbox(bar, "Show CoP", self._update_plot, advanced=True)

    def _build_data_modes(self):
        """Dropdown label -> frame key: the base maps, the cell signals, and each map index"""
        modes = dict(DATA_MODES)
        for name, signal in SIGNALS.items():
            if signal.level == "cell" and name != "pressure":  # pressure is "Calibrated pressure"
                modes[signal.label] = f"signal:{name}"
        for definition in self.indices.definitions:
            if definition["layer"] == "map":
                modes[f"Index: {definition['name']}"] = f"index:{definition['name']}"
        return modes

    def _refresh_data_modes(self):
        """The index list changed: relist the dropdown, and leave a map index that no longer exists"""
        self.data_modes = self._build_data_modes()
        self.data_menu.configure(values=list(self.data_modes))
        if self.data_mode_var.get() not in self.data_modes:
            self.data_mode_var.set("Baseline subtracted")
            self._change_data_mode()

    def _data_key(self):
        return self.data_modes[self.data_mode_var.get()]

    def _base_key(self):
        """The frame key for everything computed from the shown data (CoP, ROI, analysis): the selected
        map, or calibrated pressure when a derived signal/index map is shown"""
        key = self._data_key()
        return key if key in DATA_MODES.values() else "pressure"

    def _derived_grid(self, key):
        """Grid of a signal/index map, NaN where unknown; None without a complete pressure calibration"""
        if self.frame is None or self.frame["pressure"] is None:
            return None
        kind, _, name = key.partition(":")
        if kind == "signal":
            grid = read_signal(name, self._index_context())
        else:  # evaluated from the same Context, on the index update interval
            grid = self.indices.values.get(name)
        return grid if isinstance(grid, np.ndarray) and grid.shape == self.frame["pressure"].shape else None

    @staticmethod
    def _data_unit(key):
        """Colorbar / axis label of a data mode"""
        kind, _, name = key.partition(":")
        if kind == "signal":
            signal = SIGNALS[name]
            return f"{signal.label} ({signal.unit})" if signal.unit else signal.label
        if kind == "index":
            return f"Index: {name} (relative to reference)"
        return "Pressure (kPa)" if key == "pressure" else "Relative sensor value"

    def _build_options_bar(self):
        """Tool windows, then the on/off checkboxes; both rows are Advanced-only"""
        bar = self._group(self._toolbar_row(advanced=True), "Tools")
        for text, command in (("Pressure calibration...", self._open_calibration),
                              ("Plot options...", self._open_plot_options), ("ROI...", self._open_roi),
                              ("Analysis...", self._open_analysis), ("Diagnostics...", self._open_diagnostics),
                              ("Temporal...", self._open_temporal), ("Hotspots...", self._open_hotspots),
                              ("Movement...", self._open_motion), ("Indices...", self._open_indices),
                              ("Expression...", self._open_expression),
                              ("Engineering...", self._open_engineering), ("Help", self._open_help)):
            ttk.Button(bar, text=text, command=command).pack(side=tk.LEFT, padx=(0, 2))

        bar = self._group(self._toolbar_row(advanced=True), "Options")
        self.auto_scale_var = self._checkbox(bar, "Auto-scale", self._toggle_calibration)
        self.paused_var = self._checkbox(bar, "Pause", self._toggle_pause)
        self.numbers_var = self._checkbox(bar, "Show numbers", self._toggle_numbers)
        self.auto_reconnect_var = self._checkbox(bar, "Auto-reconnect", default=True)
        self.show_hotspots_var = self._checkbox(bar, "Show hotspots", self._toggle_hotspots, default=True)

    def _checkbox(self, parent, text, command=None, default=False, advanced=False):
        """Add one checkbox to parent, return its BooleanVar"""
        var = tk.BooleanVar(value=default)
        kwargs = {"command": command} if command else {}
        button = ttk.Checkbutton(parent, text=text, variable=var, **kwargs)
        button.pack(side=tk.LEFT, padx=(0, 8))
        if advanced:
            self._adv(button)
        return var

    def _build_status_bar(self):
        """Bottom line: patient state, index states, source health, the live status text and the disclaimer"""
        self.status_var = tk.StringVar(value="Not connected")
        self._notice, self._notice_until = "", 0.0  # one-off message that the live status line must not wipe
        status_bar = ttk.Frame(self.root, style="Status.TFrame")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Separator(self.root).pack(side=tk.BOTTOM, fill=tk.X)
        self.occupancy_label = tk.Label(status_bar, padx=10)
        self.occupancy_label.pack(side=tk.LEFT, padx=(4, 2), pady=2)
        self.index_chip_bar = self._adv(ttk.Frame(status_bar, style="Status.TFrame"))
        self.index_chip_bar.pack(side=tk.LEFT)
        self._build_index_chips()
        self._update_occupancy()
        ttk.Label(status_bar, textvariable=self.connection_var, style="Status.TLabel",
                  padding=(8, 2)).pack(side=tk.LEFT)
        ttk.Label(status_bar, text=DISCLAIMER.split(".")[0], style="StatusMuted.TLabel",
                  padding=(8, 2)).pack(side=tk.RIGHT)
        ttk.Label(status_bar, textvariable=self.status_var, style="StatusMuted.TLabel",
                  padding=(8, 2)).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._remember_rows(status_bar)

    def _readout(self, parent, variable):
        """One aligned row showing a "Name: value" variable as a muted name column and a value column; returns
        the row (the variable itself is unchanged)"""
        row = ttk.Frame(parent)
        row.pack(anchor="w", fill=tk.X)
        name, value = tk.StringVar(), tk.StringVar()
        ttk.Label(row, textvariable=name, style="Muted.TLabel", width=READOUT_NAME_WIDTH).pack(side=tk.LEFT,
                                                                                               anchor="n")
        ttk.Label(row, textvariable=value, wraplength=READOUT_VALUE_WRAP).pack(side=tk.LEFT, anchor="n")

        def split(*_args):
            head, colon, tail = variable.get().partition(": ")
            name.set(head if colon else "")
            value.set(tail if colon else head)
        variable.trace_add("write", split)
        split()
        return row

    def _build_about_panel(self):
        """Readouts column: live pressure as aligned label/value rows, then facts about the mat and the app"""
        sidebar = ttk.Frame(self.content, padding=(12, 8, 8, 8))
        sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Separator(self.content, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y)

        stats_panel = ttk.Frame(sidebar)
        stats_panel.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(stats_panel, text="Live pressure", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
        self.pressure_status_var = tk.StringVar(value="Default pressure calibration active")
        self._adv(ttk.Label(stats_panel, textvariable=self.pressure_status_var, style="Muted.TLabel",
                            wraplength=READOUT_WRAP)).pack(anchor="w", pady=(0, 4))
        self.peak_var = tk.StringVar(value="Peak: -")
        self.mean_var = tk.StringVar(value="Mean contact: -")
        self.area_var = tk.StringVar(value="Contact area: -")
        self.force_var = tk.StringVar(value="Force: -")
        self.load_var = tk.StringVar(value="Estimated load: -")
        self.hotspots_var = tk.StringVar(value="Hotspots: -")
        self.cop_text_var = tk.StringVar(value="CoP: -")
        self.selected_cell_var = tk.StringVar(value="Cell: click the 2D plot")
        for variable in (self.peak_var, self.mean_var, self.area_var, self.force_var, self.load_var,
                         self.hotspots_var, self.cop_text_var, self.selected_cell_var):
            row = self._readout(stats_panel, variable)
            if variable not in (self.peak_var, self.load_var, self.hotspots_var):
                self._adv(row)  # Simple view keeps peak, load and hotspots
            if variable is self.load_var:
                self._load_row = row
        # Amber note under the load line; packed only while cells are at the sensor limit (kept in Simple view)
        self.saturation_var = tk.StringVar()
        self.saturation_label = ttk.Label(stats_panel, textvariable=self.saturation_var, wraplength=READOUT_WRAP,
                                          style="Warn.TLabel")
        self._remember_rows(stats_panel)

        panel = self._adv(ttk.Frame(sidebar))
        panel.pack(side=tk.TOP, fill=tk.X, pady=(12, 0))
        self._remember_rows(sidebar)
        ttk.Separator(panel).pack(fill=tk.X, pady=(0, 8))
        ttk.Label(panel, text="About", style="Heading.TLabel").pack(anchor="w", pady=(0, 4))

        self.fps_var = tk.StringVar(value="FPS: -")
        self._readout(panel, self.fps_var)

        self._info_line(panel, "ESP32", header=True, top_pad=6)
        self.grid_info_var = tk.StringVar(value=f"Grid: {app_config.TOTAL_ROWS} x {app_config.TOTAL_COLS}")
        self._readout(panel, self.grid_info_var)
        self.baud_var = tk.StringVar(value=self._baud_text())
        self._readout(panel, self.baud_var)
        self.model_var = tk.StringVar()  # the connected mat's preset name, empty without one
        self._readout(panel, self.model_var)
        self._info_line(panel, f"Value range: {VALUE_MIN_DEFAULT}-{VALUE_MAX_DEFAULT}")

        self._info_line(panel, "App", header=True, top_pad=8)
        self._info_line(panel, f"Stale after: {STALE_AFTER_S}s")
        self._info_line(panel, f"Reconnect every: {RECONNECT_INTERVAL_S}s")
        self.cell_info_var = tk.StringVar()
        self._readout(panel, self.cell_info_var)
        self._update_cell_info()

    def _baud_text(self):
        return f"Baud rate: {PROFILES[self.protocol_var.get()]['baud']}"

    def _info_line(self, parent, text, header=False, top_pad=0):
        if header:
            ttk.Label(parent, text=text, font=theme.font("small", "bold")).pack(anchor="w", pady=(top_pad, 0))
        else:
            self._readout(parent, tk.StringVar(parent, value=text)).pack_configure(pady=(top_pad, 0))

    def _refresh_devices(self):
        """Repopulate the device dropdown, keeping the current selection if still valid"""
        source = self.source_var.get()
        previous = self.device_var.get()
        self.rename_button.state(["!disabled" if source == "MQTT" else "disabled"])
        if source != "Serial":
            self.protocol_label.pack_forget()
            self.protocol_menu.pack_forget()

        if source == "Serial":
            self.protocol_label.pack(side=tk.LEFT, after=self.device_menu)
            self.protocol_menu.pack(side=tk.LEFT, padx=(0, 8), after=self.protocol_label)
            self._port_devices = {port.label: port.device for port in list_ports()}  # label -> device
            values = list(self._port_devices)
            default = values[0] if values else ""
        elif source == "MQTT":
            if self._discovery is None:
                try:
                    discovery = MqttSource()  # no mat selected: only listens for mats' metadata
                    discovery.start()
                    self._discovery = discovery
                except Exception as error:
                    self.status_var.set(f"Could not look for mats: {error}")
            selected = self._mat_ids.get(previous)
            demo_prefix = getattr(app_config, "DEMO_PREFIX", "demo-")  # an older config.py may lack it
            self._mat_ids = {label + (" (offline)" if self._status.get(chip_id) == "offline" else "")
                             + (" (demo)" if demo_prefix and chip_id.startswith(demo_prefix) else ""): chip_id
                             for label, chip_id in mat_labels(self._mats, self.mat_names).items()}
            values = list(self._mat_ids)
            # keep the same mat selected even if it was just renamed
            default = next((label for label, chip_id in self._mat_ids.items() if chip_id == selected),
                           values[0] if values else "")
        else:
            values = [f"Synthetic: {name}" for name in SCENARIOS] + [DEMO_DEVICE]
            if RECORDINGS_DIR.exists():
                values += [path.name for path in RECORDINGS_DIR.iterdir()
                           if path.suffix in (".csv", ".json")]
            default = values[0]

        self._place_capture_button()
        self.device_menu.configure(values=values)
        self.device_var.set(previous if previous in values else default)

    def _sync_mats(self):
        """Relist the MQTT devices when the broker has reported a new or changed mat"""
        error = getattr(self._discovery, "error", None)
        if error != self._discovery_error:  # shown once per change, and not over a mat's own status
            if self.source is None and (error or self.status_var.get() == self._discovery_error):
                self.status_var.set(error or "")
            self._discovery_error = error
        if self._discovery is not None and (self._discovery.mats != self._mats
                                            or self._discovery.status != self._status):
            self._mats = dict(self._discovery.mats)
            self._status = dict(self._discovery.status)
            if self.source_var.get() == "MQTT":
                self._refresh_devices()

    def restart_discovery(self):
        """Drop the device-list listener and the mats it knew; the next _refresh_devices builds a new
        one with the saved broker settings (Engineering > Connection > Save)."""
        if self._discovery is not None:
            # stop() joins the paho loop and can block for seconds with an unreachable broker: not on the GUI
            # thread. Nothing reads the old source once self._discovery is replaced, so it cannot feed the new list.
            threading.Thread(target=self._discovery.stop, daemon=True).start()
            self._discovery = None
        if self.status_var.get() == self._discovery_error:
            self.status_var.set("")
        self._mats, self._status, self._discovery_error = {}, {}, None
        self._refresh_devices()

    def _rename_mat(self):
        chip_id = self._mat_ids.get(self.device_var.get())
        if chip_id is None:
            self.status_var.set("Select a mat to rename")
            return
        name = simpledialog.askstring(
            "Rename mat", f"Name for mat {chip_id} (leave empty to show the chip ID):",
            initialvalue=self.mat_names.get(chip_id, ""), parent=self.root)
        if name is None:
            return
        if name.strip():
            self.mat_names[chip_id] = name.strip()
        else:
            self.mat_names.pop(chip_id, None)
        try:
            save_mat_names(self.mat_names)
        except OSError as error:
            self.status_var.set(f"Could not save mat name: {error}")
        self._refresh_devices()

    def _build_plot_area(self):
        """Holds the reference buttons directly above the (rebuilt) plot canvas"""
        self.plot_area = ttk.Frame(self.content, padding=(8, 6, 4, 4))
        self.plot_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        bar = self._adv(ttk.Frame(self.plot_area, padding=(0, 0, 0, 4)))
        bar.pack(side=tk.TOP, fill=tk.X)
        self._remember_rows(self.plot_area)
        ttk.Button(bar, text="Capture reference", command=self._capture_reference).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(bar, text="Show reference", variable=self.difference_var,
                        command=self._toggle_difference).pack(side=tk.LEFT)

    def _build_plot(self):
        """Build the matplotlib figure for the currently selected plot type"""
        if hasattr(self, "canvas"):
            self.canvas.get_tk_widget().destroy()

        self.cell_labels = None
        self.cop_marker = None
        self.selected_marker = None
        self.hotspot_labels = []
        self.figure = theme.figure(figsize=(6, 6))
        if self.plot_type_var.get() == "3D Surface":
            self.axes = self.figure.add_subplot(projection="3d")
        else:
            self.axes = self.figure.add_subplot()
            self.image = self.axes.imshow(
                np.zeros((app_config.TOTAL_ROWS, app_config.TOTAL_COLS)),
                cmap="coolwarm" if self.difference_var.get() else theme.heatmap_cmap(),
                vmin=VALUE_MIN_DEFAULT, vmax=VALUE_MAX_DEFAULT,
                aspect="auto",
            )
            unit = self._data_unit(self._data_key())
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
                     for col in range(app_config.TOTAL_COLS)]
                    for row in range(app_config.TOTAL_ROWS)
                ]

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.plot_area)
        self.canvas.mpl_connect("button_press_event", self._on_plot_click)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        # the 2D heatmap is blitted (gui/blit.py); the 3D surface is rebuilt each time, so it always draws in full
        self.blitter = Blitter(self.canvas) if UI_BLIT and self.plot_type_var.get() != "3D Surface" else None
        # the plot is not drawn while its tab/window is hidden: catch up as soon as it shows again
        self.canvas.get_tk_widget().bind("<Map>", lambda _event: self._plot_shown(), add="+")

        if self.frame is not None:
            self._update_plot()

    # ---- source lifecycle

    def _apply_grid_shape(self, rows, cols, force=False):
        """Switch the app to a mat's grid size; everything sized to the old grid starts over
        (force: start over even at the same size, e.g. after a mirror)"""
        if not force and (rows, cols) == (app_config.TOTAL_ROWS, app_config.TOTAL_COLS):
            return
        if self.recorder is not None:
            self._toggle_recording()  # a recording cannot span two grid sizes: save it at the old one
        app_config.TOTAL_ROWS, app_config.TOTAL_COLS = rows, cols
        self._reset_calibration()
        for mode in MODES:
            mode.reset()
        self.temporal.reset_all()
        self.hotspots.reset()
        self.motion.reset()
        self.occupancy.reset()
        self._reset_indices()
        self.sensor_health.reset()
        self.frame = self.raw_grid = self.current_grid = self.pre_baseline_grid = None
        self.reference_grid = self.comparison_grid = None
        self.difference_var.set(False)
        self.selected_cell = None
        self.selected_cell_var.set("Cell: click the 2D plot")
        self.roi = None
        self.cell_history.clear()
        self.cop_history.clear()
        self.roi_history.clear()
        self.grid_info_var.set(f"Grid: {rows} x {cols}")
        self._update_stats()
        self._build_plot()
        if self.roi_window is not None and self.roi_window.window.winfo_exists():  # grid changed, even if hidden
            self.roi_window.reset()

    def _reset_calibration(self):
        """No tare, default pressure calibration (the startup one if it fits this grid)"""
        self.calibration.baseline = None
        try:
            self.pressure_calibration.individual = IndividualCalibration.default()
        except ValueError:  # the configured startup calibration file is for another grid size
            self.pressure_calibration.individual = IndividualCalibration()
        self.pressure_calibration.uniform = UniformCalibration()
        self.pressure_calibration.use("individual")

    def _orientation(self):
        return {"rotation": self._rotation, "mirror_h": self.mirror_h_var.get(),
                "mirror_v": self.mirror_v_var.get()}

    @property
    def cell_size_mm(self):
        """(width, height) mm of one cell of the oriented grid, or None; follows mat size, grid and rotation.
        Uses the rotation the grid was shaped with: a turn during playback or with no source reshapes nothing."""
        return cell_size_mm(self.mat_size_mm, app_config.TOTAL_ROWS, app_config.TOTAL_COLS, self._grid_rotation)

    @property
    def cell_area_m2(self):
        """Area of one cell in m2, or None when the mat size is not set (the one source for every window)"""
        size = self.cell_size_mm
        return None if size is None else size[0] * size[1] / 1_000_000

    def _update_cell_info(self):
        size = self.cell_size_mm
        self._show(self.cell_info_var, "Cell area: not configured" if size is None else
                               f"Cell: {size[0]:.1f} x {size[1]:.1f} mm")
        model = getattr(self.source, "model", None)
        vendor = getattr(self.source, "vendor", None)
        self._show(self.model_var, f"Mat: {vendor + ' ' if vendor else ''}{model}" if model else "")

    def _set_mat_size(self):
        """Ask for the mat's physical sensing size (outer edge of the first to the last sensing element)"""
        current = "" if self.mat_size_mm is None else f"{self.mat_size_mm[0]:g} x {self.mat_size_mm[1]:g}"
        text = simpledialog.askstring(
            "Mat size", "Sensing size of the whole mat in mm, width x height, outer edge of the first "
            "sensing element to the outer edge of the last (as built, before rotation).\n"
            "Used for area, force and the indicative load estimate. Empty = not set.",
            initialvalue=current, parent=self.root)
        if text is None:
            return
        try:
            self.mat_size_mm = self._user_size_mm = parse_mat_size(text)
        except ValueError as error:
            self._notify(f"Mat size not changed: {error}")
            return
        if self._profile_mat_id() is None:  # no real mat yet: keep it for the next Connect
            self._pending_mat_size = self.mat_size_mm
        self._save_profile()
        self._update_stats()

    def _profile_mat_id(self):
        """Real mats (Serial/MQTT) keep a profile; simulated data and recordings do not"""
        if self.source is None or isinstance(self.source, SimulatedSource):
            return None
        return getattr(self.source, "mat_id", None)

    def _save_profile(self):
        mat_id = self._profile_mat_id()
        if mat_id is None:
            return
        try:
            save_profile(mat_id, self.calibration.baseline, self.pressure_calibration, self._orientation(),
                         self._user_size_mm,  # a preset size is not written: later preset changes must still apply
                         self.roi)
        except OSError as error:
            self.status_var.set(f"Could not save the mat profile for {mat_id}: {error}")

    def _load_profile(self):
        """A real mat just connected: restore its orientation, tare and calibration, or start it clean.
        Applies the *oriented* shape first so the first live frame (_orient) does not reset it again."""
        mat_id = self._profile_mat_id()
        # new mats: the source's preset size (Maxrays MC266, or an MQTT meta), else the config default; a profile's own
        # size wins below. Only the user's size (typed, or already in the profile) is kept for saving.
        self._user_size_mm = None
        self.mat_size_mm = getattr(self.source, "default_size_mm", None) or configured_mat_size()
        self._grid_rotation = self._rotation  # every connect shapes (or, playback, sizes) the grid at the current rotation
        if mat_id is None:
            recorded = profile_size_mm({"size_mm": (self._playback_metadata or {}).get("mat_size_mm")})
            if recorded:  # the recording's own size (as built); its frames are already oriented
                turned = ((self._playback_metadata.get("orientation") or {}).get("rotation") in (90, 270)) \
                    != ((self._rotation // 90) % 2 == 1)  # cell_size_mm swaps on the app's current rotation
                self.mat_size_mm = recorded[::-1] if turned else recorded
            return ""
        profile = load_profile(mat_id)
        if profile is not None:
            self._user_size_mm = profile_size_mm(profile)  # the size is the mat's, whatever its grid
            self.mat_size_mm = self._user_size_mm or self.mat_size_mm
        rows, cols = self.source.shape
        if profile is not None:
            try:
                orientation = profile["orientation"]
                rotation = int(orientation["rotation"])
                oriented = [cols, rows] if (rotation // 90) % 2 else [rows, cols]
                if rotation not in (0, 90, 180, 270) or profile["grid_shape"] != oriented:
                    profile = None  # another grid size (e.g. firmware changed): start clean
            except (KeyError, TypeError, ValueError):
                profile = None
        if profile is not None:
            self._rotation = self._grid_rotation = rotation
            self.rotation_var.set(str(rotation))
            self.mirror_h_var.set(bool(orientation.get("mirror_h")))
            self.mirror_v_var.set(bool(orientation.get("mirror_v")))
        if (self._rotation // 90) % 2:
            rows, cols = cols, rows
        self._apply_grid_shape(rows, cols)
        self._reset_calibration()  # never inherit another mat's tare/calibration, even at the same size
        roi = None if profile is None else profile_roi(profile)
        if roi is not None or self.roi is not None:
            self.set_roi(roi)  # likewise the ROI: the mat's own, else none
        if profile is None:
            return f" | new mat profile {mat_id}"
        try:
            apply_profile(profile, self.calibration, self.pressure_calibration)
        except ValueError as error:
            return f" | mat profile {mat_id} ignored ({error})"
        return f" | mat profile {mat_id} restored"

    def _apply_pending_size(self, pending):
        """A size entered before Connect goes to the connecting real mat if its profile has none; else the profile wins"""
        mat_id = self._profile_mat_id()
        if pending is None or mat_id is None:
            return ""
        own = profile_size_mm(load_profile(mat_id))
        if own is None:
            self.mat_size_mm = self._user_size_mm = pending
            self._save_profile()
            return f" | mat size {pending[0]:g} x {pending[1]:g} mm applied"
        if own != pending:
            return f" | profile mat size {own[0]:g} x {own[1]:g} mm kept, entered size not used"
        return ""

    def _orientation_changed(self):
        """Rotate/mirror changed: cell positions moved, so the analysis state starts over like a new mat"""
        rotation = int(self.rotation_var.get())
        rows, cols = app_config.TOTAL_ROWS, app_config.TOTAL_COLS
        live = self.source is not None and not getattr(self.source, "is_playback", False)
        if ((rotation - self._rotation) // 90) % 2:
            rows, cols = cols, rows
        self._rotation = rotation
        if live:
            self._grid_rotation = rotation
            self._apply_grid_shape(rows, cols, force=True)
        self._update_cell_info()
        note = " 90/270 swaps rows and cols of a non-square mat." if rows != cols else ""
        self.status_var.set("Orientation applies to live data only; analysis state was reset, as when "
                            "switching mats." + note if live else
                            "Orientation applies to live sources (recordings are saved already oriented)." + note)

    def _orient(self, grid):
        """Orient a live grid; if its size no longer matches the app's grid (a 90/270 turn of a
        non-square mat, or a fresh connection), switch the app to it"""
        grid = orient_grid(grid, self._rotation, self.mirror_h_var.get(), self.mirror_v_var.get())
        if grid.shape != (app_config.TOTAL_ROWS, app_config.TOTAL_COLS):
            self._apply_grid_shape(*grid.shape)
        return grid

    def _capture_raw(self):
        """Tee the next RAW_CAPTURE_S seconds of the serial port's bytes to recordings/raw_<profile>_<time>.bin"""
        source = self.source
        if not isinstance(source, SerialSource) or source.capturing:
            return
        path = RECORDINGS_DIR / f"raw_{source.profile.split()[0].lower()}_{time.strftime('%Y%m%d_%H%M%S')}.bin"
        source.start_raw_capture(path)
        self.status_var.set(f"Capturing raw bytes for {RAW_CAPTURE_S:g} s to {path}")

    def _update_capture_button(self):
        """Enabled only while a Serial source is connected and no capture is running; reports a finished one"""
        source = self.source if isinstance(self.source, SerialSource) else None
        enabled = source is not None and not source.capturing
        if enabled != self._capture_enabled:  # a Tk call every poll otherwise
            self._capture_enabled = enabled
            self.capture_button.state(["!disabled" if enabled else "disabled"])
        result = source.capture_result if source is not None else None
        if result is not None and result is not self._shown_capture:
            self._shown_capture = result
            self.status_var.set(f"Raw capture failed: {result.error}" if result.error else
                                f"Raw capture: {result.path} ({result.size:,} bytes, {result.headers} x A5 5A)")

    def _connect(self):
        """Stop the current source and start the selected one"""
        self._close_calibration_windows()
        self._save_profile()  # the mat being left (switch or reconnect)
        pending_size, self._pending_mat_size = self._pending_mat_size, None
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
        self.occupancy.reset()
        self._reset_indices()
        self.session_state = None
        self.timeline = EventTimeline()
        self._show_playback(False)

        source_name = self.source_var.get()
        device = self.device_var.get()

        try:
            recording = None
            serial_source = None
            if source_name == "Simulated" and device and not device.startswith("Synthetic:"):
                path = resource_path(DEMO_RECORDING) if device == DEMO_DEVICE else RECORDINGS_DIR / device
                recording = load_session(path, with_timestamps=True, with_details=True)
            if source_name == "Serial":
                serial_source = SerialSource(self._port_devices.get(device, device), self.protocol_var.get())
            if source_name != "MQTT":
                # MQTT mats report their size after start(); a recording carries its own; Serial's profile does
                self._apply_grid_shape(*(serial_source.shape if serial_source else
                                         recording[0][0].shape if recording else DEFAULT_SHAPE))
            if serial_source:
                self.source = serial_source
            elif source_name == "MQTT":
                if device not in self._mat_ids:
                    raise ValueError("no mat selected (none has reported to the broker yet)")
                self.source = MqttSource(self._mat_ids[device])
            elif device.startswith("Synthetic:"):
                self.source = SimulatedSource(scenario=device.split(":", 1)[1].strip())
            elif not device:
                self.source = SimulatedSource()
            else:
                frames, timestamps, metadata, events = recording
                self.source = SimulatedSource(playback_frames=frames, playback_timestamps=timestamps,
                                              value_max=metadata.get("value_max", VALUE_MAX_DEFAULT),
                                              mat_id=metadata.get("mat_id") or "recording")
                self.timeline = EventTimeline(events)
                self._live_state = (self.calibration, self.pressure_calibration, self.temporal,
                                    self.hotspots, self.motion,
                                    self.active_mode.label, self.mode_param_var.get(),
                                    self.contact_threshold_kpa, self.preset_name,
                                    self.experiment_info.copy())
                self._current_analysis_settings = self.current_settings()
                self._live_indices = copy.deepcopy(self.indices.definitions)
                self._replay_policy = self.replay_settings_var.get()
                if self._replay_policy == "Re-analyze with current settings" and previous_analysis_settings:
                    self._current_analysis_settings = previous_analysis_settings
                self._playback_metadata = metadata
                self._recorded_state_events = [event for event in events if event.get("kind") in STATE_EVENTS]
                self._reset_playback_state()

            if getattr(self.source, "is_playback", False):
                self.source.set_playback_speed(float(self.playback_speed_var.get().rstrip("x")))
            self._show_playback(getattr(self.source, "is_playback", False))

            self.active_mode.reset()
            self.cell_history.clear()
            self.cop_history.clear()
            self.roi_history.clear()
            self.sensor_health.reset()
            self.source.start()
            if source_name == "MQTT":
                self._apply_grid_shape(*self.source.shape)  # start() only returns once the mat reported it
            profile_label = self._load_profile() + self._apply_pending_size(pending_size)
            self.last_frame_time = time.time()
            replay_label = f" | {self._replay_policy}" if getattr(self.source, "is_playback", False) else ""
            self._demo_playback = device == DEMO_DEVICE and source_name == "Simulated"
            if self._demo_playback:
                replay_label += " | DEMO: bundled sample recording, not live data"
            self.status_var.set(f"Connected via {source_name} ({device}){replay_label}{profile_label}")
            self._reconnect_since = None
        except Exception as error:
            self.source = None
            self._restore_live_state()
            self._applying_playback_event = False
            self.status_var.set(f"Could not connect: {error}")

    def _load_demo(self):
        """Play the bundled seat recording through the normal Simulated playback path"""
        self.source_var.set("Simulated")
        self._refresh_devices()
        self.device_var.set(DEMO_DEVICE)
        self._connect()

    def _disconnect(self):
        self._reconnect_since = None  # a manual Disconnect stops auto-reconnect retries
        self._close_calibration_windows()
        self._save_profile()
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
        self.occupancy.reset()
        self._reset_indices()
        self._show_playback(False)
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
        if self._live_indices is not None:
            self._set_indices(self._live_indices)
            self._live_indices = None
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
            settings["indices"] = metadata.get("indices", self._live_indices)  # older recording: keep yours
            self.preset_name = metadata.get("preset", "Recorded")
        self.experiment_info = metadata.get("experiment", {}).copy()
        self.contact_threshold_kpa = apply_settings(settings, self.temporal, self.hotspots, self.motion)
        self._set_indices(settings.get("indices", self._live_indices))
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
                recorded = (event.get("payload") or {}).get("settings", {})
                if event["kind"] == "algorithm_settings_changed" and "indices" in recorded:
                    self._set_indices(recorded["indices"])
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
        if self._data_key() not in DATA_MODES.values() and not self.pressure_calibration.is_complete:
            self.data_mode_var.set(self._data_mode_shown)
            self._notify("Signal and index maps need a complete pressure calibration - keeping the "
                         f"previous map ({self._data_mode_shown})")
            return
        self._data_mode_shown = self.data_mode_var.get()
        if self.difference_var.get() and self._data_key() != self.reference_mode:
            self.difference_var.set(False)
        self.roi_history.clear()
        self._update_stats()
        if self.frame is not None:
            self._build_plot()
        self._update_history_plot()
        self._refresh_analysis()

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
                                   values=["None", "Linear", "Smooth"], width=12)
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
        key = self._data_key()
        grid = self.frame.get(key)  # signal/index maps are not part of the frame
        if grid is None:
            self.status_var.set("This data mode is unavailable for a reference")
            return
        self.reference_grid = grid.copy()
        self.comparison_grid = None
        self.reference_mode = key
        self.difference_var.set(True)
        self._build_plot()

    def _toggle_difference(self):
        if self.difference_var.get() and (self.reference_grid is None or
                                          self.reference_mode != self._data_key()):
            self.difference_var.set(False)
            self.status_var.set("Capture a reference in the selected data mode first")
        else:
            self._build_plot()

    # ---- tool tabs

    def open_tool(self, attr, name, factory, replace=False):
        """Select the tool's tab (or raise its popped-out window), else build factory(notebook) into a new tab
        named name; replace=True closes an open one first. The window object is kept in self.<attr>."""
        window = getattr(self, attr)
        if window is not None and window.window.winfo_exists():
            if not replace:
                window.window.lift()
                return window
            window.window.destroy()
        window = factory(self.notebook)
        window.window.title(name)
        self._tools[attr] = factory
        setattr(self, attr, window)
        return window

    def _pop_out(self, page):
        """Rebuild the tool of a tab in its own window (closing that window just closes it)"""
        for attr, factory in self._tools.items():
            window = getattr(self, attr)
            if window is not None and window.window is page:
                page.destroy()
                setattr(self, attr, factory(self.root))
                return

    def _shown(self, window):
        """A tool window that is open and visible (a hidden tab is not refreshed)"""
        return window is not None and is_shown(window.window)

    def _tab_changed(self):
        """A selected tab is refreshed at once, so it never shows stale data"""
        for window in (self.analysis_window, self.diagnostics_window, self.temporal_window, self.hotspot_window,
                       self.motion_window, self.indices_window, self.expression_window, self.roi_window):
            if window is not None and isinstance(window.window, Page) and self._shown(window):
                window.refresh()

    def _open_calibration(self):
        mat_id = self._profile_mat_id()
        profile_text = (f"Mat profile: {mat_id} (saved automatically on disconnect, mat switch and close)"
                        if mat_id else "No mat profile: simulated data, a recording or not connected - "
                                       "changes here are not saved per mat")

        def build(parent):
            editor = CalibrationWindow(parent, self.pressure_calibration,
                                       lambda: self.pre_baseline_grid, self._refresh_calibration, profile_text,
                                       lambda: self.cell_area_m2)
            self.calibration_windows.append(editor)
            return editor
        self.open_tool("calibration_window", "Calibration", build)

    def _open_roi(self):
        self.open_tool("roi_window", "ROI", lambda parent: RoiWindow(parent, self))

    def _open_analysis(self):
        self.open_tool("analysis_window", "Analysis", lambda parent: AnalysisWindow(parent, self))

    def _open_diagnostics(self):
        self.open_tool("diagnostics_window", "Diagnostics", lambda parent: DiagnosticsWindow(
            parent, self.sensor_health, lambda: self.selected_cell, self._select_cell,
            lambda: self.source.quality.snapshot() if self.source is not None else None,
            lambda: self.source.serial_stats() if isinstance(self.source, SerialSource) else None))

    def _open_temporal(self):
        self.open_tool("temporal_window", "Temporal", lambda parent: TemporalWindow(parent, self))

    def _open_hotspots(self):
        self.open_tool("hotspot_window", "Hotspots", lambda parent: HotspotWindow(parent, self))

    def _open_motion(self):
        self.open_tool("motion_window", "Movement", lambda parent: MotionWindow(parent, self))

    def _open_indices(self):
        self.open_tool("indices_window", "Indices", lambda parent: IndicesWindow(parent, self))

    def _open_expression(self):
        self.open_tool("expression_window", "Expression", lambda parent: ExpressionWindow(parent, self))

    def _open_annotation(self, initial_type="Note"):
        AnnotationWindow(self.root, self, initial_type)

    def _open_engineering(self):
        self.open_tool("engineering_window", "Engineering", lambda parent: EngineeringWindow(parent, self))

    def _open_help(self):
        self.open_tool("help_window", "Help", HelpWindow)

    def current_settings(self):
        settings = capture_settings(self.contact_threshold_kpa, self.temporal,
                                    self.hotspots, self.motion)
        settings["indices"] = copy.deepcopy(self.indices.definitions)
        return settings

    def apply_engineering_settings(self, settings, preset_name=None):
        if "indices" in settings:  # first: an invalid set raises before anything is applied
            self._set_indices(settings["indices"])
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
            payload["roi"] = mask_to_cells(self.roi)
            payload["comparison"] = compare_hotspot_roi(self.roi, self.hotspots.active)
        return self.add_event("annotation", note, payload)

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
        key = self._base_key()
        grid = self.frame[key]
        if grid is None:
            return self.frame["baseline_subtracted"], "relative sensor value"
        return grid, "kPa" if key == "pressure" else "relative sensor value"

    def set_roi(self, mask):
        """Make a boolean cell mask the live ROI; None or an empty mask clears it"""
        self.roi = mask.copy() if mask is not None and mask.any() else None
        self.temporal.clear_roi()
        self.roi_history.clear()
        self._add_roi_history_sample()
        self._update_plot()
        self._refresh_analysis()

    def _outline_cells(self, mask, **style):
        """Draw a line along the cell edges around the selected cells of a mask"""
        fine = np.kron(np.pad(mask, 1).astype(float), np.ones((8, 8)))  # padded: closes at the mat edge
        y = (np.arange(fine.shape[0]) + 0.5) / 8 - 1.5
        x = (np.arange(fine.shape[1]) + 0.5) / 8 - 1.5
        return self.axes.contour(x, y, fine, levels=[0.5], **style)

    def _refresh_analysis(self):
        if self._shown(self.analysis_window):
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
        try:
            self.pressure_calibration.capture_tare(self.pre_baseline_grid)  # all-or-nothing
        except ValueError as error:
            self.status_var.set(str(error))
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
        self._refresh_calibration("calibration_changed")  # offsets changed too; keeps replay in step
        self.status_var.set("Tare captured: current reading set as zero")

    def _view_baseline(self):
        if self.calibration.baseline is None:
            self.status_var.set("No tare baseline captured yet")
            return
        window = tk.Toplevel(self.root)
        window.title("Tare baseline")
        figure = theme.figure(figsize=(5, 5))
        axes = figure.add_subplot()
        image = axes.imshow(self.calibration.baseline, cmap=theme.heatmap_cmap(), aspect="auto")
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
                "cell_width_mm": None if self.cell_size_mm is None else self.cell_size_mm[0],
                "cell_height_mm": None if self.cell_size_mm is None else self.cell_size_mm[1],
                "mat_size_mm": None if self.mat_size_mm is None else list(self.mat_size_mm),
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
                "indices": copy.deepcopy(self.indices.definitions),
                # frames are stored scaled to 0-1000; value_max is the raw full scale they came from
                "value_max": getattr(self.source, "value_max", VALUE_MAX_DEFAULT),
                "mat_id": getattr(self.source, "mat_id", None),
                "orientation": self._orientation(),
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

    def _export_snapshot(self):
        """Save the current frame as a long-format CSV, plus a PNG of the heatmap beside it"""
        if self.frame is None:
            self._notify("No frame yet - nothing to export")
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export snapshot", defaultextension=".csv",
            initialfile=f"snapshot_{time.strftime('%Y%m%d_%H%M%S')}.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        png = Path(path).with_suffix(".png")
        try:
            write_snapshot_csv(path, self.frame, self.frame_timestamp, getattr(self.source, "mat_id", None))
            self.figure.savefig(png, dpi=150)
        except (OSError, ValueError) as error:
            self._notify(f"Could not export snapshot: {error}")
            return
        self._notify(f"Exported snapshot to {path} and {png}")

    # ---- per-frame update

    def _poll(self):
        """Check for a new frame and update everything, then reschedule"""
        self._sync_mats()
        self._update_capture_button()
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
            live = not getattr(self.source, "is_playback", False)
            for item in grids:
                grid, sample_time = item if isinstance(item, tuple) else (item, None)
                if live:
                    grid = self._orient(grid)
                self._handle_new_frame(grid, sample_time)
            self._check_connection_health()
            if (time.time() - self._last_diagnostics_draw >= TOOL_REFRESH_S  # time first: _shown asks Tk
                    and self._shown(self.diagnostics_window)):
                self._last_diagnostics_draw = time.time()
                self.diagnostics_window.refresh()
            if (time.time() - self._last_temporal_draw >= TOOL_REFRESH_S
                    and self._shown(self.temporal_window)):
                self._last_temporal_draw = time.time()
                self.temporal_window.refresh()
            if time.time() - self._last_feature_draw >= TOOL_REFRESH_S:
                self._last_feature_draw = time.time()
                if self._shown(self.hotspot_window):
                    self.hotspot_window.refresh()
                if self._shown(self.motion_window):
                    self.motion_window.refresh()
                if self._shown(self.indices_window):
                    self.indices_window.refresh()
                if self._shown(self.expression_window):
                    self.expression_window.refresh()
                if self._shown(self.roi_window):
                    self.roi_window.refresh()
        self._retry_reconnect()
        self._update_occupancy()
        self._update_fps()
        self.root.after(POLL_INTERVAL_MS if self.source is not None else UI_IDLE_POLL_MS, self._poll)

    def _handle_new_frame(self, grid, sample_time=None):
        self.last_frame_time = time.time()
        if sample_time is not None and self.frame_timestamp is not None and sample_time <= self.frame_timestamp:
            self.cell_history.clear()
            self.cop_history.clear()
            self.roi_history.clear()
            self.sensor_health.reset()
            self._reset_indices()
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
        self.occupancy.update(frame["pressure"], self.frame_timestamp, self.contact_threshold_kpa)
        self._update_indices()
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

        # drawing is expensive (esp. with numbers on) - cap the rate
        now = time.time()
        if not self.paused_var.get() and now - self._last_draw_time >= DRAW_INTERVAL_S:
            self._last_draw_time = now
            self._update_plot()
        if now - self._last_analysis_draw >= TOOL_REFRESH_S:
            self._last_analysis_draw = now
            self._refresh_analysis()

    @staticmethod
    def _show(variable, text):
        """variable.set(text) unless it already shows it"""
        if variable.get() != text:
            variable.set(text)

    def _notify(self, text, seconds=8.0):
        """Status-line message that stays in front of the live numbers for a few seconds"""
        self._notice, self._notice_until = text, time.time() + seconds
        self.status_var.set(text)

    @staticmethod
    def _status_cell(label, token):
        """Colour a solid status cell from the active palette, with whichever text colour reads on it"""
        colour = theme.palette()[token]
        label.configure(bg=colour, fg=theme.text_on(colour))

    def _update_occupancy(self, force=False):
        text, token = OCCUPANCY_LABELS[self.occupancy.occupied]
        shown = (text, theme.palette()[token])  # the colour too: a theme switch repaints
        if shown == self._occupancy_shown and not force:
            return
        self._occupancy_shown = shown
        self.occupancy_label.configure(text=text)
        self._status_cell(self.occupancy_label, token)

    def _build_index_chips(self):
        for chip in self.index_chip_bar.winfo_children():
            chip.destroy()
        self.index_chips = {}
        for definition in self.indices.definitions:
            chip = tk.Label(self.index_chip_bar, text=definition["name"], padx=8)
            chip.pack(side=tk.LEFT, padx=2, pady=2)
            self.index_chips[definition["name"]] = chip
        self._update_index_chips()

    def _update_index_chips(self):
        for name, chip in self.index_chips.items():
            self._status_cell(chip, INDEX_CHIP_COLORS[self.indices.states[name]])

    def _set_indices(self, definitions):
        """Replace the index definitions (raises ValueError and changes nothing if invalid)"""
        self.indices.set_definitions(definitions)
        self.index_history = {}
        self._build_index_chips()
        self._refresh_data_modes()

    def _index_context(self):
        return Context(self.frame["pressure"], self.frame_timestamp, self.contact_threshold_kpa,
                       self.temporal, self.hotspots, self.motion, self.roi)

    def _update_indices(self, force=False):
        now = time.time()
        if self.frame is None or (not force and now - self._last_index_update < INDEX_UPDATE_INTERVAL_S):
            return
        self._last_index_update = now
        context = self._index_context()
        for name, old, new in self.indices.update(context, self.frame_timestamp, self.occupancy.occupied):
            self.add_event(INDEX_EVENTS[new], name, {
                "index": name, "value": self.indices.compared(name), "previous_state": old})
        for definition in self.indices.definitions:
            value = self.indices.values[definition["name"]]
            if definition["layer"] == "summary" and value is not None:
                self.index_history.setdefault(
                    definition["name"], deque(maxlen=HISTORY_MAX_FRAMES)).append((self.frame_timestamp, value))
        self._update_index_chips()

    def _reset_indices(self):
        self.indices.reset()
        self.index_history = {}
        self._update_index_chips()

    def _update_fps(self):
        now = time.time()
        if now - self._fps_last_check >= 1.0:
            self.fps_var.set(f"FPS: {self._fps_frame_count / (now - self._fps_last_check):.1f}")
            self._fps_frame_count = 0
            self._fps_last_check = now

    def _demo_tag(self):
        return " | DEMO" if self._demo_playback and self.source is not None else ""

    def _check_connection_health(self):
        """Flag a stale connection, and optionally auto-reconnect"""
        if getattr(self.source, "is_playback", False) and self.source.paused:
            self._show(self.connection_var, "Playback paused" + self._demo_tag())
            return
        if self.last_frame_time is None:
            return
        stale_for = time.time() - self.last_frame_time
        if stale_for < STALE_AFTER_S:
            if self._source_was_stale:
                self.add_event("source_reconnected")
                self._source_was_stale = False
            self._show(self.connection_var, "Connected" + self._demo_tag())
            return

        self._show(self.connection_var, f"No data for {stale_for:.0f}s")
        if not self._source_was_stale:
            self.add_event("source_disconnected")
            self._source_was_stale = True
            self.occupancy.reset()
            self._reset_indices()
            self.temporal.invalidate()
            self.hotspots.invalidate()
            self.motion.invalidate()
        if self.auto_reconnect_var.get() and time.time() - self.last_reconnect_attempt >= RECONNECT_INTERVAL_S:
            self._reconnect_since = self._reconnect_since or time.time() - stale_for
            self._auto_reconnect()

    def _auto_reconnect(self):
        self.last_reconnect_attempt = time.time()
        text = f"No data for {time.time() - self._reconnect_since:.0f}s - reconnecting..."
        self.connection_var.set(text)
        self._connect()
        if self.source is None:  # port unplugged or held elsewhere: _retry_reconnect tries again
            self.connection_var.set(text)

    def _retry_reconnect(self):
        """A reconnect attempt failed (source is None): keep trying until it works or the user disconnects"""
        if (self.source is None and self._reconnect_since is not None and self.auto_reconnect_var.get()
                and time.time() - self.last_reconnect_attempt >= RECONNECT_INTERVAL_S):
            self._auto_reconnect()

    def _update_plot(self):
        if self.frame is None:
            return
        key = self._data_key()
        derived = key not in DATA_MODES.values()  # a signal or index map: own unit, NaN stays blank
        grid = self._derived_grid(key) if derived else self.frame[key]
        pressure_unavailable = grid is None
        if pressure_unavailable:
            grid = np.zeros((app_config.TOTAL_ROWS, app_config.TOTAL_COLS))
        elif not derived:
            grid = np.where(np.isfinite(grid) & (grid > self.signal_noise_threshold), grid, 0.0)
        finite_values = grid[np.isfinite(grid)]
        difference = (self.difference_var.get() and self.reference_grid is not None
                      and self.reference_mode == key and not pressure_unavailable)
        if difference:
            comparison = self.comparison_grid if self.comparison_grid is not None else grid
            reference = self.reference_grid
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
        elif derived:  # units differ per map, so always auto
            vmin = 0.0
            vmax = float(finite_values.max()) if finite_values.size and finite_values.max() > 0 else 1.0
        else:
            vmin, vmax = self.calibration.vmin, self.calibration.vmax
        if self._plot_visible():  # a hidden tab or minimised window skips the draw, not the status line below
            self._draw_plot(grid, key, derived, difference, pressure_unavailable, finite_values, vmin, vmax)

        if self.recorder is not None:
            elapsed = time.time() - self.recorder.started_at
            prefix = f"Recording '{self.recorder.name}' - {elapsed:.0f}s, {self.recorder.frame_count} frames   "
        else:
            prefix = ""
        if pressure_unavailable and derived and self.frame["pressure"] is not None:
            status = f"{self.data_mode_var.get()}: no value yet"
        elif pressure_unavailable:
            status = f"Pressure calibration incomplete ({self.pressure_calibration.calibrated_count}/{app_config.TOTAL_ROWS * app_config.TOTAL_COLS} cells)"
        else:
            unit = " kPa" if key == "pressure" else (f" {SIGNALS[key[7:]].unit}" if key.startswith("signal:") else "")
            valid = grid[np.isfinite(grid)]
            number = "{:.3g}" if derived else "{:.1f}"
            status = (f"avg {number.format(valid.mean())}{unit}   max {number.format(valid.max())}{unit}   "
                      f"min {number.format(valid.min())}{unit}" if valid.size else "No valid sensor values")
        if time.time() < self._notice_until:
            prefix = self._notice + "   " + prefix
        self._show(self.status_var, prefix + ("Difference vs reference | " if difference else "") + status)

    def _draw_plot(self, grid, key, derived, difference, pressure_unavailable, finite_values, vmin, vmax):
        """Put the prepared grid on the canvas (the main heatmap or 3D surface)"""
        plot_grid = interpolate_grid(grid, self.interpolation_method, self.display_scale)

        if self.plot_type_var.get() == "3D Surface":
            plot_grid = np.nan_to_num(plot_grid)  # a surface cannot leave holes
            self.axes.clear()
            cols, rows = np.meshgrid(np.linspace(0, app_config.TOTAL_COLS - 1, plot_grid.shape[1]),
                                     np.linspace(0, app_config.TOTAL_ROWS - 1, plot_grid.shape[0]))
            self.axes.plot_surface(
                cols, rows, -plot_grid,
                cmap="coolwarm_r" if difference else theme.heatmap_cmap().reversed(),
                vmin=-vmax, vmax=-vmin,
            )
            self.axes.set_zlim(-vmax, -vmin)
            self.axes.set_zlabel("-kPa" if key == "pressure" else
                                 "-" + self._data_unit(key) if derived else "Negative sensor value")
        else:
            for collection in list(self.axes.collections):
                collection.remove()
            self.image.set_data(plot_grid)
            # Smooth: bicubic resampling at screen resolution on top of the upsampled grid
            interpolation = "bicubic" if self.interpolation_method == "Smooth" else "antialiased"
            extent = (-0.5, app_config.TOTAL_COLS - 0.5, app_config.TOTAL_ROWS - 0.5, -0.5)
            cmap = "coolwarm" if difference else theme.heatmap_cmap()
            cmap_name = cmap if isinstance(cmap, str) else cmap.name
            # each of these redraws the colorbar even when nothing changed, so only touch what did
            if self.image.get_interpolation() != interpolation:
                self.image.set_interpolation(interpolation)
            if tuple(self.image.get_extent()) != extent:
                self.image.set_extent(extent)
            if self.image.get_clim() != (vmin, vmax):
                self.image.set_clim(vmin, vmax)
            if self.image.get_cmap().name != cmap_name:
                self.image.set_cmap(cmap)
            overlays = []  # artists redrawn on every update (blitted); the rest of the figure is a cached bitmap
            self.axes.set_xlim(-0.5, app_config.TOTAL_COLS - 0.5)
            self.axes.set_ylim(app_config.TOTAL_ROWS - 0.5, -0.5)
            if self.show_contours and not pressure_unavailable and not difference and not derived:
                configured = self.pressure_contour_levels if key == "pressure" else self.relative_contour_levels
                levels = ([level for level in configured if finite_values.min() < level < finite_values.max()]
                          if finite_values.size else [])
                if levels:
                    x = np.linspace(0, app_config.TOTAL_COLS - 1, plot_grid.shape[1])
                    y = np.linspace(0, app_config.TOTAL_ROWS - 1, plot_grid.shape[0])
                    overlays.append(self.axes.contour(x, y, plot_grid, levels=levels, colors=theme.palette()["ink"],
                                                      linewidths=0.6, alpha=0.6))
            if (self.show_hotspot_threshold and key == "pressure" and not difference and
                    finite_values.size and finite_values.min() < self.hotspots.activate_kpa < finite_values.max()):
                x = np.linspace(0, app_config.TOTAL_COLS - 1, plot_grid.shape[1])
                y = np.linspace(0, app_config.TOTAL_ROWS - 1, plot_grid.shape[0])
                overlays.append(self.axes.contour(x, y, plot_grid, levels=[self.hotspots.activate_kpa],
                                                  colors="purple", linewidths=0.8, linestyles="dashed"))
            if self.show_boundary and self.frame["pressure"] is not None:
                mask = contact_mask(self.frame["pressure"], self.contact_threshold_kpa)
                if mask.any() and not mask.all():
                    overlays.append(self.axes.contour(
                        np.arange(app_config.TOTAL_COLS), np.arange(app_config.TOTAL_ROWS), mask.astype(float),
                        levels=[0.5], colors="blue", linewidths=0.8, alpha=0.6))
            for label in self.hotspot_labels:
                label.remove()
            self.hotspot_labels = []
            if self.show_hotspots_var.get() and self.hotspots.data_valid and not difference and key == "pressure":
                for track in self.hotspots.active:
                    mask = np.zeros((app_config.TOTAL_ROWS, app_config.TOTAL_COLS), dtype=float)
                    for row, col in track["cells"]:
                        mask[row, col] = 1
                    if not mask.all():
                        overlays.append(self.axes.contour(
                            np.arange(app_config.TOTAL_COLS), np.arange(app_config.TOTAL_ROWS), mask,
                            levels=[0.5], colors="red" if track["persistent"] else "orange", linewidths=1.3))
                    row, col = track["centroid"]
                    palette = theme.palette()
                    label = self.axes.text(col, row, f"#{track['id']} {track['active_s']:.0f}s",
                                           color=palette["ink"], fontsize=8, ha="center", va="center",
                                           bbox={"facecolor": palette["panel"], "alpha": 0.75, "edgecolor": "none"})
                    self.hotspot_labels.append(label)
            if not difference:
                for name, state in self.indices.states.items():
                    mask = self.indices.over_mask(name) if state == OVER else None
                    if mask is not None and mask.any() and not mask.all():
                        overlays.append(self.axes.contour(
                            np.arange(app_config.TOTAL_COLS), np.arange(app_config.TOTAL_ROWS),
                            mask.astype(float), levels=[0.5], colors=INDEX_OUTLINE_COLOR,
                            linewidths=1.3, linestyles="dotted"))
            if self.roi is not None:
                overlays.append(self._outline_cells(self.roi, colors="blue", linewidths=1.5))
            if self.selected_cell is not None:
                self.selected_marker.set_data([self.selected_cell[1]], [self.selected_cell[0]])
            if self.cop_var.get() and self.display_cop[0] is not None:
                self.cop_marker.set_data([self.display_cop[0]], [self.display_cop[1]])
            else:
                self.cop_marker.set_data([], [])
            if self.cell_labels is not None:
                for row in range(app_config.TOTAL_ROWS):
                    for col in range(app_config.TOTAL_COLS):
                        value = grid[row, col]
                        text = (f"{value:.1f}" if key == "pressure" else
                                (f"{value:.3g}" if np.isfinite(value) else "") if derived else f"{value:.0f}")
                        label = self.cell_labels[row][col]
                        if label.get_text() != text:  # an unchanged label keeps its cached layout
                            label.set_text(text)
            if self.blitter is not None:
                labels = [] if self.cell_labels is None else [label for line in self.cell_labels for label in line]
                # the last argument is what the cached bitmap shows: colour scale, colormap, the colorbar's title
                self.blitter.set_artists(
                    [self.image, self.cop_marker, self.selected_marker, *overlays, *self.hotspot_labels, *labels,
                     *self.axes.spines.values()],  # the image covers half a spine line otherwise
                    (vmin, vmax, cmap_name, difference, key))
                self.blitter.update()
                return
        self.canvas.draw_idle()

    def _plot_visible(self):
        """The live heatmap is on screen (not behind another tab, not a minimised window)"""
        try:
            return bool(self.canvas.get_tk_widget().winfo_viewable())
        except tk.TclError:
            return True

    def _plot_shown(self):
        """The heatmap just became visible again: draw the newest frame"""
        if self.blitter is not None:
            self.blitter.invalidate()
        if self.frame is not None and not self.paused_var.get():
            self._update_plot()

    def _hotspot_text(self):
        if not self.hotspots.data_valid:
            return "Hotspots: -"
        active = self.hotspots.active
        if not active:
            return "Hotspots: none"
        return f"Hotspots: {len(active)} active, longest {max(track['active_s'] for track in active):.0f} s"

    def _show_saturation(self, count):
        """Amber warning under the load line while cells are at the sensor limit"""
        if count >= getattr(app_config, "SATURATION_WARN_CELLS", 1):
            self._show(self.saturation_var, f"{count} cells at sensor limit: load and peak read low")
            if not self.saturation_label.winfo_manager():
                self.saturation_label.pack(anchor="w", after=self._load_row)
        else:
            self.saturation_label.pack_forget()

    def _update_stats(self):
        self._update_cell_info()
        self._show(self.hotspots_var, self._hotspot_text())
        if self.frame is None:
            self.display_cop = (None, None)
            self._show_saturation(0)
            return

        saturated = saturated_cells(self.frame["raw"])  # received values, not the tare-subtracted ones
        self._show_saturation(saturated)
        key = self._base_key()  # CoP follows pressure while a signal/index map is shown
        selected_grid = self.frame[key]
        if selected_grid is None:
            self.display_cop = (None, None)
        elif key == "pressure":
            self.display_cop = weighted_center(
                selected_grid, max(self.contact_threshold_kpa, self.signal_noise_threshold))
        else:
            self.display_cop = weighted_center(selected_grid, self.signal_noise_threshold)

        if self.frame is None or self.frame["pressure"] is None:
            count = self.pressure_calibration.calibrated_count
            self._show(self.pressure_status_var, f"Calibrate {app_config.TOTAL_ROWS * app_config.TOTAL_COLS - count} more cells for pressure statistics")
            self._show(self.peak_var, "Peak: -")
            self._show(self.mean_var, "Mean contact: -")
            self._show(self.area_var, "Contact area: -")
            self._show(self.force_var, "Force: -")
            self._show(self.load_var, "Estimated load: -")
            x, y = self.display_cop
            self._show(self.cop_text_var,
                       f"CoP (relative): x={x:.1f}, y={y:.1f} cells" if x is not None else "CoP (relative): -")
            self.stats = None
            return

        self.stats = pressure_statistics(self.frame["pressure"], self.contact_threshold_kpa,
                                         self.cell_area_m2)
        self._show(self.pressure_status_var, "Calibrated pressure")
        self._show(self.peak_var, f"Peak: {self.stats['peak_kpa']:.1f} kPa")
        mean = self.stats["mean_kpa"]
        self._show(self.mean_var, f"Mean contact: {mean:.1f} kPa" if mean is not None else "Mean contact: -")
        count = self.stats["contact_cells"]
        area = self.stats["contact_area_m2"]
        self._show(self.area_var, f"Contact area: {area * 10_000:.1f} cm² ({count} cells)" if area is not None
                          else f"Contact area: {count} cells")
        force = self.stats["force_n"]
        self._show(self.force_var, f"Force: {force:.1f} N" if force is not None else "Force: set mat size")
        self._show(self.load_var, load_estimate_text(force, self.pressure_calibration.is_default_curve, saturated))
        x, y = self.display_cop
        label = "CoP" if key == "pressure" else "CoP (relative)"
        self._show(self.cop_text_var, f"{label}: x={x:.1f}, y={y:.1f} cells" if x is not None else f"{label}: -")

    def _on_plot_click(self, event):
        if self.plot_type_var.get() != "2D Heatmap" or event.inaxes != self.axes:
            return
        if event.xdata is None or event.ydata is None:
            return
        row, col = round(event.ydata), round(event.xdata)
        if not (0 <= row < app_config.TOTAL_ROWS and 0 <= col < app_config.TOTAL_COLS):
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
        key = self._data_key()
        if key not in sample:  # only the shown signal/index map is worth computing per frame
            grid = self._derived_grid(key)
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
        values = grid[self.roi]
        valid = values[np.isfinite(values)]
        if valid.size:
            pressure = self.frame["pressure"]
            temporal = self.temporal.roi(self.roi)
            self.roi_history.append({"time": self.frame_timestamp,
                                     "mean": float(valid.mean()), "peak": float(valid.max()),
                                     "pressure_mean": None if pressure is None else float(np.nanmean(pressure[self.roi])),
                                     "exposure_mean": temporal["mean_exposure"],
                                     "burden_mean": temporal["mean_burden"],
                                     "relieved_fraction": temporal["relieved_fraction"]})

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
        self.history_figure = theme.figure(figsize=(6, 3))
        self.history_axes = self.history_figure.add_subplot()
        self.history_canvas = FigureCanvasTkAgg(self.history_figure, master=self.history_window)
        self.history_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._update_selected_details()
        self._update_history_plot()

    def _update_history_plot(self):
        if self.history_window is None or not self.history_window.winfo_exists():
            return
        key = self._data_key()
        samples = [item for item in self.cell_history if item.get(key) is not None]
        self.history_axes.clear()
        if samples:
            start = samples[0]["time"]
            self.history_axes.plot([item["time"] - start for item in samples],
                                   [item[key] for item in samples], color="green")
        self.history_axes.set_xlabel("Time since selection (s)")
        self.history_axes.set_ylabel(self._data_unit(key))
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
        self._save_profile()
        if self.source is not None:
            self.source.stop()
        if self._discovery is not None:
            self._discovery.stop()
        self.root.destroy()
