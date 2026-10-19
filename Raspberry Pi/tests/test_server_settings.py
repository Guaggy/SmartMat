"""Admin-editable settings: REST rules, persistence in the database, and live effect on alerts, push and the engines."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from server.__main__ import Server
from server.alerts import AlertManager
from server.app import create_app
from server.engine import MatEngine, tuned_indices
from server.settings import KEYS, SPEC, Settings
from server.store import Store

from test_server_app import ADMIN, NURSE, ApiTests


class SettingsApiTests(ApiTests):
    def setUp(self):
        super().setUp()
        self.settings = Settings(self.store)
        self.client = create_app(self.store, self.alerts, self.engines, clock=lambda: self.now,
                                 settings=self.settings).test_client()
        self.make_users()

    def values(self):
        return {s["key"]: s["value"] for s in self.client.get("/api/settings").get_json()["settings"]}

    def test_everyone_can_read_the_settings_with_their_limits_and_defaults(self):
        listed = self.client.get("/api/settings").get_json()["settings"]
        self.assertEqual([s["key"] for s in listed], list(KEYS))
        hold = next(s for s in listed if s["key"] == "alert_high_hold_s")
        self.assertEqual((hold["value"], hold["default"], hold["min"], hold["max"], hold["unit"], hold["changed"]),
                         (30, 30, 5, 3600, "s", False))
        self.assertEqual({s["group"] for s in listed}, {"alerts", "risk", "mats", "posture", "data"})

    def test_only_an_admin_with_a_pin_can_change_them(self):
        values = {"alert_high_hold_s": 60}
        self.assertEqual(self.put("/api/settings", values=values).status_code, 401)
        self.assertEqual(self.put("/api/settings", pin="0000", values=values).status_code, 403)
        self.assertEqual(self.put("/api/settings", pin=NURSE, values=values).status_code, 403)
        self.assertEqual(self.values()["alert_high_hold_s"], 30)
        response = self.put("/api/settings", pin=ADMIN, values=values)
        self.assertEqual((response.status_code, response.get_json()["user"]), (200, "Admin"))
        self.assertEqual(self.values()["alert_high_hold_s"], 60)

    def test_a_change_is_logged_with_old_and_new_value_and_the_user(self):
        self.put("/api/settings", pin=ADMIN, values={"retention_days": 90, "push_enabled": False})
        self.put("/api/settings", pin=ADMIN, values={"retention_days": 90})   # nothing changes: nothing logged
        entries = [e for e in self.store.events() if e["kind"] == "settings changed"]
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0]["user"], entries[0]["detail"]),
                         ("Admin", {"retention_days": [30, 90], "push_enabled": [True, False]}))

    def test_bad_values_are_refused_and_nothing_changes(self):
        for values in ({"alert_high_hold_s": 1}, {"alert_high_hold_s": 4000}, {"alert_high_hold_s": 30.5},
                       {"alert_high_hold_s": "30"}, {"alert_high_hold_s": True}, {"push_enabled": 1},
                       {"near_percent": float("nan")}, {"nope": 1}, {}, {"posture_side_cells": 0}):
            before = self.values()
            response = self.put("/api/settings", pin=ADMIN, values=values)
            self.assertEqual(response.status_code, 400, values)
            self.assertIn("error", response.get_json())
            self.assertEqual(self.values(), before)
        before = self.values()   # one good and one bad: all or nothing
        self.assertEqual(self.put("/api/settings", pin=ADMIN, values={"retention_days": 10, "near_percent": 5}).status_code, 400)
        self.assertEqual(self.values(), before)
        self.assertEqual(self.put("/api/settings", pin=ADMIN, values=[1]).status_code, 400)

    def test_a_whole_number_may_arrive_as_a_float_and_floats_stay_floats(self):
        self.put("/api/settings", pin=ADMIN, values={"alert_high_hold_s": 45.0, "posture_hold_s": 5})
        values = self.values()
        self.assertEqual((values["alert_high_hold_s"], values["posture_hold_s"]), (45, 5.0))
        self.assertIsInstance(values["alert_high_hold_s"], int)
        self.assertIsInstance(values["posture_hold_s"], float)

    def test_null_goes_back_to_the_default(self):
        self.put("/api/settings", pin=ADMIN, values={"near_percent": 60})
        listed = {s["key"]: s for s in self.put("/api/settings", pin=ADMIN, values={"near_percent": None}).get_json()["settings"]}
        self.assertEqual((listed["near_percent"]["value"], listed["near_percent"]["changed"]), (80, False))
        self.assertEqual(self.store.saved_settings(), {})

    def test_a_default_comes_from_config(self):
        with mock.patch("server.settings.config.ALERT_OFFLINE_S", 90):
            self.assertEqual(Settings().get("alert_offline_s"), 90)
        with mock.patch("server.settings.config.ALERT_OFFLINE_S", "soon"):   # a typo in config.py: the built-in default
            self.assertEqual(Settings().get("alert_offline_s"), 30)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.store = Store(self.dir / "smartmat.db")
        self.addCleanup(self.store.close)

    def test_overrides_survive_a_restart(self):
        Settings(self.store).update({"relief_minutes": 90, "push_enabled": False})
        again = Settings(self.store)
        self.assertEqual((again.get("relief_minutes"), again.get("push_enabled")), (90, False))
        self.assertEqual(again.get("near_percent"), 80)

    def test_an_invalid_or_unknown_saved_value_is_ignored(self):
        self.store.save_settings({"retention_days": 99999, "old_key": 1, "near_percent": 70})
        settings = Settings(self.store)
        self.assertEqual((settings.get("retention_days"), settings.get("near_percent")), (30, 70))

    def test_every_setting_has_a_usable_default(self):
        settings = Settings()
        for key, _, kind, _, _, low, high, _, _ in SPEC:
            value = settings.default(key)
            self.assertIsInstance(value, kind)
            if kind is not bool:
                self.assertTrue(low <= value <= high, key)


class LiveEffectTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.store = Store(self.dir / "smartmat.db")
        self.addCleanup(self.store.close)
        self.settings = Settings(self.store)
        self.server = Server(self.store, AlertManager(), demo=2, use_mqtt=False, settings=self.settings)
        self.addCleanup(self.server.stop)

    def test_alert_holds_and_push_follow_the_settings_at_once(self):
        self.settings.update({"alert_high_hold_s": 45, "alert_offline_s": 120, "push_enabled": False})
        self.assertEqual(self.server.alerts.holds, {"high_risk": 45, "offline": 120})
        self.assertFalse(self.server.pusher.enabled)
        self.settings.update({"alert_high_hold_s": None})
        self.assertEqual(self.server.alerts.holds["high_risk"], 30)

    def test_the_stale_limit_reaches_every_engine(self):
        engine = self.server.engines["demo-1"]
        engine.last_t = 100.0
        self.assertTrue(engine.online(105))
        self.settings.update({"stale_after_s": 3})
        self.assertFalse(engine.online(105))
        self.assertFalse(self.server.engines["demo-2"].online(105))

    def test_risk_settings_change_the_indices_and_survive_a_profile_change(self):
        engine = self.server.engines["demo-1"]
        self.settings.update({"relief_minutes": 60, "near_percent": 70})
        expected = tuned_indices(60, 70)
        self.assertEqual(engine.indices.definitions, _validated(expected))
        engine.set_profile(engine.profile)            # new trackers: the settings are applied again
        self.assertEqual(engine.indices.definitions, _validated(expected))
        reference = [t["reference"] for d in engine.indices.definitions for t in d["terms"] if t.get("signal") == "since_relief"]
        self.assertEqual(reference, [3600.0])
        self.assertEqual({d["near_fraction"] for d in engine.indices.definitions}, {0.7})

    def test_a_setting_that_changes_nothing_for_an_engine_keeps_its_warning_state(self):
        engine = self.server.engines["demo-1"]
        engine.indices.states["Mat overview"] = "over"
        self.settings.update({"stale_after_s": 20})
        self.assertEqual(engine.indices.states["Mat overview"], "over")   # only relief/near restart the states

    def test_a_mat_that_connects_later_starts_with_the_current_settings(self):
        self.settings.update({"posture_hold_s": 9, "near_percent": 60})
        late = MatEngine("late", 20, 20)
        self.server._add("late", late, feed=mock.Mock())
        self.assertEqual(late.posture.hold_s, 9)
        self.assertEqual({d["near_fraction"] for d in late.indices.definitions}, {0.6})

    def test_posture_cells_reach_the_classifier(self):
        engine = self.server.engines["demo-1"]
        grid, t = self.server.feeds["demo-1"].take()
        with mock.patch("server.engine.classify_posture", return_value="centred") as classify:
            engine.feed(grid, t)
            self.assertEqual(classify.call_args.args[3:], (2.0, 2.5))      # the config.py defaults
            self.settings.update({"posture_side_cells": 9.5, "posture_forward_cells": 7.5})
            engine.feed(grid, t + 1)
            self.assertEqual(classify.call_args.args[3:], (9.5, 7.5))


def _validated(definitions):
    from processing.indices import validate_indices
    return validate_indices(definitions)


if __name__ == "__main__":
    unittest.main()
