"""Push notifications: the devices table and routes, message building (text, quiet hours), the sender and the tick."""

import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from server import push
from server.__main__ import Server
from server.alerts import AlertManager
from server.app import create_app
from server.engine import MatEngine
from server.push import PushSender, build_messages, is_quiet, parse_hhmm
from server.store import Store

PIN = "1234"
TOKEN = "ExponentPushToken[abcDEF123_-xyz]"
ALERT = {"id": "a1", "chip_id": "m1", "kind": "high_risk"}


def utc(hour, minute=0, month=1):
    return datetime(2026, month, 15, hour, minute, tzinfo=timezone.utc).timestamp()


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.store = Store(self.dir / "smartmat.db")
        self.addCleanup(self.store.close)


class DeviceStoreTests(StoreCase):
    def test_add_update_remove(self):
        self.store.add_device(TOKEN, "android", "Kari", 5.0, name="Kari's phone", lang="en", tz="Europe/Oslo")
        device = self.store.devices()[0]
        self.assertEqual((device["token"], device["platform"], device["lang"], device["user"]), (TOKEN, "android", "en", "Kari"))
        self.store.update_device(TOKEN, quiet_from="22:00", quiet_to="07:00", lang="nb", ignored="x")
        device = self.store.devices()[0]
        self.assertEqual((device["quiet_from"], device["quiet_to"], device["lang"]), ("22:00", "07:00", "nb"))
        self.assertTrue(self.store.remove_device(TOKEN))
        self.assertFalse(self.store.remove_device(TOKEN))
        self.assertEqual(self.store.devices(), [])

    def test_registering_twice_keeps_one_row_and_defaults_to_norwegian(self):
        self.store.add_device(TOKEN, "android", "Kari", 1.0)
        self.store.add_device(TOKEN, "ios", "Ola", 2.0)
        rows = self.store.devices()
        self.assertEqual([(r["platform"], r["user"], r["lang"]) for r in rows], [("ios", "Ola", "nb")])

    def test_rejects_anything_that_is_not_an_expo_token(self):
        for bad in ("", "abc", None, "ExponentPushToken[]", "ExponentPushToken[a b]", "ExponentPushToken[x]/../"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.store.add_device(bad, "android", "Kari", 1.0)
        with self.assertRaises(KeyError):
            self.store.update_device("ExponentPushToken[nope]", name="x")


class DeviceApiTests(StoreCase):
    def setUp(self):
        super().setUp()
        self.now = 1000.0
        self.alerts = AlertManager(high_hold_s=0, offline_hold_s=0)
        self.client = create_app(self.store, self.alerts, {}, clock=lambda: self.now).test_client()
        self.client.post("/api/users", json={"name": "Admin", "role": "admin", "new_pin": PIN})

    def register(self, **extra):
        body = {"expo_push_token": TOKEN, "platform": "android", "name": "Pixel", "lang": "nb", "pin": PIN, **extra}
        return self.client.post("/api/devices", json=body)

    def test_register_needs_a_pin_and_logs_who_without_the_token(self):
        self.assertEqual(self.register(pin=None).status_code, 401)
        self.assertEqual(self.register(pin="9999").status_code, 403)
        self.assertEqual(self.store.devices(), [])
        response = self.register(tz="Europe/Oslo", quiet_from="22:00", quiet_to="07:00")
        self.assertEqual((response.status_code, response.get_json()), (201, {"ok": True, "user": "Admin"}))
        self.assertEqual(self.store.devices()[0]["tz"], "Europe/Oslo")
        event = next(e for e in self.store.events() if e["kind"] == "device registered")
        self.assertEqual(event["user"], "Admin")
        self.assertNotIn("Expo", str(event))

    def test_register_validates_input(self):
        self.assertEqual(self.register(platform="symbian").status_code, 400)
        self.assertEqual(self.register(expo_push_token="nope").status_code, 400)
        self.assertEqual(self.register(lang="fr").status_code, 400)
        self.assertEqual(self.register(tz="Mars/Base").status_code, 400)
        self.assertEqual(self.register(quiet_from="25:00").status_code, 400)
        self.assertEqual(self.store.devices(), [])

    def test_update_and_delete_by_token_need_no_pin(self):
        self.register()
        url = f"/api/devices/{TOKEN}"
        self.assertEqual(self.client.put(url, json={"quiet_from": "21:30", "quiet_to": "06:00", "tz": "Europe/Oslo"}).status_code, 200)
        self.assertEqual(self.store.devices()[0]["quiet_from"], "21:30")
        self.assertEqual(self.client.put(url, json={"tz": "Mars/Base"}).status_code, 400)
        self.assertEqual(self.client.put("/api/devices/ExponentPushToken[other]", json={"name": "x"}).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertEqual(self.store.devices(), [])


class MessageTests(unittest.TestCase):
    def device(self, **extra):
        return {"token": TOKEN, "lang": "nb", "tz": "Europe/Oslo", "quiet_from": None, "quiet_to": None, **extra}

    def test_text_uses_mat_name_and_room_only(self):
        mat = {"name": "Stol 1", "room": "101", "seat": "A"}
        (message,) = build_messages(ALERT, mat, [self.device()], utc(12))
        self.assertEqual((message["title"], message["body"]), ("Stol 1", "Rom 101: Høy risiko (veiledende)"))
        self.assertEqual((message["channelId"], message["priority"], message["to"]), ("alerts", "high", TOKEN))
        self.assertEqual(message["data"], {"alert_id": "a1", "chip_id": "m1", "kind": "high_risk"})
        (english,) = build_messages(dict(ALERT, kind="offline"), mat, [self.device(lang="en")], utc(12))
        self.assertEqual(english["body"], "Room 101: Mat offline")

    def test_without_room_or_name_it_falls_back(self):
        (message,) = build_messages(ALERT, {}, [self.device(lang="xx")], utc(12))
        self.assertEqual((message["title"], message["body"]), ("m1", "Høy risiko (veiledende)"))

    def test_quiet_window_in_the_phones_time_zone(self):
        quiet = self.device(quiet_from="22:00", quiet_to="07:00")
        # Oslo is UTC+1 in January and UTC+2 in July
        self.assertTrue(is_quiet(quiet, utc(21, 30)))          # 22:30 in Oslo
        self.assertTrue(is_quiet(quiet, utc(5, 59)))           # 06:59
        self.assertFalse(is_quiet(quiet, utc(6, 0)))           # 07:00 is open again
        self.assertFalse(is_quiet(quiet, utc(12)))
        self.assertTrue(is_quiet(quiet, utc(20, 30, month=7)))  # 22:30 summer time
        self.assertFalse(is_quiet(quiet, utc(5, 30, month=7)))  # 07:30 summer time
        self.assertEqual(build_messages(ALERT, {}, [quiet], utc(23)), [])

    def test_no_or_bad_quiet_settings_never_mute(self):
        for extra in ({}, {"quiet_from": "22:00"}, {"quiet_from": "08:00", "quiet_to": "08:00"},
                      {"quiet_from": "x", "quiet_to": "07:00"}, {"quiet_from": "22:00", "quiet_to": "07:00", "tz": None},
                      {"quiet_from": "22:00", "quiet_to": "07:00", "tz": "Mars/Base"}):
            self.assertFalse(is_quiet(self.device(**extra), utc(23)), extra)

    def test_parse_hhmm(self):
        self.assertEqual((parse_hhmm("07:05"), parse_hhmm("7:05"), parse_hhmm("24:00"), parse_hhmm("x")), (425, 425, None, None))


class SenderTests(StoreCase):
    def setUp(self):
        super().setUp()
        self.sent = []
        self.reply = lambda chunk: {"data": [{"status": "ok", "id": "t"} for _ in chunk]}
        self.sender = PushSender(self.store, post=self.post, clock=lambda: utc(12), background=False, enabled=True)
        self.store.set_meta("m1", {"name": "Stol 1", "room": "101"})

    def post(self, url, chunk, token):
        self.sent.append((url, chunk, token))
        return self.reply(chunk)

    def test_no_devices_means_no_request(self):
        self.sender.notify(ALERT)
        self.assertEqual(self.sent, [])

    def test_one_request_with_one_message_per_phone(self):
        self.store.add_device(TOKEN, "android", "Kari", 1.0)
        self.store.add_device("ExponentPushToken[second]", "ios", "Ola", 2.0, lang="en")
        self.sender.notify(ALERT)
        self.assertEqual(len(self.sent), 1)
        url, chunk, _ = self.sent[0]
        self.assertEqual(url, push.URL)
        self.assertEqual([m["body"] for m in chunk], ["Rom 101: Høy risiko (veiledende)", "Room 101: High pressure risk (indicative)"])

    def test_disabled_sender_is_silent(self):
        self.store.add_device(TOKEN, "android", "Kari", 1.0)
        PushSender(self.store, post=self.post, enabled=False).notify(ALERT)
        self.assertEqual(self.sent, [])

    def test_unregistered_phone_is_removed_other_errors_keep_it(self):
        self.store.add_device(TOKEN, "android", "Kari", 1.0)
        self.store.add_device("ExponentPushToken[keep]", "android", "Ola", 2.0)
        self.reply = lambda chunk: {"data": [{"status": "error", "message": "gone", "details": {"error": "DeviceNotRegistered"}},
                                             {"status": "error", "message": "rate", "details": {"error": "MessageRateExceeded"}}]}
        self.sender.notify(ALERT)
        self.assertEqual([d["token"] for d in self.store.devices()], ["ExponentPushToken[keep]"])

    def test_network_failure_is_swallowed(self):
        self.store.add_device(TOKEN, "android", "Kari", 1.0)

        def broken(*_):
            raise OSError("no internet")
        PushSender(self.store, post=broken, clock=lambda: utc(12), background=False, enabled=True).notify(ALERT)
        self.assertEqual(len(self.store.devices()), 1)

    def test_more_than_100_phones_are_sent_in_chunks(self):
        for i in range(120):
            self.store.add_device(f"ExponentPushToken[d{i}]", "android", "Kari", float(i))
        self.sender.notify(ALERT)
        self.assertEqual([len(chunk) for _, chunk, _ in self.sent], [100, 20])


class TickTests(StoreCase):
    def test_a_raised_alert_is_pushed_once_and_clearing_sends_nothing(self):
        class Recorder:
            def __init__(self):
                self.alerts = []

            def notify(self, alert):
                self.alerts.append(alert)

        recorder = Recorder()
        server = Server(self.store, AlertManager(high_hold_s=0, offline_hold_s=0), use_mqtt=False, pusher=recorder)
        self.addCleanup(server.stop)
        server.engines["m1"] = MatEngine("m1", 20, 20)  # never got a frame: offline
        server.tick(100.0)
        server.tick(101.0)
        self.assertEqual([(a["chip_id"], a["kind"]) for a in recorder.alerts], [("m1", "offline")])
        server.engines["m1"].status = None
        server.engines["m1"].last_t = 101.5
        server.engines["m1"].clock = lambda: 102.0  # online again -> the alert clears
        self.assertEqual(len(server.alerts.open_alerts()), 1)
        server.tick(102.0)
        self.assertEqual(server.alerts.open_alerts(), [])  # it did clear, and clearing sent nothing
        self.assertEqual(len(recorder.alerts), 1)


if __name__ == "__main__":
    unittest.main()
