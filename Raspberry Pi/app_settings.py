"""In-app settings kept in settings.json in the user data folder (paths.APP_DIR).

Only the MQTT broker for now. Stored as plain text, on purpose. Never raises on a
missing or corrupt file: the broker then comes from config.py, then the defaults.
"""

import json
import os

import config
import paths

FILE = None  # tests point this at a temp file; None = <paths.APP_DIR>/settings.json
MQTT_DEFAULTS = {"host": "localhost", "port": 1883, "username": "", "password": ""}
CONFIG_NAMES = {"host": "broker_host", "port": "broker_port",
                "username": "mqtt_username", "password": "mqtt_password"}
PLACEHOLDERS = {"your-mqtt-username", "your-mqtt-password"}  # config.example.py credentials: count as unset (the host never does)


def settings_path():
    return FILE or paths.APP_DIR / "settings.json"


def load():
    """The saved settings as a dict; {} if the file is missing, unreadable or not a JSON object"""
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_mqtt(host, port, username, password):
    """Write the broker settings (other saved keys are kept). Raises OSError if the file cannot be written."""
    data = load()
    data["mqtt"] = {"host": host, "port": port, "username": username, "password": password}
    path = settings_path()
    temp = path.with_name(path.name + ".tmp")  # write then swap, so a crash mid-write keeps the old file
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp, path)


def parse_port(value):
    """An int 1..65535 from an int or a numeric string, else None"""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        port = int(str(value).strip())
    except ValueError:
        return None
    return port if 1 <= port <= 65535 else None


def _usable(key, value, from_config):
    """The value cleaned up, or None when it counts as unset (an empty username IS a valid saved value)"""
    if key == "port":
        return parse_port(value)
    if not isinstance(value, str):
        return None
    if key == "host":
        value = value.strip()
        if not value:
            return None
    return None if from_config and value in PLACEHOLDERS else value


def effective_mqtt():
    """{"host", "port", "username", "password"}: settings.json, then config.py, then the defaults"""
    saved = load().get("mqtt")
    saved = saved if isinstance(saved, dict) else {}
    result = {}
    for key, default in MQTT_DEFAULTS.items():
        result[key] = default
        for value, from_config in ((saved.get(key), False), (getattr(config, CONFIG_NAMES[key], None), True)):
            value = _usable(key, value, from_config)
            if value is not None:
                result[key] = value
                break
    return result
