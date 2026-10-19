"""Settings an administrator can change in the dashboard, on top of the defaults in config.py.

Only the keys in SPEC can be changed. An override is stored in the database (settings table) and applied at once,
without a restart; resetting a key goes back to the config.py value. Nothing here touches the mats directly: the
server registers a listener that pushes the effective values into the alert manager, the push sender and the engines.
"""

import math
import threading

import config

# key, group, type, config.py name, fallback, min, max, unit, advanced (hidden under "advanced" in the page)
SPEC = (
    ("alert_high_hold_s", "alerts", int, "ALERT_HIGH_HOLD_S", 30, 5, 3600, "s", False),
    ("alert_offline_s", "alerts", int, "ALERT_OFFLINE_S", 30, 5, 3600, "s", False),
    ("push_enabled", "alerts", bool, "PUSH_ENABLED", True, None, None, "", False),
    ("relief_minutes", "risk", int, "RISK_RELIEF_MIN", 120, 10, 720, "min", False),
    ("near_percent", "risk", int, "RISK_NEAR_PERCENT", 80, 50, 99, "%", False),
    ("stale_after_s", "mats", int, "STALE_AFTER_S", 10, 3, 300, "s", False),
    ("saturation_warn_cells", "mats", int, "SATURATION_WARN_CELLS", 1, 1, 400, "", False),
    ("posture_hold_s", "posture", float, "POSTURE_HOLD_S", 3.0, 0, 60, "s", True),
    ("posture_side_cells", "posture", float, "POSTURE_SIDE_CELLS", 2.0, 0.5, 10, "cells", True),
    ("posture_forward_cells", "posture", float, "POSTURE_FORWARD_CELLS", 2.5, 0.5, 10, "cells", True),
    ("retention_days", "data", int, "RETENTION_DAYS", 30, 1, 365, "days", False),
)
KEYS = tuple(row[0] for row in SPEC)


def _check(row, value):
    """The value as its type, or ValueError with a sentence for the user"""
    key, _, kind, _, _, low, high, unit, _ = row
    key = key.replace("_", " ")  # the error is shown as it is
    if kind is bool:
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be on or off")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{key} must be a number")
    if kind is int:
        if value != int(value):
            raise ValueError(f"{key} must be a whole number")
        value = int(value)
    else:
        value = float(value)
    if not low <= value <= high:
        raise ValueError(f"{key} must be between {low:g} and {high:g}{' ' + unit if unit else ''}")
    return value


class Settings:
    def __init__(self, store=None):
        self._store = store
        self._lock = threading.Lock()
        self._listeners = []
        self.overrides = {}
        for key, value in (store.saved_settings() if store is not None else {}).items():
            row = next((r for r in SPEC if r[0] == key), None)
            if row is not None:
                try:
                    self.overrides[key] = _check(row, value)
                except ValueError:  # an invalid saved value falls back to the default instead of stopping the server
                    pass

    def default(self, key):
        row = next(r for r in SPEC if r[0] == key)
        return _check(row, getattr(config, row[3], row[4])) if _valid_default(row) else row[4]

    def get(self, key):
        with self._lock:
            return self.overrides[key] if key in self.overrides else self.default(key)

    def values(self):
        return {key: self.get(key) for key in KEYS}

    def describe(self):
        """For the page: one entry per setting with its value, default, limits and group"""
        out = []
        for key, group, kind, _, _, low, high, unit, advanced in SPEC:
            out.append({"key": key, "group": group, "type": kind.__name__, "value": self.get(key),
                        "default": self.default(key), "min": low, "max": high, "unit": unit, "advanced": advanced,
                        "changed": key in self.overrides})
        return out

    def listen(self, listener, call=True):
        """listener(values) is called with every effective value whenever one changes (and, with `call`, once right away)"""
        self._listeners.append(listener)
        if call:
            listener(self.values())

    def update(self, changes):
        """changes: {key: value, or None for "back to the default"}. All or nothing: ValueError names the first
        bad one and nothing changes. Returns {key: (old, new)} for the ones that really changed."""
        rows = {r[0]: r for r in SPEC}
        checked = {}
        for key, value in changes.items():
            if key not in rows:
                raise ValueError(f"unknown setting {key}")
            checked[key] = None if value is None else _check(rows[key], value)
        with self._lock:
            before = {key: self.overrides[key] if key in self.overrides else self.default(key) for key in KEYS}
            for key, value in checked.items():
                if value is None:
                    self.overrides.pop(key, None)
                else:
                    self.overrides[key] = value
            after = {key: self.overrides[key] if key in self.overrides else self.default(key) for key in KEYS}
            if self._store is not None:
                self._store.save_settings({key: self.overrides.get(key) for key in checked})
        changed = {key: (before[key], after[key]) for key in KEYS if before[key] != after[key]}
        if changed:
            values = self.values()
            for listener in self._listeners:
                listener(values)
        return changed


def _valid_default(row):
    try:
        _check(row, getattr(config, row[3], row[4]))
        return True
    except ValueError:  # a typo in config.py must not take the page down
        return False
