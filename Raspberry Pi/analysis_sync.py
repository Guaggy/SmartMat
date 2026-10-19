"""One mat's analysis settings, between this desktop and the SmartMat server: compare, push, pull, and a preview that
replays a recording through the server's own engine and alert rules ("what would the server do with these settings").

Only the settings that change what the server's analysis and warnings do are synced: the engineering preset (contact
threshold, temporal, hotspots, movement) and the risk indices. Display options (colour map, smoothing, plot options)
and the server's own rules (alert delays, risk sensitivity, stale limit, posture) stay where they are set.

No Tk here: the window code is in gui/server_panel.py. The preview is stepped (`Replay.step`) so the window can drive
it from the main thread: the server's engine briefly sets the global grid size while it works, which must never run
at the same time as the desktop's own live analysis.
"""

import json
import math
from collections import defaultdict

import numpy as np

from processing.indices import tuned_indices, validate_indices
from processing.settings import ENGINEERING_GROUPS, flatten_preset, unflatten_preset, validate_settings

RISKS = ("high", "medium", "low", "none", "offline")


def is_sync_key(key):
    return key in ("contact_threshold_kpa", "indices") or ("." in key and key.split(".", 1)[0] in ENGINEERING_GROUPS)


def label(key):
    """A readable name for a settings key: "hotspots.activate_kpa" -> "hotspots: activate kpa" """
    group, _, name = key.partition(".")
    return f"{group}: {name.replace('_', ' ')}" if name else key.replace("_", " ")


def describe(key, value):
    """A value as text for a table"""
    if key == "indices":
        return "built-in" if value is None else f"{len(value)} indices"
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


# ---- the two sides as flat {key: value}

def local_values(settings):
    """This desktop's engineering settings (DesktopApp.current_settings(): a nested preset plus "indices") as flat keys.
    `indices` is None when the settings carry none (older presets): that row is then left out of the comparison."""
    values = flatten_preset(settings)
    values["indices"] = validate_indices(settings["indices"]) if settings.get("indices") is not None else None
    return values


def server_values(page):
    """{key: value in force} from a config page of the server. The built-in risk indices (None) are written out, tuned
    by the server's two risk knobs, so both sides compare real definitions"""
    values = {item["key"]: item["value"] for item in page["settings"]}
    if values.get("indices") is None:
        values["indices"] = tuned_indices(values["relief_minutes"], values["near_percent"])
    values["indices"] = validate_indices(values["indices"])
    return values


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(a, list) or isinstance(b, list):
        return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    return a == b


def compare(settings, page):
    """Rows for every synced setting: {key, label, local, server, source, differs}. `source` is where the server's value
    comes from (factory, site or mat). Rows that differ come first, then the others in the preset's order."""
    local, remote = local_values(settings), server_values(page)
    source = {item["key"]: item["source"] for item in page["settings"]}
    rows = []
    for key in local:
        if key not in remote:
            continue
        differs = local[key] is not None and not _same(local[key], remote[key])
        rows.append({"key": key, "label": label(key), "local": local[key], "server": remote[key],
                     "source": source.get(key, "factory"), "differs": differs})
    return sorted(rows, key=lambda row: not row["differs"])   # stable: the preset's order inside each part


def changes_to_push(rows, only=None):
    """{key: this desktop's value} for the rows that differ (and are in `only` when given): what a push would set"""
    return {row["key"]: row["local"] for row in rows if row["differs"] and (only is None or row["key"] in only)}


def settings_from_server(page):
    """The server's values as desktop settings (a nested preset plus "indices"), checked like a loaded preset.
    ValueError when they are not a valid preset."""
    values = server_values(page)
    settings = validate_settings(dict(unflatten_preset(values), indices=values["indices"]))
    return settings


def values_after_push(page, changes):
    """The server's resolved values for this mat as they would be after a push of `changes`"""
    return dict(server_values(page), **changes)


# ---- preview: the server's engine on a recording

def format_seconds(seconds):
    if seconds is None:
        return "-"
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    return f"{seconds // 60} min {seconds % 60:02d} s" if seconds < 3600 else f"{seconds // 3600} h {seconds % 3600 // 60:02d} min"


class Replay:
    """A recording played through the server's MatEngine and AlertManager with one set of resolved settings.
    step() feeds a few frames and returns how far it is (0..1); result() says how long the mat was at each risk level
    and which alerts the server would have raised. The recording is fed at most `max_fps` frames a second (the server
    analyses about four a second) and at most `max_s` seconds of it (0 = all)."""

    def __init__(self, frames, times, resolved, profile=None, max_fps=4.0, max_s=0.0, name=""):
        from server.alerts import AlertManager   # only a preview needs the server's code
        from server.engine import MatEngine
        rows, cols = frames[0].shape
        if times is None:
            times = [index * 0.1 for index in range(len(frames))]
        self.name, self.t0 = name, times[0]
        self.engine = MatEngine("preview", rows, cols, profile=profile)
        self.engine.configure(resolved)
        self.alerts = AlertManager(high_hold_s=resolved["alert_high_hold_s"], offline_hold_s=resolved["alert_offline_s"])
        self.queue, last = [], None
        for grid, t in zip(frames, times):
            if max_s and t - self.t0 > max_s:
                break
            if last is None or t - last >= 1.0 / max_fps - 1e-9:
                self.queue.append((np.asarray(grid, dtype=float), t))
                last = t
        self.next, self.risk_seconds, self.log, self.fed, self.t_last = 0, defaultdict(float), [], 0, self.t0
        self.next_tick = self.t0 + 1.0

    def done(self):
        return self.next >= len(self.queue)

    def step(self, frames=8):
        for _ in range(frames):
            if self.done():
                break
            grid, t = self.queue[self.next]
            self.next += 1
            self.engine.feed(grid, t)
            self.fed += 1
            self.t_last = t
            while t >= self.next_tick:
                self._tick(self.next_tick)
                self.next_tick += 1.0
        return 1.0 if not self.queue else self.next / len(self.queue)

    def _tick(self, t):
        snap = self.engine.snapshot(t)
        self.risk_seconds[snap["risk"]] += 1.0
        for kind, alert in self.alerts.update("preview", snap["risk"], snap["online"], t):
            if kind == "raised":
                self.log.append({"id": alert["id"], "kind": alert["kind"], "t_raised": t - self.t0, "t_cleared": None})
            else:
                for entry in self.log:
                    if entry["id"] == alert["id"]:
                        entry["t_cleared"] = t - self.t0

    def result(self):
        return {"name": self.name, "frames": self.fed, "duration_s": self.t_last - self.t0,
                "risk_seconds": {risk: self.risk_seconds.get(risk, 0.0) for risk in RISKS},
                "alerts": [dict(entry) for entry in self.log],
                "first_alert_s": self.log[0]["t_raised"] if self.log else None}


def run(replays, progress=None, cancelled=None):
    """Drive replays one after the other to the end (tests and scripts; the window steps them itself).
    Returns [result, ...], or None when cancelled() said so."""
    for index, replay in enumerate(replays):
        while not replay.done():
            if cancelled is not None and cancelled():
                return None
            fraction = replay.step()
            if progress is not None:
                progress((index + fraction) / len(replays))
    return [replay.result() for replay in replays]


def summary_lines(before, after):
    """Short lines comparing two results: the server as it is now, and with the pushed settings"""
    def minutes(result, risk):
        return format_seconds(result["risk_seconds"][risk])
    lines = [f"Replayed {format_seconds(after['duration_s'])} of the recording ({after['frames']} frames)",
             f"Alerts the server would raise: {len(before['alerts'])} now, {len(after['alerts'])} with these settings",
             f"First alert: {format_seconds(before['first_alert_s'])} now, {format_seconds(after['first_alert_s'])} with these settings"]
    for risk in ("high", "medium", "low"):
        lines.append(f"Time at {risk} risk: {minutes(before, risk)} now, {minutes(after, risk)} with these settings")
    return lines
