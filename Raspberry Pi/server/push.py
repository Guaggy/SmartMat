"""Push notifications for raised alerts through the Expo push service (one API for Android FCM and iOS APNs).

One push per alert that is raised, none when it clears. The text carries only the mat's name and room (mats are
named by room and seat, never by patient). A phone can set a quiet window (local time + time zone) and gets nothing
while it lasts; the alert is still in the app. Sending runs in a thread so a slow network never delays the tick.

Second, optional channel: ntfy (https://ntfy.sh or a self-hosted server, e.g. on the Tailscale network). It reaches an
iPhone running Expo Go, which cannot receive Expo push, through the free ntfy iOS app. Off unless NTFY_ENABLED and
NTFY_TOPIC are set in config.py. The message is the same text. There are no per-phone quiet hours on this channel: use
an iOS Focus mode. On the public ntfy.sh anyone who knows the topic can read it, so the topic is a secret.
"""

import json
import re
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
NTFY_TIMEOUT_S = 5  # a slow or dead ntfy server must not hold anything up
NTFY_TOPIC_OK = re.compile(r"[A-Za-z0-9_-]{1,64}")  # what ntfy accepts as a topic name
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


def ntfy_settings():
    """The NTFY_* values of config.py. A config.py written before ntfy existed lacks them: ntfy is then off."""
    return {"enabled": bool(getattr(config, "NTFY_ENABLED", False)),
            "url": str(getattr(config, "NTFY_URL", "https://ntfy.sh") or "https://ntfy.sh"),
            "topic": str(getattr(config, "NTFY_TOPIC", "") or ""),
            "token": str(getattr(config, "NTFY_TOKEN", "") or ""),
            "click_url": str(getattr(config, "NTFY_CLICK_URL", "") or ""),
            "lang": getattr(config, "NTFY_LANG", "en")}


def build_ntfy(alert, mat, settings):
    """The ntfy message (JSON publish to the server's base URL) for one raised alert, or None when ntfy is not usable.

    Mat name and room only, never a patient identifier. JSON rather than headers so the Norwegian letters survive."""
    topic, base = settings.get("topic", ""), settings.get("url", "").strip().rstrip("/")
    if not settings.get("enabled") or not NTFY_TOPIC_OK.fullmatch(topic) or not re.match(r"https?://[^\s/]+", base):
        return None
    texts = TEXTS.get(settings.get("lang"), TEXTS["en"])
    offline = alert["kind"] == "offline"
    room = (mat.get("room") or "").strip()
    what = texts["offline" if offline else "high_risk"]
    payload = {"topic": topic, "title": mat.get("name") or alert["chip_id"],
               "message": f"{texts['room'].format(room=room)}: {what}" if room else what,
               "priority": 4,  # "high" in ntfy
               "tags": ["electric_plug" if offline else "rotating_light"]}
    click = settings.get("click_url", "").strip().replace("{alert_id}", str(alert["id"]))
    if click:
        payload["click"] = click  # tapping the notification opens the dashboard / alert
    return {"url": base, "payload": payload, "token": settings.get("token", "")}


def post_json(url, payload, access_token="", timeout=10):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    request = urllib.request.Request(url, json.dumps(payload).encode(), headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def post_ntfy(url, payload, token=""):
    return post_json(url, payload, token, timeout=NTFY_TIMEOUT_S)


class PushSender:
    def __init__(self, store, post=post_json, clock=time.time, background=True, enabled=ENABLED, ntfy=None,
                 ntfy_post=post_ntfy):
        self.store, self.post, self.clock, self.background, self.enabled = store, post, clock, background, enabled
        self.ntfy = ntfy_settings() if ntfy is None else ntfy
        self.ntfy_post = ntfy_post
        self._ntfy_failing = False  # a failure is logged once, then again only after a success

    def notify(self, alert):
        """Call for every alert the AlertManager reports as raised (never for cleared). `enabled` is the master
        switch (the dashboard's push setting); ntfy additionally needs NTFY_ENABLED and a topic."""
        if not self.enabled:
            return
        mat = self.store.mats().get(alert["chip_id"], {})
        try:
            ntfy = build_ntfy(alert, mat, self.ntfy)
        except Exception as error:  # a broken NTFY_* value must not stop the Expo push or the tick
            print(f"ntfy: {type(error).__name__}: {error}")
            ntfy = None
        if ntfy:
            self._run(self._send_ntfy, ntfy)
        devices = self.store.devices()
        messages = build_messages(alert, mat, devices, self.clock()) if devices else []
        if messages:
            self._run(self._send, messages)

    def _run(self, target, argument):
        if self.background:
            threading.Thread(target=target, args=(argument,), daemon=True).start()
        else:
            target(argument)

    def _send_ntfy(self, message):
        try:
            self.ntfy_post(message["url"], message["payload"], message["token"])
            self._ntfy_failing = False
        except Exception as error:  # no internet, wrong token, ntfy down: only a log line, once
            if not self._ntfy_failing:
                print(f"ntfy: {type(error).__name__}: {error} (not logged again until it works)")
            self._ntfy_failing = True

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
