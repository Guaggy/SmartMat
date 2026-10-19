"""Alert state machine per mat (no I/O of its own): high risk or offline held long enough opens an alert,
which stays open until the condition clears. Acknowledge/ignore records who handled it. `on_change(alert)` is called
whenever an alert is raised, handled or cleared (the server saves it), and `restore` loads saved ones after a restart."""

import threading
import uuid
from collections import deque

import config

HIGH_HOLD_S = getattr(config, "ALERT_HIGH_HOLD_S", 30.0)
OFFLINE_HOLD_S = getattr(config, "ALERT_OFFLINE_S", 30.0)
RESTORE_GRACE_S = getattr(config, "ALERT_RESTORE_GRACE_S", 60.0)  # after a restart the mats need a moment to report again


class AlertManager:
    def __init__(self, high_hold_s=HIGH_HOLD_S, offline_hold_s=OFFLINE_HOLD_S, on_change=None, grace_s=RESTORE_GRACE_S):
        self.holds = {"high_risk": high_hold_s, "offline": offline_hold_s}
        self.on_change, self.grace_s = on_change, grace_s
        self._grace_until = {}  # alert id -> a restored alert is not cleared by "inactive" before this time
        self._since = {}   # (chip_id, kind) -> when the condition started
        self._open = {}    # alert id -> alert dict
        self._done = deque(maxlen=30)  # handled alerts whose condition has cleared (recent history for the bell)
        self._lock = threading.Lock()  # updated by the server tick, read by the web requests

    def restore(self, saved, now):
        """Take back the alerts saved before a restart. Uncleared ones stay open without being raised or pushed
        again; handled-and-cleared ones fill the history."""
        with self._lock:
            for alert in sorted(saved, key=lambda a: a["t_raised"]):
                if alert["t_cleared"] is None:
                    self._open[alert["id"]] = dict(alert)
                    self._grace_until[alert["id"]] = now + self.grace_s
                elif alert["state"] != "open":
                    self._done.append(dict(alert))

    def reset_holds(self):
        """Start counting every condition that has not opened an alert yet from its next update (after a clock jump
        the saved start times mean nothing); open alerts stay"""
        with self._lock:
            self._since.clear()

    def _changed(self, alert):
        if self.on_change is not None:
            self.on_change(dict(alert))

    def update(self, chip_id, risk, online, t):
        """Feed one mat's state; returns [("raised" | "cleared", alert)]"""
        events = []
        with self._lock:
            for kind, active in (("high_risk", online and risk == "high"), ("offline", not online)):
                key = (chip_id, kind)
                alert = next((a for a in self._open.values() if a["chip_id"] == chip_id and a["kind"] == kind), None)
                if not active:
                    self._since.pop(key, None)
                    if alert is not None and not online and t < self._grace_until.get(alert["id"], 0):
                        continue  # restored a moment ago and the mat has not reported yet
                    if alert is not None:
                        self._grace_until.pop(alert["id"], None)
                        alert["t_cleared"] = t
                        del self._open[alert["id"]]
                        if alert["state"] != "open":
                            self._done.append(alert)
                        self._changed(alert)
                        events.append(("cleared", dict(alert)))
                    continue
                if alert is not None:
                    self._grace_until.pop(alert["id"], None)  # reporting again and still the same condition
                since = self._since.setdefault(key, t)
                if alert is None and t - since >= self.holds[kind]:
                    alert = {"id": uuid.uuid4().hex[:12], "chip_id": chip_id, "kind": kind, "t_raised": t,
                             "since": since, "t_cleared": None, "state": "open", "by": None, "t_handled": None}
                    self._open[alert["id"]] = alert
                    self._changed(alert)
                    events.append(("raised", dict(alert)))
        return events

    def recent(self):
        """Open and acknowledged alerts plus the handled ones that have cleared since, newest first"""
        with self._lock:
            return sorted((dict(a) for a in (*self._done, *self._open.values())), key=lambda a: -a["t_raised"])

    def open_alerts(self, chip_id=None):
        with self._lock:
            return [dict(a) for a in sorted(self._open.values(), key=lambda a: a["t_raised"])
                    if chip_id is None or a["chip_id"] == chip_id]

    def _handle(self, alert_id, user, t, state):
        with self._lock:
            alert = self._open.get(alert_id)
            if alert is None:
                raise KeyError(alert_id)
            if alert["state"] != "open":
                raise ValueError(f"Alert already handled by {alert['by']}")
            alert.update(state=state, by=user, t_handled=t)
            self._changed(alert)
            return dict(alert)

    def acknowledge(self, alert_id, user, t):
        """Someone is on it; stays open (off the bell) until the condition clears. KeyError if unknown or cleared, ValueError if already handled"""
        return self._handle(alert_id, user, t, "acknowledged")

    def ignore(self, alert_id, user, t):
        return self._handle(alert_id, user, t, "ignored")
