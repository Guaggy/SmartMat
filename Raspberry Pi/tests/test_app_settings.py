"""app_settings: settings.json round trip, precedence over config.py, placeholders, bad files."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import app_settings


class AppSettingsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.file = Path(folder.name) / "settings.json"
        for patch in (mock.patch.object(app_settings, "FILE", self.file),
                      mock.patch.object(app_settings, "config", SimpleNamespace())):
            patch.start()
            self.addCleanup(patch.stop)

    def set_config(self, **values):
        app_settings.config.__dict__.update(values)

    def test_defaults_when_nothing_is_set(self):
        self.assertEqual(app_settings.effective_mqtt(),
                         {"host": "localhost", "port": 1883, "username": "", "password": ""})

    def test_config_py_beats_defaults(self):
        self.set_config(broker_host="10.0.0.5", broker_port=1999, mqtt_username="u", mqtt_password="p")
        self.assertEqual(app_settings.effective_mqtt(),
                         {"host": "10.0.0.5", "port": 1999, "username": "u", "password": "p"})

    def test_example_placeholders_count_as_unset(self):
        self.set_config(broker_host="192.168.1.50", broker_port=1883,
                        mqtt_username="your-mqtt-username", mqtt_password="your-mqtt-password")
        self.assertEqual(app_settings.effective_mqtt(),
                         {"host": "localhost", "port": 1883, "username": "", "password": ""})

    def test_settings_json_beats_config_py(self):
        self.set_config(broker_host="10.0.0.5", mqtt_username="cfg", mqtt_password="cfgpw")
        app_settings.save_mqtt("pi.local", 1884, "me", "secret")
        self.assertEqual(app_settings.effective_mqtt(),
                         {"host": "pi.local", "port": 1884, "username": "me", "password": "secret"})

    def test_saved_empty_username_wins_over_config(self):
        self.set_config(mqtt_username="cfg", mqtt_password="cfgpw")
        app_settings.save_mqtt("pi.local", 1883, "", "")
        result = app_settings.effective_mqtt()
        self.assertEqual((result["username"], result["password"]), ("", ""))

    def test_round_trip_keeps_other_keys(self):
        self.file.write_text(json.dumps({"other": 1}), encoding="utf-8")
        app_settings.save_mqtt("h", 1, "u", "p")
        self.assertEqual(json.loads(self.file.read_text(encoding="utf-8")),
                         {"other": 1, "mqtt": {"host": "h", "port": 1, "username": "u", "password": "p"}})

    def test_missing_corrupt_or_wrong_shaped_file_falls_back(self):
        self.set_config(broker_host="10.0.0.5")
        self.assertEqual(app_settings.effective_mqtt()["host"], "10.0.0.5")  # missing
        for text in ("{not json", "[]", '"text"', '{"mqtt": 5}', '{"mqtt": {"host": 7, "port": "x"}}', ""):
            self.file.write_text(text, encoding="utf-8")
            self.assertEqual(app_settings.effective_mqtt()["host"], "10.0.0.5", text)
            self.assertEqual(app_settings.effective_mqtt()["port"], 1883, text)

    def test_bad_values_fall_through_one_by_one(self):
        self.set_config(broker_port=1999)
        self.file.write_text(json.dumps({"mqtt": {"host": "  ", "port": 70000, "username": None}}), encoding="utf-8")
        self.assertEqual(app_settings.effective_mqtt(),
                         {"host": "localhost", "port": 1999, "username": "", "password": ""})

    def test_unwritable_location_raises_oserror_for_the_dialog(self):
        with mock.patch.object(app_settings, "FILE", self.file / "nope" / "settings.json"):
            with self.assertRaises(OSError):
                app_settings.save_mqtt("h", 1, "", "")

    def test_parse_port(self):
        for value, expected in (("1883", 1883), (" 8883 ", 8883), (1, 1), (65535, 65535), ("0", None),
                                (65536, None), ("abc", None), ("", None), (None, None), (True, None),
                                (18.5, None), ("18.5", None), ("-1", None)):
            self.assertEqual(app_settings.parse_port(value), expected, repr(value))


if __name__ == "__main__":
    unittest.main()
