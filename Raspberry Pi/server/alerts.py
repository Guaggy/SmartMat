"""Alert state machine per mat (no I/O): high risk or offline held long enough opens an alert,
which stays open until the condition clears. Acknowledge/ignore records who handled it."""

import threading
import uuid

import config

HIGH_HOLD_S = getattr(config, "ALERT_HIGH_HOLD_S", 30.0)
OFFLINE_HOLD_S = getattr(config, "ALERT_OFFLINE_S", 30.0)


class AlertManager:
    def __init__(self, high_hold_s=HIGH_HOLD_S, offline_hold_s=OFFLINE_HOLD_S):
        self.holds = {"high": high_hold_s, "offline": offline_hold_s}
        self._since = {}   # (chip_id, kind) -> when the condition started
        self._open = {}    # alert id -> alert dict
        self._lock = threading.Lock()  # updated by the server tick, read by the web requests

    def update(self, chip_id, risk, online, t):
        """Feed one mat's state; returns [("raised" | "cleared", alert)]"""
        events = []
        with self._lock:
            for kind, active in (("high", online and risk == "high"), ("offline", not online)):
                key = (chip_id, kind)
                alert = next((a for a in self._open.values() if a["chip_id"] == chip_id and a["kind"] == kind), None)
                if not active:
                    self._since.pop(key, None)
                    if alert is not None:
                        alert["t_cleared"] = t
                        del self._open[alert["id"]]
                        events.append(("cleared", dict(alert)))
                    continue
                since = self._since.setdefault(key, t)
                if alert is None and t - since >= self.holds[kind]:
                    alert = {"id": uuid.uuid4().hex[:12], "chip_id": chip_id, "kind": kind, "t_raised": t,
                             "since": since, "t_cleared": None, "state": "open", "user": None, "t_handled": None}
                    self._open[alert["id"]] = alert
                    events.append(("raised", dict(alert)))
        return events

    def open_alerts(self, chip_id=None):
        with self._lock:
            return [dict(a) for a in sorted(self._open.values(), key=lambda a: a["t_raised"])
                    if chip_id is None or a["chip_id"] == chip_id]

    def _handle(self, alert_id, user, t, state):
        with self._lock:
            alert = self._open.get(alert_id)
            if alert is None:
                raise KeyError(alert_id)
            alert.update(state=state, user=user, t_handled=t)
            return dict(alert)

    def acknowledge(self, alert_id, user, t):
        """Someone is on it; stays open (off the bell) until the condition clears. KeyError if not open"""
        return self._handle(alert_id, user, t, "acknowledged")

    def ignore(self, alert_id, user, t):
        return self._handle(alert_id, user, t, "ignored")
