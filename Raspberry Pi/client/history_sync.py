"""A mat's rough history from the SmartMat server (a snapshot every few minutes plus one at every alert), ready to play
back: fetch a time range, step through it, show a snapshot's numbers and save the range as a recording the deep-analysis
tools can open.

Everything here is indicative: the pictures are 8-bit grids sampled minutes apart, so this is for looking at how
pressure and posture developed over hours, not for frame-level analysis. No Tk here: the window is gui/history_window.py.
"""

import json
import math
import time

import numpy as np

PAGE = 300                 # snapshots per request when grids are included (the server's cap)
MAX_SNAPSHOTS = 3000       # a few days at 5 minutes; keeps memory and the wait reasonable
RANGES = (("Last 6 hours", 6), ("Last 24 hours", 24), ("Last 3 days", 72), ("Last 7 days", 168))
MODES = ("instant", "peak")
MODE_LABELS = {"instant": "Instant", "peak": "5-min peak"}
SPEEDS = (1, 2, 5, 10, 25)  # snapshots per second
RISKS = ("high", "medium", "low", "none", "offline")
ALERT_REASONS = ("alert_raised", "alert_cleared")


def decode_grid(grid, scale_max):
    """rows x cols ints 0-255 -> float array in the snapshot's unit; None stays None"""
    if grid is None:
        return None
    return np.asarray(grid, dtype=float) / 255.0 * float(scale_max or 0)


def usable(snapshot):
    return isinstance(snapshot, dict) and isinstance(snapshot.get("t"), (int, float)) and math.isfinite(snapshot["t"])


class History:
    """The snapshots of one mat over a range, oldest first"""

    def __init__(self, mat, snapshots, since=None, until=None, interval_s=None, truncated=False):
        self.mat = mat
        self.snapshots = sorted((s for s in snapshots if usable(s)), key=lambda s: s["t"])
        self.since, self.until, self.interval_s, self.truncated = since, until, interval_s, truncated

    def __len__(self):
        return len(self.snapshots)

    def times(self):
        return [s["t"] for s in self.snapshots]

    def alert_markers(self):
        """[(index, 'raised'|'cleared', alert_kind)] for the marker strip"""
        return [(i, s["reason"].split("_", 1)[1], s.get("alert_kind") or "") for i, s in enumerate(self.snapshots)
                if s.get("reason") in ALERT_REASONS]

    def risk_strip(self):
        """The risk of every snapshot (for a coloured strip under the scrubber)"""
        return [s.get("risk") if s.get("risk") in RISKS else "none" for s in self.snapshots]

    def grid(self, index, mode="instant"):
        """The snapshot's picture in its unit. 'peak' falls back to the instant picture when the snapshot has no peak
        (alert snapshots); None when it has no picture at all (an offline mat's alert)"""
        snap = self.snapshots[index]
        raw = snap.get("peak_grid") if mode == "peak" else None
        if raw is None:
            raw = snap.get("grid")
        return decode_grid(raw, snap.get("scale_max"))

    def has_peak(self, index):
        return self.snapshots[index].get("peak_grid") is not None

    def top(self, mode="instant"):
        """One colour scale for the whole range (so frames are comparable): the highest cell seen, at least 1"""
        best = 1.0
        for snap in self.snapshots:
            scale = float(snap.get("scale_max") or 0)
            for key in ("grid", "peak_grid") if mode == "peak" else ("grid",):
                raw = snap.get(key)
                if raw is not None and scale:
                    best = max(best, float(np.max(raw)) / 255.0 * scale)
        return best

    def unit(self):
        for snap in reversed(self.snapshots):
            if snap.get("unit"):
                return "kPa" if snap["unit"] == "kPa" else "relative"
        return "kPa"


def fetch_range(client, mat, since, until, progress=None, cancelled=None, max_snapshots=MAX_SNAPSHOTS):
    """Page through the server's history with grids. (True, History) or (False, text). `progress(n)` after each page;
    `cancelled()` true stops early (False, "cancelled"). Runs in a thread: no Tk here."""
    snapshots, start, after, interval, enabled = [], since, False, None, True
    while True:
        if cancelled is not None and cancelled():
            return False, "cancelled"
        ok, page = client.get_snapshots(mat, start, until, PAGE, True, after)
        if not ok:
            return False, page
        if not isinstance(page, dict) or not isinstance(page.get("snapshots"), list):
            return False, "the server sent no history (is it a newer SmartMat server?)"
        snapshots.extend(page["snapshots"])
        interval, enabled = page.get("interval_s", interval), page.get("enabled", enabled)
        if progress is not None:
            progress(len(snapshots))
        if not (page.get("truncated") and page.get("next_from") is not None):
            truncated = False
            break
        if len(snapshots) >= max_snapshots:
            truncated = True
            break
        start, after = page["next_from"], True
    if not snapshots and not enabled:
        return False, "this server does not keep a history (HISTORY_ENABLED is off)"
    return True, History(mat, snapshots, since, until, interval, truncated)


def hotspot_text(hotspots):
    if not hotspots:
        return "none"
    shown = []
    for h in hotspots[:4]:
        text = f"{h.get('peak_kpa') or 0:.0f} kPa"
        shown.append(text + (" (persistent)" if h.get("persistent") else ""))
    more = len(hotspots) - 4
    return f"{len(hotspots)}: " + ", ".join(shown) + (f", +{more} more" if more > 0 else "")


def duration_text(seconds):
    if seconds is None:
        return "-"
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours:
        return f"{hours} h {minutes:02d} min"
    return f"{minutes} min" if minutes else f"{seconds} s"


def _num(value, unit="", digits=1):
    return "-" if value is None else f"{value:.{digits}f}" + (f" {unit}" if unit else "")


def time_text(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))


def numbers(snapshot):
    """[(label, text)] for the side panel. Values are indicative (an estimate from a rough mat), not measurements."""
    pressure_unit = "kPa" if snapshot.get("unit") == "kPa" else "(relative)"
    reason = snapshot.get("reason", "")
    event = f"  [{reason.replace('_', ' ')}: {snapshot.get('alert_kind') or 'alert'}]" if reason in ALERT_REASONS else ""
    score = snapshot.get("score")
    return [
        ("Time", time_text(snapshot["t"]) + event),
        ("Risk", str(snapshot.get("risk", "-")) + ("" if score is None else f" (index {score:.2f} of limit)")),
        ("Peak pressure", _num(snapshot.get("peak_kpa"), pressure_unit)),
        ("Contact area", _num(snapshot.get("contact_area_cm2"), "cm²", 0)),
        ("Load (indicative)", _num(snapshot.get("load_kg"), "kg")),
        ("Posture", "unoccupied" if snapshot.get("posture") in (None, "none") else str(snapshot["posture"])),
        ("Time since movement", duration_text(snapshot.get("since_movement_s"))),
        ("Time in position", duration_text(snapshot.get("time_in_position_s"))),
        ("Hotspots", hotspot_text(snapshot.get("hotspots"))),
    ]


class Player:
    """Position and play state for a History; the window calls tick() from one after() timer while playing."""

    def __init__(self, history, mode="instant"):
        self.history, self.mode = history, mode
        self.index, self.playing, self.speed = 0, False, SPEEDS[1]

    @property
    def last(self):
        return max(len(self.history) - 1, 0)

    def seek(self, index):
        self.index = min(max(int(round(index)), 0), self.last)
        return self.index

    def play(self):
        if not len(self.history):
            return False
        if self.index >= self.last:
            self.index = 0
        self.playing = True
        return True

    def pause(self):
        self.playing = False

    def tick(self):
        """One step forward; stops at the end. True when the picture changed"""
        if not self.playing:
            return False
        if self.index >= self.last:
            self.playing = False
            return False
        self.index += 1
        if self.index >= self.last:
            self.playing = False
        return True

    def delay_ms(self):
        return int(1000 / self.speed)

    def set_mode(self, mode):
        self.mode = mode if mode in MODES else "instant"

    def next_alert(self, step=1):
        """Index of the next (step=1) or previous (step=-1) alert snapshot, or None"""
        marks = [i for i, _, _ in self.history.alert_markers()]
        found = [i for i in marks if (i > self.index if step > 0 else i < self.index)]
        return (min(found) if step > 0 else max(found)) if found else None

    def current(self):
        return self.history.snapshots[self.index] if len(self.history) else None

    def grid(self):
        return self.history.grid(self.index, self.mode) if len(self.history) else None


# ---- save as a recording (the desktop's smartmat_raw_v1 JSON: load it, then use the deep-analysis tools)

def to_recording(history, mode="instant", name=None):
    """The history as a recording dict. Snapshots without a picture, or of a different mat size than the first picture,
    are left out. Stored values are 0-1000 with metadata.value_max = the mat's full scale (kPa when the unit is kPa)."""
    scales = [s["scale_max"] for s in history.snapshots if s.get("scale_max")]
    value_max = float(max(scales)) if scales else 1000.0
    frames, events, shape, last_t = [], [], None, None
    for i, snap in enumerate(history.snapshots):
        grid = history.grid(i, mode)
        if grid is None or not snap.get("scale_max"):
            continue
        if shape is None:
            shape = grid.shape
        if grid.shape != shape:
            continue
        stamp = snap["t"] if last_t is None or snap["t"] > last_t else last_t + 0.001   # strictly increasing
        last_t = stamp
        frames.append({"timestamp": stamp, "raw": np.round(grid / value_max * 1000.0, 2).tolist()})
        if snap.get("reason") in ALERT_REASONS:
            events.append({"timestamp": stamp, "kind": snap["reason"], "frame_index": len(frames) - 1,
                           "note": f"{snap['reason'].replace('_', ' ')}: {snap.get('alert_kind') or 'alert'}",
                           "payload": {"alert_id": snap.get("alert_id"), "risk": snap.get("risk")}})
    if not frames:
        raise ValueError("no snapshot in this range has a picture")
    return {
        "format": "smartmat_raw_v1",
        "name": name or f"{history.mat}_history",
        "started_at": frames[0]["timestamp"],
        "source": "SmartMat server history",
        "grid_shape": [int(shape[0]), int(shape[1])],
        "units": "relative sensor value 0-1000, scaled from 0..metadata.value_max "
                 f"({'kPa' if history.unit() == 'kPa' else 'relative units'}); rough server snapshots, not frame-rate data",
        "metadata": {"mat_id": history.mat, "value_max": value_max, "history_mode": mode,
                     "interval_s": history.interval_s, "unit": history.unit(),
                     "frame_spacing": "server snapshots (about 5 min apart), not a continuous recording"},
        "events": events,
        "frames": frames,
    }


def save_recording(history, path, mode="instant"):
    """Write the recording JSON to `path`; returns the number of frames"""
    session = to_recording(history, mode, name=getattr(path, "stem", None))
    with open(path, "w", encoding="utf-8") as file:
        json.dump(session, file, allow_nan=False)
    return len(session["frames"])
