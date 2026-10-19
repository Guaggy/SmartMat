"""Push notifications for raised alerts through the Expo push service (one API for Android FCM and iOS APNs).

One push per alert that is raised, none when it clears. The text carries only the mat's name and room (mats are
named by room and seat, never by patient). A phone can set a quiet window (local time + time zone) and gets nothing
while it lasts; the alert is still in the app. Sending runs in a thread so a slow network never delays the tick.
"""

import json
import threading
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import config

ENABLED = getattr(config, "PUSH_ENABLED", True)
URL = getattr(config, "PUSH_URL", "https://exp.host/--/api/v2/push/send")
ACCESS_TOKEN = getattr(config, "PUSH_ACCESS_TOKEN", "")  # optional Expo "enhanced security" token
TTL_S = getattr(config, "PUSH_TTL_S", 1800)  # an alert older than this is not worth delivering late
CHUNK = 100  # the Expo API takes at most 100 messages per request
CHANNEL = "alerts"  # Android notification channel created by the app

TEXTS = {
    "nb": {"high_risk": "Høy risiko (veiledende)", "offline": "Frakoblet", "room": "Rom {room}"},
    "en": {"high_risk": "High pressure risk (indicative)", "offline": "Mat offline", "room": "Room {room}"},
}


def parse_hhmm(text):
    """"22:30" -> minutes after midnight, None if it is not HH:MM"""
    try:
        hours, minutes = str(text).strip().split(":")
        hours, minutes = int(hours), int(minutes)
    except ValueError:
        return None
    return hours * 60 + minutes if 0 <= hours < 24 and 0 <= minutes < 60 else None


def valid_zone(name):
    try:
        ZoneInfo(name)
        return True
    except Exception:  # unknown key, bad characters, missing tzdata
        return False


def is_quiet(device, now):
    """True while `now` (unix seconds) is inside the phone's quiet window [from, to) in its own time zone"""
    start, end = parse_hhmm(device.get("quiet_from")), parse_hhmm(device.get("quiet_to"))
    if start is None or end is None or start == end or not device.get("tz") or not valid_zone(device["tz"]):
        return False
    local = datetime.fromtimestamp(now, ZoneInfo(device["tz"]))
    minute = local.hour * 60 + local.minute
    return start <= minute < end if start < end else minute >= start or minute < end


def build_messages(alert, mat, devices, now):
    """Expo push messages for one raised alert: [{to, title, body, ...}] for the phones that are not in quiet hours"""
    messages = []
    for device in devices:
        if is_quiet(device, now):
            continue
        texts = TEXTS.get(device.get("lang"), TEXTS["nb"])
        what = texts["offline" if alert["kind"] == "offline" else "high_risk"]
        room = (mat.get("room") or "").strip()
        messages.append({
            "to": device["token"], "title": mat.get("name") or alert["chip_id"],
            "body": f"{texts['room'].format(room=room)}: {what}" if room else what,
            "sound": "default", "channelId": CHANNEL, "priority": "high", "ttl": TTL_S,
            "data": {"alert_id": alert["id"], "chip_id": alert["chip_id"], "kind": alert["kind"]},
        })
    return messages


def post_json(url, payload, access_token="", timeout=10):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    request = urllib.request.Request(url, json.dumps(payload).encode(), headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


class PushSender:
    def __init__(self, store, post=post_json, clock=time.time, background=True, enabled=ENABLED):
        self.store, self.post, self.clock, self.background, self.enabled = store, post, clock, background, enabled

    def notify(self, alert):
        """Call for every alert the AlertManager reports as raised (never for cleared)"""
        if not self.enabled:
            return
        devices = self.store.devices()
        if not devices:
            return
        mat = self.store.mats().get(alert["chip_id"], {})
        messages = build_messages(alert, mat, devices, self.clock())
        if not messages:
            return
        if self.background:
            threading.Thread(target=self._send, args=(messages,), daemon=True).start()
        else:
            self._send(messages)

    def _send(self, messages):
        for start in range(0, len(messages), CHUNK):
            chunk = messages[start:start + CHUNK]
            try:
                tickets = self.post(URL, chunk, ACCESS_TOKEN).get("data") or []
            except Exception as error:  # no internet must not break anything else
                print(f"push: {type(error).__name__}: {error}")
                continue
            for message, ticket in zip(chunk, tickets):
                if ticket.get("status") == "ok":
                    continue
                if (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
                    self.store.remove_device(message["to"])  # app uninstalled or notifications revoked
                else:
                    print(f"push: not delivered: {ticket.get('message')}")
