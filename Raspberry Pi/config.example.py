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

# Local web server (gui/web.py)
WEB_PORT = 8000

# Connection health (gui/desktop.py)
STALE_AFTER_S = 10        # flag the connection as stale if no frame arrives for this long
RECONNECT_INTERVAL_S = 3  # how often to retry when auto-reconnect is on
