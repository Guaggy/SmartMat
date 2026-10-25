"""Copy this file to config.py (already in .gitignore, so it never gets
pushed to git) and fill in your own values below.
"""

# NOTE: always read the grid size as config.TOTAL_ROWS / config.TOTAL_COLS. A
# `from config import TOTAL_ROWS` copy goes stale when an MQTT mat of another size connects.

broker_host = "localhost"  # set the Pi/broker address here, or in the app under Engineering > Connection
broker_port = 1883
mqtt_username = "your-mqtt-username"
mqtt_password = "your-mqtt-password"

# Grid size for Serial/Simulated (Serial: must match src/main.cpp). An MQTT mat reports its own.
TOTAL_ROWS = 16
TOTAL_COLS = 15
BAUD_RATE = 115200
# Maxrays USB mats stream ~60 frames/s; frames are averaged down to this rate for the analysis (0 = off).
SERIAL_TARGET_FPS = 10

VALUE_MIN_DEFAULT = 0
VALUE_MAX_DEFAULT = 1000

# Physical SENSING size of the whole mat, outer edge of the first sensing element to the outer edge
# of the last (as built, before any rotation). Cell width = width / columns, cell height = height / rows.
# Default for mats whose profile has no size; each mat's size is set in the app (Mat size... under Estimated load)
# and kept in its profile. Enables area, force and the indicative load estimate (engineering aid only).
MAT_WIDTH_MM = None
MAT_HEIGHT_MM = None
# Older alternative: per-cell size, used only when no mat size is known.
CELL_WIDTH_MM = None
CELL_HEIGHT_MM = None

# Minimum calibrated pressure for a sensor to count as contacted. 1.0 kPa is about 5 counts of the
# Maxrays 8-bit mat on the default curve (idle noise <= 1 count); 2.0 left body-edge cells flagged
# Noisy/Drifting. Tuned on one seat take (samples/seat_take1.json), re-check with more takes.
CONTACT_THRESHOLD_KPA = 1.0

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

# Connected hotspot detection on calibrated sensor cells. The kPa values are absolute floors; the
# fractions raise them to N x the mean over loaded cells, so a hotspot is a pressure concentration
# rather than "the whole seat" and does not depend on the (uncalibrated) kPa curve (0 = off, kPa only).
# Tuned on one seat take (samples/seat_take1.json, tools/replay_tune.py), re-check with more takes.
HOTSPOT_ACTIVATE_KPA = 20.0
HOTSPOT_DEACTIVATE_KPA = 15.0
HOTSPOT_ACTIVATE_FRACTION = 1.7
HOTSPOT_DEACTIVATE_FRACTION = 1.2
HOTSPOT_MIN_CELLS = 4
HOTSPOT_PERSISTENCE_S = 30.0
HOTSPOT_MAX_MOVE_CELLS = 2.5
HOTSPOT_END_RELIEF_S = 10.0   # relieved this long before the hotspot ends (its id is reused if it comes back sooner)
HOTSPOT_RELIEF_GRACE_S = 1.0  # missing for less than this is a dropout, not relief (0 = off)

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

# Rolling received-value diagnostics; thresholds are engineering defaults (app units, 0-1000; one Maxrays
# count is 3.9). STUCK_NEIGHBOR_STD and SATURATION_FRAMES tuned on one seat take, re-check with more takes:
# a 0-count cell beside the body and cells at 255 under the sitting bones are normal for the 8-bit mat.
HEALTH_WINDOW_FRAMES = 50
HEALTH_UNLOADED_MAX = 40
HEALTH_UNLOADED_DELTA = 20
HEALTH_NOISE_STD = 12
HEALTH_DRIFT_DELTA = 15
HEALTH_DRIFT_MIN_S = 10
HEALTH_SATURATION_MARGIN = 10
HEALTH_SATURATION_FRAMES = 10
HEALTH_STUCK_STD = 0.5
HEALTH_STUCK_NEIGHBOR_STD = 60
HEALTH_STUCK_FRAMES = 30
HEALTH_INVALID_FRAMES = 3


# Connection health (gui/desktop.py)
STALE_AFTER_S = 10        # flag the connection as stale if no frame arrives for this long
RECONNECT_INTERVAL_S = 3  # how often to retry when auto-reconnect is on

# Start with the reduced Simple view (connect, tare, record, export, heatmap, key numbers); Advanced shows everything.
START_IN_SIMPLE_MODE = True

# Saturation warning
# Warn (and read the load as a lower bound) when at least this many cells are at the sensor limit
SATURATION_WARN_CELLS = 1

# Demo mats
# Chip ids starting with this are replayed recordings (tools/publish_demo_mat.py); the app labels them "(demo)".
DEMO_PREFIX = "demo-"

# Server (python -m server): headless analysis, alerts and web dashboard for every mat
SERVER_PORT = 8000            # web UI + REST
SERVER_SERIAL_PORTS = []      # USB mats the server owns and republishes to MQTT, e.g. [("COM3", "Maxrays 20x20 (921600)")]
POSTURE_SIDE_CELLS = 2.0      # centre of pressure this many cells left/right of the mat centre -> "left"/"right"
POSTURE_FORWARD_CELLS = 2.5   # ... this many cells towards the last row -> "forward"
POSTURE_HOLD_S = 3.0          # a new posture must last this long before it counts
ALERT_HIGH_HOLD_S = 30.0      # risk "high" this long opens an alert
ALERT_OFFLINE_S = 30.0        # a mat offline this long opens an alert
ALERT_RESTORE_GRACE_S = 60.0  # after a server restart, saved open alerts are kept this long while the mats report again
RISK_RELIEF_MIN = 120         # the server's risk index counts a loaded area as fully "at risk" after this many minutes without relief
RISK_NEAR_PERCENT = 80        # "medium" risk starts at this percent of the "high" limit
# Admins can change the alert, risk, posture, stale, saturation and retention values above in the dashboard (the gear
# icon); the dashboard value wins over this file, and "reset" goes back to what is written here.
PUSH_ENABLED = True           # push a raised alert to phones registered by the phone app (needs internet access to exp.host)
PUSH_ACCESS_TOKEN = ""        # optional Expo access token (expo.dev > Access tokens) so only this server can push to the phones
NTFY_ENABLED = False          # second push channel through ntfy, for an iPhone without a dev build (Phone App/README.md); needs PUSH_ENABLED
NTFY_URL = "https://ntfy.sh"  # public relay, or your own ntfy server, e.g. "http://100.x.y.z:8080" on Tailscale
NTFY_TOPIC = ""               # unguessable name (ntfy.sh topics are readable by anyone who knows them), e.g. "smartmat-k3j9x2q7vb"
NTFY_TOKEN = ""               # optional ntfy access token (tk_...) for a protected topic on your own server
NTFY_CLICK_URL = ""           # optional: tapping the notification opens this, e.g. "http://100.x.y.z:8000" ({alert_id} is replaced)
NTFY_LANG = "en"              # "en" or "nb": language of the notification text
RETENTION_DAYS = 30           # events, timeline and history snapshots older than this are deleted
HISTORY_ENABLED = True        # keep a small snapshot (grid + key numbers, ~0.5 KB) per mat for playback and exports
HISTORY_INTERVAL_S = 300      # ... every this many seconds, and at every alert raised/cleared
PIN_LOCKOUT_ATTEMPTS = 0      # wrong PINs in a row before a user is locked out (0 = no lockout)
PIN_LOCKOUT_S = 60            # how long a lockout lasts
