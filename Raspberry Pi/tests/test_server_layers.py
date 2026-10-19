"""Settings in layers (factory, site, mat): resolution, validation across layers, versions, rollback, and what they do to
the engines, the alert delays and the alerts themselves; plus the REST routes for a mat's own settings."""

import shutil
import tempfile
import unittest
from pathlib import Path

import config
from server.__main__ import Server
from server.alerts import AlertManager
from server.app import create_app
from server.settings import SITE, Settings
from server.store import Store

from test_server_app import ADMIN, NURSE, ApiTests

TWO_INDICES = [
    {"name": "Load", "layer": "map", "threshold": 1.0, "near_fraction": 0.5,
     "terms": [{"signal": "exposure", "window_min": 15, "reference": 100.0, "weight": 1.0, "inverted": False}]},
    {"name": "Overview", "layer": "summary", "threshold": 1.0, "near_fraction": 0.5,
     "terms": [{"source": "Load", "reducer": "peak", "region": "mat", "reference": 1.0, "weight": 1.0, "inverted": False}]},
]


class ResolutionTests(unittest.TestCase):
    def test_a_mat_overrides_the_site_which_overrides_the_factory(self):
        settings = Settings()
        self.assertEqual((settings.get("near_percent"), settings.get("near_percent", "m1"), settings.source("near_percent", "m1")), (80, 80, "factory"))
        settings.update({"near_percent": 70})
        self.assertEqual((settings.get("near_percent", "m1"), settings.source("near_percent", "m1")), (70, "site"))
        settings.update({"near_percent": 60}, scope="m1")
        self.assertEqual((settings.get("near_percent"), settings.get("near_percent", "m1"), settings.get("near_percent", "m2")), (70, 60, 70))
        self.assertEqual(settings.source("near_percent", "m1"), "mat")

    def test_a_mat_page_shows_value_source_and_the_value_it_falls_back_to(self):
        settings = Settings()
        settings.update({"alert_high_hold_s": 45})
        settings.update({"alert_high_hold_s": 10}, scope="m1")
        item = next(i for i in settings.describe("m1") if i["key"] == "alert_high_hold_s")
        self.assertEqual((item["value"], item["default"], item["changed"], item["source"]), (10, 45, True, "mat"))
        other = next(i for i in settings.describe("m2") if i["key"] == "alert_high_hold_s")
        self.assertEqual((other["value"], other["default"], other["changed"], other["source"]), (45, 45, False, "site"))
        self.assertNotIn("push_enabled", [i["key"] for i in settings.describe("m1")])   # whole-installation settings are not per mat
        self.assertIn("push_enabled", [i["key"] for i in settings.describe()])

    def test_none_makes_a_mat_inherit_again(self):
        settings = Settings()
        settings.update({"near_percent": 60}, scope="m1")
        settings.update({"near_percent": None}, scope="m1")
        self.assertEqual((settings.get("near_percent", "m1"), settings.source("near_percent", "m1")), (80, "factory"))

    def test_a_site_change_reaches_mats_that_do_not_override_it_only(self):
        settings = Settings()
        settings.update({"stale_after_s": 20}, scope="m1")
        settings.update({"stale_after_s": 30})
        self.assertEqual((settings.get("stale_after_s", "m1"), settings.get("stale_after_s", "m2")), (20, 30))

    def test_refusals_leave_everything_as_it_was(self):
        settings = Settings()
        with self.assertRaises(ValueError):
            settings.update({"push_enabled": False}, scope="m1")           # for the whole installation
        with self.assertRaises(ValueError):
            settings.update({"near_percent": 70, "nope": 1}, scope="m1")   # one good, one unknown
        with self.assertRaises(ValueError):
            settings.update({"hotspots.min_cells": 0.5}, scope="m1")       # not a whole number
        with self.assertRaises(ValueError):
            settings.update({"temporal.exposure_mode": "Sometimes"})
        self.assertEqual((settings.version(), settings.version("m1"), settings.get("near_percent", "m1")), (0, 0, 80))

    def test_thresholds_must_stay_in_order_across_layers(self):
        settings = Settings()                                   # factory: activate 20, deactivate 15
        with self.assertRaisesRegex(ValueError, "Hotspot"):     # the layer alone is checked against what it inherits
            settings.update({"hotspots.deactivate_kpa": 25}, scope="m1")
        settings.update({"hotspots.activate_kpa": 18}, scope="m1")           # fine: 18 > the inherited 15
        with self.assertRaisesRegex(ValueError, r"\(mat m1\)"):              # valid for the site (20 > 19), but not for m1 (18 < 19)
            settings.update({"hotspots.deactivate_kpa": 19})
        self.assertEqual((settings.get("hotspots.deactivate_kpa"), settings.version()), (15.0, 0))   # the refused change did not happen
        settings.update({"hotspots.deactivate_kpa": 12})                      # a change that keeps every mat valid is accepted
        self.assertEqual(settings.get("hotspots.deactivate_kpa", "m1"), 12.0)

    def test_custom_indices_are_checked_and_can_be_cleared(self):
        settings = Settings()
        settings.update({"indices": TWO_INDICES}, scope="m1")
        self.assertEqual([d["name"] for d in settings.get("indices", "m1")], ["Load", "Overview"])
        self.assertIsNone(settings.get("indices", "m2"))
        with self.assertRaises(ValueError):
            settings.update({"indices": [{"name": "Broken"}]}, scope="m1")
        settings.update({"indices": None}, scope="m1")
        self.assertIsNone(settings.get("indices", "m1"))


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.settings = Settings(clock=lambda: self.now)

    def test_every_change_is_a_numbered_version_with_who_why_and_what(self):
        self.settings.update({"near_percent": 70}, user="Kari", reason="too many alerts")
        self.now += 60
        self.settings.update({"near_percent": 65, "relief_minutes": 90}, user="Ola")
        first, second = self.settings.history()[1], self.settings.history()[0]
        self.assertEqual((first["version"], first["user"], first["reason"], first["t"]), (1, "Kari", "too many alerts", 1000.0))
        self.assertEqual(first["changes"], {"near_percent": [80, 70]})
        self.assertEqual((second["version"], second["user"], second["t"]), (2, "Ola", 1060.0))
        self.assertEqual(second["changes"], {"near_percent": [70, 65], "relief_minutes": [120, 90]})
        self.assertEqual(self.settings.version(), 2)

    def test_each_scope_counts_its_own_versions(self):
        self.settings.update({"near_percent": 70})
        self.settings.update({"near_percent": 60}, scope="m1")
        self.settings.update({"relief_minutes": 60}, scope="m1")
        self.assertEqual((self.settings.version(), self.settings.version("m1"), self.settings.version("m2")), (1, 2, 0))
        self.assertEqual([h["version"] for h in self.settings.history("m1")], [2, 1])
        self.assertEqual(self.settings.history("m2"), [])

    def test_a_change_that_changes_nothing_makes_no_version(self):
        self.settings.update({"near_percent": 70})
        self.assertEqual(self.settings.update({"near_percent": 70}), {})
        self.assertEqual(self.settings.update({"relief_minutes": None}), {})   # already inheriting
        self.assertEqual(self.settings.version(), 1)

    def test_pinning_a_value_equal_to_the_inherited_one_is_a_change(self):
        self.settings.update({"near_percent": 80}, scope="m1")   # same as the site value, but now the mat holds it itself
        self.assertEqual(self.settings.version("m1"), 1)
        self.settings.update({"near_percent": 70})
        self.assertEqual(self.settings.get("near_percent", "m1"), 80)

    def test_rollback_is_a_new_version_and_the_history_stays(self):
        self.settings.update({"near_percent": 70}, reason="a")
        self.settings.update({"near_percent": 60, "relief_minutes": 90}, reason="b")
        self.settings.rollback(SITE, 1, user="Admin", reason="b was wrong")
        self.assertEqual((self.settings.get("near_percent"), self.settings.get("relief_minutes"), self.settings.version()), (70, 120, 3))
        last = self.settings.history()[0]
        self.assertEqual((last["version"], last["user"], last["reason"]), (3, "Admin", "b was wrong"))
        self.assertEqual(len(self.settings.history()), 3)
        self.settings.rollback(SITE, 0)   # version 0 is the factory state
        self.assertEqual((self.settings.get("near_percent"), self.settings.version()), (80, 4))
        self.assertEqual(self.settings.history()[0]["reason"], "rolled back to version 0")
        with self.assertRaises(KeyError):
            self.settings.rollback(SITE, 99)

    def test_rolling_back_to_what_is_already_there_changes_nothing(self):
        self.settings.update({"near_percent": 70})
        self.assertEqual(self.settings.rollback(SITE, 1), {})
        self.assertEqual(self.settings.version(), 1)

    def test_the_stamp_names_both_versions(self):
        self.assertEqual(self.settings.stamp("m1"), "s0.m0")
        self.settings.update({"near_percent": 70})
        self.settings.update({"near_percent": 60}, scope="m1")
        self.settings.update({"relief_minutes": 60}, scope="m1")
        self.assertEqual((self.settings.stamp("m1"), self.settings.stamp("m2"), self.settings.stamp()), ("s1.m2", "s1.m0", "s1"))

    def test_listeners_hear_the_scope_once_and_may_read_the_settings(self):
        heard = []
        self.settings.listen(lambda scope: heard.append((scope, self.settings.get("near_percent", "m1"))), call=False)
        self.settings.update({"near_percent": 70})
        self.settings.update({"near_percent": 60}, scope="m1")
        self.settings.update({"near_percent": 60}, scope="m1")   # nothing changed: not announced
        self.assertEqual(heard, [("site", 70), ("m1", 60)])


class PersistenceTests(unittest.TestCase):
    def test_layers_versions_and_history_survive_a_restart(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        store = Store(folder / "smartmat.db")
        settings = Settings(store)
        settings.update({"near_percent": 70}, user="Kari", reason="x")
        settings.update({"stale_after_s": 20}, scope="m1", user="Ola")
        settings.update({"stale_after_s": 25}, scope="m1", user="Ola")
        store.close()
        store = Store(folder / "smartmat.db")
        self.addCleanup(store.close)
        again = Settings(store)
        self.assertEqual((again.get("near_percent"), again.get("stale_after_s", "m1"), again.stamp("m1")), (70, 25, "s1.m2"))
        self.assertEqual([(h["version"], h["user"]) for h in again.history("m1")], [(2, "Ola"), (1, "Ola")])
        self.assertEqual(again.rollback("m1", 1)["stale_after_s"], (25, 20))
        self.assertEqual(again.history("m1")[0]["version"], 3)


class EffectTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.store = Store(self.dir / "smartmat.db")
        self.addCleanup(self.store.close)
        self.settings = Settings(self.store)
        self.alerts = AlertManager(on_change=self.store.save_alert, stamp=self.settings.stamp)
        self.server = Server(self.store, self.alerts, demo=2, use_mqtt=False, settings=self.settings)
        self.addCleanup(self.server.stop)
        self.one, self.two = self.server.engines["demo-1"], self.server.engines["demo-2"]

    def test_the_engineering_preset_is_per_mat(self):
        self.settings.update({"hotspots.activate_kpa": 33.0, "contact_threshold_kpa": 2.5}, scope="demo-1")
        self.assertEqual((self.one.hotspots.activate_kpa, self.one.contact_threshold_kpa), (33.0, 2.5))
        self.assertEqual((self.two.hotspots.activate_kpa, self.two.contact_threshold_kpa), (20.0, config.CONTACT_THRESHOLD_KPA))
        self.settings.update({"movement.major_score": 0.8})        # the site layer: both mats, the first keeps its own values
        self.assertEqual((self.one.motion.major_score, self.two.motion.major_score), (0.8, 0.8))
        self.assertEqual(self.one.hotspots.activate_kpa, 33.0)

    def test_what_a_mat_overrides_survives_a_profile_change_and_inheriting_again(self):
        self.settings.update({"hotspots.activate_kpa": 33.0}, scope="demo-1")
        self.one.set_profile(self.one.profile)                      # new trackers
        self.assertEqual(self.one.hotspots.activate_kpa, 33.0)
        self.settings.update({"hotspots.activate_kpa": None}, scope="demo-1")
        self.assertEqual(self.one.hotspots.activate_kpa, 20.0)

    def test_a_change_to_the_preset_only_touches_the_mat_it_is_for(self):
        self.one.hotspots.created_total = 7
        self.two.hotspots.created_total = 9
        self.settings.update({"hotspots.min_cells": 3}, scope="demo-1")
        self.assertEqual(self.one.hotspots.min_cells, 3)
        self.assertEqual(self.two.hotspots.min_cells, self.settings.default("hotspots.min_cells"))   # mat two was not touched
        self.assertEqual((self.one.hotspots.created_total, self.two.hotspots.created_total), (7, 9))   # counters are kept

    def test_custom_indices_are_per_mat(self):
        self.settings.update({"indices": TWO_INDICES}, scope="demo-1")
        self.assertEqual([d["name"] for d in self.one.indices.definitions], ["Load", "Overview"])
        self.assertEqual([d["name"] for d in self.two.indices.definitions], ["Sustained load", "Mat overview"])
        self.settings.update({"relief_minutes": 60}, scope="demo-1")   # the risk knobs only tune the built-in indices
        self.assertEqual([d["name"] for d in self.one.indices.definitions], ["Load", "Overview"])
        self.settings.update({"indices": None}, scope="demo-1")
        reference = [t["reference"] for d in self.one.indices.definitions for t in d["terms"] if t.get("signal") == "since_relief"]
        self.assertEqual(reference, [3600.0])

    def test_alert_delays_are_per_mat(self):
        self.settings.update({"alert_high_hold_s": 5}, scope="demo-1")
        for chip in ("demo-1", "demo-2"):
            self.alerts.update(chip, "high", True, 0)
        raised = {chip: self.alerts.update(chip, "high", True, 6) for chip in ("demo-1", "demo-2")}
        self.assertEqual((len(raised["demo-1"]), len(raised["demo-2"])), (1, 0))      # demo-2 still waits its 30 s
        self.settings.update({"alert_high_hold_s": 8})                                 # the site layer: demo-1 keeps its own 5 s
        self.assertEqual(self.alerts.chip_holds["demo-1"]["high_risk"], 5)
        self.assertEqual(self.alerts.chip_holds["demo-2"]["high_risk"], 8)
        self.assertEqual(self.alerts.holds["high_risk"], 8)

    def test_a_mat_that_connects_later_starts_with_its_saved_layer(self):
        from server.engine import MatEngine
        self.settings.update({"hotspots.activate_kpa": 31.0, "alert_offline_s": 7}, scope="late")
        late = MatEngine("late", 20, 20)
        self.server._add("late", late, feed=None)
        self.assertEqual(late.hotspots.activate_kpa, 31.0)
        self.assertEqual(self.alerts.chip_holds["late"]["offline"], 7)

    def test_an_alert_carries_the_settings_version_that_raised_it_and_keeps_it(self):
        self.settings.update({"alert_high_hold_s": 5})
        self.settings.update({"alert_high_hold_s": 5, "near_percent": 70}, scope="demo-1")
        self.alerts.update("demo-1", "high", True, 0)
        [(_, alert)] = self.alerts.update("demo-1", "high", True, 5)
        self.assertEqual(alert["config"], "s1.m1")
        self.settings.update({"near_percent": 60}, scope="demo-1")   # later changes do not rewrite it
        self.assertEqual(self.alerts.open_alerts()[0]["config"], "s1.m1")
        self.assertEqual(self.store.saved_alerts()[0]["config"], "s1.m1")
        restored = AlertManager(stamp=self.settings.stamp)
        restored.restore(self.store.saved_alerts(), 100)
        self.assertEqual(restored.open_alerts()[0]["config"], "s1.m1")

    def test_an_old_database_gets_the_alert_column(self):
        import sqlite3
        path = self.dir / "old.db"
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE alerts (id TEXT PRIMARY KEY, chip_id TEXT NOT NULL, kind TEXT NOT NULL, t_raised REAL NOT NULL,"
                   " since REAL, t_cleared REAL, state TEXT NOT NULL, by TEXT, t_handled REAL)")
        db.execute("INSERT INTO alerts (id, chip_id, kind, t_raised, state) VALUES ('a', 'm', 'offline', 1.0, 'open')")
        db.commit()
        db.close()
        store = Store(path)
        self.addCleanup(store.close)
        self.assertEqual(store.saved_alerts()[0]["config"], None)
        store.save_alert(dict(store.saved_alerts()[0], config="s1.m0"))
        self.assertEqual(store.saved_alerts()[0]["config"], "s1.m0")


class MatConfigApiTests(ApiTests):
    def setUp(self):
        super().setUp()
        self.settings = Settings(self.store)
        self.client = create_app(self.store, self.alerts, self.engines, clock=lambda: self.now, settings=self.settings).test_client()
        self.make_users()

    def get(self, url):
        return self.client.get(url)

    def test_a_mats_page_lists_its_settings_with_source_and_version(self):
        self.put("/api/settings", pin=ADMIN, values={"near_percent": 70})
        page = self.get("/api/mats/m1/config").get_json()
        self.assertEqual((page["scope"], page["version"], page["stamp"]), ("m1", 0, "s1.m0"))
        item = next(i for i in page["settings"] if i["key"] == "near_percent")
        self.assertEqual((item["value"], item["source"], item["changed"]), (70, "site", False))
        self.assertEqual(self.get("/api/mats/nope/config").status_code, 404)

    def test_an_admin_sets_a_mats_own_value_with_a_reason(self):
        response = self.put("/api/mats/m1/config", pin=ADMIN, values={"near_percent": 60, "hotspots.activate_kpa": 28}, reason="soft cushion")
        body = response.get_json()
        self.assertEqual((response.status_code, body["user"], body["stamp"]), (200, "Admin", "s0.m1"))
        item = next(i for i in body["settings"] if i["key"] == "near_percent")
        self.assertEqual((item["value"], item["source"], item["changed"]), (60, "mat", True))
        self.assertEqual(self.settings.get("near_percent"), 80)          # the site layer is untouched
        event = next(e for e in self.store.events("m1") if e["kind"] == "config changed")
        self.assertEqual((event["user"], event["detail"]["scope"], event["detail"]["version"], event["detail"]["reason"]), ("Admin", "m1", 1, "soft cushion"))
        self.assertEqual(event["detail"]["changes"]["near_percent"], [80, 60])

    def test_only_an_admin_with_a_pin_can_change_a_mat(self):
        values = {"near_percent": 60}
        self.assertEqual(self.put("/api/mats/m1/config", values=values).status_code, 401)
        self.assertEqual(self.put("/api/mats/m1/config", pin="0000", values=values).status_code, 403)
        self.assertEqual(self.put("/api/mats/m1/config", pin=NURSE, values=values).status_code, 403)
        self.assertEqual(self.put("/api/mats/nope/config", pin=ADMIN, values=values).status_code, 404)
        self.assertEqual(self.settings.version("m1"), 0)

    def test_bad_input_is_a_400_and_changes_nothing(self):
        for values, reason in (({"push_enabled": False}, ""), ({"nope": 1}, ""), ({"near_percent": 5}, ""), ({}, ""), ([1], ""),
                               ({"hotspots.deactivate_kpa": 99}, ""), ({"near_percent": 60}, "x" * 201), ({"near_percent": 60}, 5)):
            response = self.put("/api/mats/m1/config", pin=ADMIN, values=values, reason=reason)
            self.assertEqual(response.status_code, 400, values)
            self.assertIn("error", response.get_json())
        self.assertEqual(self.settings.version("m1"), 0)

    def test_history_lists_versions_newest_first_and_needs_a_known_mat(self):
        self.put("/api/mats/m1/config", pin=ADMIN, values={"near_percent": 60}, reason="one")
        self.put("/api/mats/m1/config", pin=ADMIN, values={"near_percent": 55}, reason="two")
        data = self.get("/api/config/history?scope=m1").get_json()
        self.assertEqual((data["scope"], data["version"], [h["version"] for h in data["history"]], [h["reason"] for h in data["history"]]),
                         ("m1", 2, [2, 1], ["two", "one"]))
        self.assertEqual(data["history"][0]["user"], "Admin")
        self.assertEqual(self.get("/api/config/history").get_json()["history"], [])           # the site layer has none yet
        self.assertEqual(self.get("/api/config/history?scope=nope").status_code, 404)
        self.assertEqual(self.get("/api/config/history?limit=abc").status_code, 400)
        self.assertEqual(len(self.get("/api/config/history?scope=m1&limit=1").get_json()["history"]), 1)

    def test_rollback_needs_an_admin_and_makes_a_new_version(self):
        self.put("/api/mats/m1/config", pin=ADMIN, values={"near_percent": 60})
        self.put("/api/mats/m1/config", pin=ADMIN, values={"near_percent": 55})
        self.assertEqual(self.post("/api/config/rollback", pin=NURSE, scope="m1", version=1).status_code, 403)
        self.assertEqual(self.post("/api/config/rollback", pin=ADMIN, scope="m1", version=99).status_code, 404)
        self.assertEqual(self.post("/api/config/rollback", pin=ADMIN, scope="m1", version="1").status_code, 400)
        self.assertEqual(self.post("/api/config/rollback", pin=ADMIN, scope="nope", version=1).status_code, 404)
        response = self.post("/api/config/rollback", pin=ADMIN, scope="m1", version=1, reason="55 was too sensitive")
        body = response.get_json()
        self.assertEqual((response.status_code, body["version"], body["changed"]), (200, 3, 1))
        self.assertEqual(self.settings.get("near_percent", "m1"), 60)
        self.assertEqual(self.get("/api/config/history?scope=m1").get_json()["history"][0]["reason"], "55 was too sensitive")
        site = self.post("/api/config/rollback", pin=ADMIN, version=0)   # the site layer, nothing to undo
        self.assertEqual((site.status_code, site.get_json()["changed"]), (200, 0))

    def test_the_alert_list_shows_which_settings_raised_each_alert(self):
        settings = Settings(self.store)
        alerts = AlertManager(high_hold_s=0, stamp=settings.stamp)
        client = create_app(self.store, alerts, self.engines, clock=lambda: self.now, settings=settings).test_client()
        settings.update({"near_percent": 70}, scope="m1")
        alerts.update("m1", "high", True, self.now)
        listed = client.get("/api/alerts").get_json()["alerts"]
        self.assertEqual(listed[0]["config"], "s0.m1")


if __name__ == "__main__":
    unittest.main()
