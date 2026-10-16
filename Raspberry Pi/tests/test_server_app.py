"""Server REST API: users and PINs, alerts, metadata, profiles, the event log (Flask test client)."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from processing import calibration
from server.alerts import AlertManager
from server.app import create_app
from server.engine import MatEngine
from server.store import Store
from test_server_engine import blob, profile  # pytest puts tests/ on sys.path

ADMIN, NURSE = "1234", "5678"


class ApiTests(unittest.TestCase):
    lockout = 0

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        patcher = mock.patch.object(calibration, "PROFILES_DIR", self.dir / "profiles")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.now = 1000.0
        self.store = Store(self.dir / "smartmat.db", lockout_attempts=self.lockout, lockout_s=60)
        self.addCleanup(self.store.close)
        self.alerts = AlertManager(high_hold_s=0, offline_hold_s=0)
        self.engines = {"m1": MatEngine("m1", 20, 20), "demo-1": MatEngine("demo-1", 20, 20)}
        for engine in self.engines.values():
            engine.clock = lambda: self.now
        self.client = create_app(self.store, self.alerts, self.engines, clock=lambda: self.now).test_client()

    def post(self, url, **json):
        return self.client.post(url, json=json)

    def put(self, url, **json):
        return self.client.put(url, json=json)

    def make_users(self):
        self.assertEqual(self.post("/api/users", name="Admin", role="admin", new_pin=ADMIN).status_code, 201)
        self.assertEqual(self.post("/api/users", name="Kari", role="user", new_pin=NURSE, pin=ADMIN).status_code, 201)

    def kinds(self, chip_id=None):
        return [(e["kind"], e["user"]) for e in self.store.events(chip_id)]


class UserTests(ApiTests):
    def test_first_admin_bootstrap_then_admins_only(self):
        self.assertTrue(self.client.get("/api/users").get_json()["setup"])
        self.assertEqual(self.post("/api/users", name="X", role="user", new_pin="1111").status_code, 400)
        self.assertEqual(self.post("/api/users", name="Admin", role="admin", new_pin="12").status_code, 400)
        self.make_users()
        self.assertEqual(self.post("/api/users", name="Ola", role="user", new_pin="2222").status_code, 401)
        self.assertEqual(self.post("/api/users", name="Ola", role="user", new_pin="2222", pin=NURSE).status_code, 403)
        self.assertEqual(self.post("/api/users", name="Ola", role="user", new_pin=NURSE, pin=ADMIN).status_code, 400)
        users = self.client.get("/api/users").get_json()
        self.assertFalse(users["setup"])
        self.assertEqual([(u["name"], u["role"]) for u in users["users"]], [("Admin", "admin"), ("Kari", "user")])
        self.assertNotIn("pin_hash", users["users"][0])
        self.assertEqual(self.kinds(), [("user added", "Admin"), ("user added", "Admin")])

    def test_disable_and_reset_pin(self):
        self.make_users()
        self.assertEqual(self.put("/api/users/1", pin=ADMIN, active=False).status_code, 400)  # last admin
        self.assertEqual(self.put("/api/users/2", pin=ADMIN, new_pin="9999").status_code, 200)
        self.assertEqual(self.put("/api/mats/m1/meta", pin=NURSE, room="1").status_code, 403)
        self.assertEqual(self.put("/api/mats/m1/meta", pin="9999", room="1").status_code, 200)
        self.assertEqual(self.put("/api/users/2", pin=ADMIN, active=False).status_code, 200)
        self.assertEqual(self.put("/api/mats/m1/meta", pin="9999", room="1").status_code, 403)


class AlertApiTests(ApiTests):
    def test_ack_by_pin_logs_the_user_and_a_wrong_pin_logs_nothing(self):
        self.make_users()
        [(_, alert)] = self.alerts.update("m1", "high", True, self.now)
        before = self.kinds()
        response = self.post(f"/api/alerts/{alert['id']}/ack", pin="0000")
        self.assertEqual((response.status_code, response.get_json()), (403, {"error": "wrong PIN"}))
        self.assertEqual(self.kinds(), before)
        response = self.post(f"/api/alerts/{alert['id']}/ack", pin=NURSE)
        self.assertEqual((response.status_code, response.get_json()["user"]), (200, "Kari"))
        self.assertEqual(self.kinds("m1"), [("alert acknowledged", "Kari")])
        listed = self.client.get("/api/alerts").get_json()["alerts"]
        self.assertEqual([(a["id"], a["state"], a["name"]) for a in listed], [(alert["id"], "acknowledged", "m1")])
        self.assertEqual(self.post("/api/alerts/nope/ignore", pin=NURSE).status_code, 404)

    def test_no_write_without_a_pin(self):
        self.make_users()
        [(_, alert)] = self.alerts.update("m1", "high", True, self.now)
        for response in (self.post(f"/api/alerts/{alert['id']}/ack"), self.put("/api/mats/m1/meta", room="2"),
                         self.put("/api/mats/m1/profile", profile=profile()),
                         self.client.put("/api/mats/m1/meta", data="room=2")):
            self.assertIn(response.status_code, (400, 401))
            self.assertIn("error", response.get_json())
        self.assertEqual(self.kinds("m1"), [])
        self.assertEqual(self.alerts.open_alerts()[0]["state"], "open")


class LockoutOnTests(ApiTests):
    lockout = 2

    def test_locked_after_wrong_pins_until_the_time_passes(self):
        self.make_users()
        for _ in range(2):
            self.assertEqual(self.put("/api/mats/m1/meta", pin="0000", room="1").status_code, 403)
        self.assertEqual(self.put("/api/mats/m1/meta", pin=NURSE, room="1").status_code, 429)
        self.now += 61
        self.assertEqual(self.put("/api/mats/m1/meta", pin=NURSE, room="1").status_code, 200)


class LockoutOffTests(ApiTests):
    def test_never_locked(self):
        self.make_users()
        for _ in range(6):
            self.assertEqual(self.put("/api/mats/m1/meta", pin="0000", room="1").status_code, 403)
        self.assertEqual(self.put("/api/mats/m1/meta", pin=NURSE, room="1").status_code, 200)


class MatApiTests(ApiTests):
    def test_overview_rows_sorted_worst_first(self):
        grid = blob(10, 10) / 50 * 1000
        for step in range(40):
            self.engines["m1"].feed(grid, self.now - 4 + step * 0.1)
        self.store.set_meta("old1", {"name": "Old"})  # known from mats.json, never seen
        data = self.client.get("/api/overview").get_json()
        rows = data["mats"]
        self.assertEqual([(r["id"], r["risk"]) for r in rows],
                         [("demo-1", "offline"), ("old1", "offline"), ("m1", "low")])
        self.assertEqual(set(rows[0]), {"id", "name", "room", "seat", "unit", "demo", "online", "risk", "posture",
                                        "time_in_position_s", "saturated", "saturated_cells", "open_alerts",
                                        "since_relief_s"})
        self.assertEqual([r["demo"] for r in rows], [True, False, False])
        self.assertEqual((rows[2]["online"], rows[2]["posture"]), (True, "centred"))
        self.assertEqual(data["open_alerts"], 0)
        self.assertEqual(self.client.get("/api/mats/m1").get_json()["snapshot"]["occupied"], True)
        self.assertEqual(self.client.get("/api/mats/nope").status_code, 404)
        self.assertIn("error", self.client.get("/api/nothing").get_json())

    def test_meta_put_shows_in_the_overview_and_the_log(self):
        self.make_users()
        response = self.put("/api/mats/m1/meta", pin=NURSE, name="Chair 3", room="204", seat="B")
        self.assertEqual((response.status_code, response.get_json()["name"]), (200, "Chair 3"))
        self.put("/api/mats/m1/meta", pin=NURSE, unit="Ward 2")
        row = next(r for r in self.client.get("/api/overview").get_json()["mats"] if r["id"] == "m1")
        self.assertEqual((row["name"], row["room"], row["seat"], row["unit"]), ("Chair 3", "204", "B", "Ward 2"))
        self.assertEqual(self.put("/api/mats/zzz/meta", pin=NURSE, room="1").status_code, 404)
        log = self.client.get("/api/mats/m1/log").get_json()["events"]
        self.assertEqual([e["detail"] for e in log], [{"meta": {"unit": "Ward 2"}},  # newest first
                                                      {"meta": {"name": "Chair 3", "room": "204", "seat": "B"}}])

    def test_profile_put_bumps_the_version_and_saves_the_file(self):
        self.make_users()
        self.assertEqual(self.client.get("/api/mats/m1/profile").get_json()["version"], 0)
        response = self.put("/api/mats/m1/profile", pin=NURSE, profile=profile(mirror_h=True))
        self.assertEqual((response.status_code, response.get_json()["version"]), (200, 1))
        got = self.client.get("/api/mats/m1/profile").get_json()
        self.assertEqual((got["version"], got["profile"]["orientation"]["mirror_h"]), (1, True))
        self.assertTrue(calibration.load_profile("m1")["orientation"]["mirror_h"])
        self.assertEqual(self.put("/api/mats/m1/profile", pin=NURSE, profile=profile(16, 15)).status_code, 400)
        self.assertEqual(self.put("/api/mats/m1/profile", pin=NURSE, profile={"x": 1}).status_code, 400)
        self.assertEqual(self.engines["m1"].profile_version, 1)
        self.assertEqual(self.put("/api/mats/m1/profile", pin=ADMIN, profile=profile()).get_json()["version"], 2)
        self.assertEqual(self.kinds("m1"), [("calibration pushed", "Admin"), ("calibration pushed", "Kari")])

    def test_timeline_and_retention(self):
        self.store.record_states(100, [("m1", "centred", "low")])
        self.store.record_states(101, [("m1", "centred", "low")])
        self.store.record_states(102, [("m1", "left", "medium")])
        self.store.record_states(200, [("m1", "left", "medium")])  # after a gap: a new segment
        self.now = 300
        segments = self.client.get("/api/mats/m1/timeline?hours=1").get_json()["timeline"]
        self.assertEqual([(s["t_start"], s["t_end"], s["posture"]) for s in segments],
                         [(100, 102, "centred"), (102, 102, "left"), (200, 200, "left")])
        self.assertEqual(self.client.get("/api/mats/m1/timeline?hours=x").status_code, 400)
        self.store.log(100, "config changed", "m1")
        self.store.purge(150 + 86400, days=1)
        self.assertEqual(len(self.store.timeline("m1", 0)), 1)
        self.assertEqual(self.store.events("m1"), [])

    def test_health_theme_and_page(self):
        self.assertTrue(self.client.get("/api/health").get_json()["ok"])
        self.assertIn("palette_light", self.client.get("/api/theme").get_json())
        page = self.client.get("/")
        self.assertIn(b"/api/overview", page.data)
        page.close()


if __name__ == "__main__":
    unittest.main()
