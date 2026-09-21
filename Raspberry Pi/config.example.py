"""Copy this file to config.py (already in .gitignore, so it never gets
pushed to git) and fill in your own values below.
"""

broker_host = "192.168.1.50"  # static/reserved IP of the Raspberry Pi's Mosquitto broker
broker_port = 1883
mqtt_username = "your-mqtt-username"
mqtt_password = "your-mqtt-password"
mqtt_topic = "smartmat/frame"

# These must match src/main.cpp on the ESP32
TOTAL_ROWS = 16
TOTAL_COLS = 15
BAUD_RATE = 115200

VALUE_MIN_DEFAULT = 0
VALUE_MAX_DEFAULT = 1000

# Physical cell dimensions; set both to measured values to enable area and force.
CELL_WIDTH_MM = None
CELL_HEIGHT_MM = None

# Minimum calibrated pressure for a sensor to count as contacted.
CONTACT_THRESHOLD_KPA = 2.0

# Raw/processed values at or below this level are hidden and ignored by signal CoP.
SIGNAL_NOISE_THRESHOLD = 0.0

# Startup pressure calibration; set a JSON file to replace the linear fallback.
DEFAULT_PRESSURE_CALIBRATION_FILE = None
DEFAULT_PRESSURE_CALIBRATION_RAW_MAX = VALUE_MAX_DEFAULT
DEFAULT_PRESSURE_CALIBRATION_KPA = 50.0

# Fixed heatmap maximum in pressure mode when auto-scale is off.
PRESSURE_DISPLAY_MAX_KPA = 50.0

# Number of selected-cell samples kept in the history window.
HISTORY_MAX_FRAMES = 600

# Temporal analysis uses measured timestamps and skips longer gaps.
TEMPORAL_MAX_GAP_S = 2.0
EXPOSURE_THRESHOLD_KPA = 2.0
EXPOSURE_MODE = "Full pressure"
BURDEN_LOAD_THRESHOLD_KPA = 2.0
BURDEN_ACCUMULATION_RATE = 1.0
BURDEN_RECOVERY_TIME_S = 300.0
RELIEF_PARTIAL_RATIO = 0.5
RELIEF_FULL_RATIO = 0.2
RELIEF_MIN_DURATION_S = 1.0
ROI_RELIEF_FRACTION = 0.5
TEMPORAL_BUCKET_S = 10
TEMPORAL_WINDOWS_MIN = (1, 5, 15, 30, 60)

# Connected hotspot detection on calibrated sensor cells.
HOTSPOT_ACTIVATE_KPA = 20.0
HOTSPOT_DEACTIVATE_KPA = 15.0
HOTSPOT_MIN_CELLS = 2
HOTSPOT_PERSISTENCE_S = 30.0
HOTSPOT_MAX_MOVE_CELLS = 2.5
HOTSPOT_END_RELIEF_S = 3.0

# Movement uses normalized map change, CoP travel, and contact-area change.
MOVEMENT_SMALL_SCORE = 0.15
MOVEMENT_SIGNIFICANT_SCORE = 0.35
MOVEMENT_MAJOR_SCORE = 0.65
MOVEMENT_COP_SCALE_CELLS = 4.0
MOVEMENT_COOLDOWN_S = 5.0

# Reposition requires sustained redistribution after settling.
REPOSITION_MIN_SCORE = 0.35
REPOSITION_SETTLE_S = 5.0
REPOSITION_BEFORE_S = 30.0
REPOSITION_AFTER_S = 30.0
REPOSITION_MIN_CHANGE = 0.25
REPOSITION_MIN_CONTACT_CELLS = 2
REPOSITION_COOLDOWN_S = 60.0

# Maximum timing error accepted when pairing manual and automatic repositions.
VALIDATION_MATCH_WINDOW_S = 15.0

# Plot-only interpolation; statistics always use the original sensor grid.
DISPLAY_SCALE = 4
PRESSURE_CONTOUR_LEVELS_KPA = (5, 10, 20, 40)
RELATIVE_CONTOUR_LEVELS = (100, 250, 500, 750)

# Rolling received-value diagnostics; thresholds are engineering defaults.
HEALTH_WINDOW_FRAMES = 50
HEALTH_UNLOADED_MAX = 40
HEALTH_UNLOADED_DELTA = 20
HEALTH_NOISE_STD = 12
HEALTH_DRIFT_DELTA = 15
HEALTH_DRIFT_MIN_S = 10
HEALTH_SATURATION_MARGIN = 10
HEALTH_SATURATION_FRAMES = 5
HEALTH_STUCK_STD = 0.5
HEALTH_STUCK_NEIGHBOR_STD = 15
HEALTH_STUCK_FRAMES = 30
HEALTH_INVALID_FRAMES = 3

# Local web server (gui/web.py)
WEB_PORT = 8000

# Connection health (gui/desktop.py)
STALE_AFTER_S = 10        # flag the connection as stale if no frame arrives for this long
RECONNECT_INTERVAL_S = 3  # how often to retry when auto-reconnect is on
