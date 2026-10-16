"""In-app settings kept in settings.json in the user data folder (paths.APP_DIR).

The MQTT broker, the SmartMat server URL and the desktop theme. Stored as plain text, on purpose. Never raises on a
missing or corrupt file: the broker then comes from config.py, then the defaults.
"""

import json
import os
from urllib.parse import urlsplit

import config
import paths

FILE = None  # tests point this at a temp file; None = <paths.APP_DIR>/settings.json
MQTT_DEFAULTS = {"host": "localhost", "port": 1883, "username": "", "password": ""}
CONFIG_NAMES = {"host": "broker_host", "port": "broker_port",
                "username": "mqtt_username", "password": "mqtt_password"}
THEMES = ("light", "dark")
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
    _save("mqtt", {"host": host, "port": port, "username": username, "password": password})


def theme():
    """The saved desktop theme, "light" or "dark"; anything else (or nothing) counts as "light" """
    value = load().get("theme")
    return value if value in THEMES else "light"


def save_theme(mode):
    """Save the desktop theme (ValueError for an unknown mode, OSError if the file cannot be written)"""
    if mode not in THEMES:
        raise ValueError(f"unknown theme {mode!r}")
    _save("theme", mode)


def _save(key, value):
    """Set one top-level key, keeping the others"""
    data = load()
    data[key] = value
    _write(data)


def _write(data):
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


def parse_server_url(value):
    """'http://10.0.0.15:8000/' -> 'http://10.0.0.15:8000'; None unless a string with an http/https scheme and a host"""
    if not isinstance(value, str):
        return None
    value = value.strip()
    try:
        parts = urlsplit(value)
        valid = parts.scheme in ("http", "https") and bool(parts.hostname) and not any(c.isspace() for c in value)
        parts.port  # raises ValueError for a port outside 0-65535
    except ValueError:
        return None
    return value.rstrip("/") if valid else None


def effective_server_url():
    """The saved SmartMat server URL, or "" when not configured (a bad saved value counts as not configured)"""
    return parse_server_url(load().get("server_url")) or ""


def save_server_url(url):
    """Save a valid URL, or "" to clear it. Raises ValueError for anything else, OSError if the file cannot be written."""
    clean = parse_server_url(url) if url.strip() else ""
    if clean is None:
        raise ValueError("The server address must start with http:// or https://, for example http://10.0.0.15:8000")
    data = load()
    data["server_url"] = clean
    _write(data)
