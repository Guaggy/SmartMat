"""Copy this file to config.py (already in .gitignore, so it never gets
pushed to git) and fill in your own values below.
"""

# NOTE: always read the grid size as config.TOTAL_ROWS / config.TOTAL_COLS. A
# `from config import TOTAL_ROWS` copy goes stale when an MQTT mat of another size connects.

broker_host = "192.168.1.50"  # static/reserved IP of the Raspberry Pi's Mosquitto broker
broker_port = 1883
mqtt_username = "your-mqtt-username"
mqtt_password = "your-mqtt-password"

# Grid size for Serial/Simulated (Serial: must match src/main.cpp). An MQTT mat reports its own.
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

# "Patient detected" indicator: this many cells above CONTACT_THRESHOLD_KPA, held this long.
OCCUPANCY_MIN_CELLS = 4
OCCUPANCY_ENTER_S = 2.0   # load must last this long before "Patient detected"
OCCUPANCY_EXIT_S = 5.0    # mat must stay empty this long before "No patient"

# Custom indices (Engineering window > Indices): warning hold time and evaluation rate.
INDEX_WARNING_HOLD_S = 5.0     # a new OK/near/over state must last this long before it shows
INDEX_UPDATE_INTERVAL_S = 1.0  # indices move slowly; no need to evaluate them every frame

# Maximum timing error accepted when pairing manual and automatic repositions.
VALIDATION_MATCH_WINDOW_S = 15.0

# Plot-only interpolation; statistics always use the original sensor grid.
DISPLAY_SCALE = 2
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
