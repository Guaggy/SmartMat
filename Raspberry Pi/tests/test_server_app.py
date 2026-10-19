"""Server REST API: users and PINs, alerts, metadata, profiles, the event log (Flask test client)."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import branding
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
        self.assertTrue(self.client.get("/api/users").get_json()["needs_admin"])
        self.assertTrue(self.client.get("/api/health").get_json()["needs_admin"])
        self.assertEqual(self.post("/api/users", name="X", role="user", new_pin="1111").status_code, 400)
        self.assertEqual(self.post("/api/users", name="Admin", role="admin", new_pin="12").status_code, 400)
        self.make_users()
        self.assertEqual(self.post("/api/users", name="Ola", role="user", new_pin="2222").status_code, 401)
        self.assertEqual(self.post("/api/users", name="Ola", role="user", new_pin="2222", pin=NURSE).status_code, 403)
        self.assertEqual(self.post("/api/users", name="Ola", role="user", new_pin=NURSE, pin=ADMIN).status_code, 400)
        users = self.client.get("/api/users").get_json()
        self.assertFalse(users["needs_admin"])
        self.assertFalse(self.client.get("/api/health").get_json()["needs_admin"])
        self.assertEqual([(u["name"], u["role"]) for u in users["users"]], [("Admin", "admin"), ("Kari", "user")])
        self.assertEqual(set(users["users"][0]), {"id", "name", "role", "active"})  # no PIN hash, no salt
        self.assertIs(users["users"][0]["active"], True)
        self.assertEqual(self.kinds(), [("user added", "Admin"), ("user added", "Admin")])

    def test_disable_and_reset_pin(self):
        self.make_users()
        self.assertEqual(self.put("/api/users/1", pin=ADMIN, active=False).status_code, 400)  # last admin
        self.assertEqual(self.put("/api/users/2", pin=ADMIN, new_pin="9999").status_code, 200)
        self.assertEqual(self.post("/api/alerts/nope/ack", pin=NURSE).status_code, 403)   # the old PIN is gone
        self.assertEqual(self.post("/api/alerts/nope/ack", pin="9999").status_code, 409)   # the new one is a user (no such alert)
        self.assertEqual(self.put("/api/users/2", pin=ADMIN, active=False).status_code, 200)
        self.assertEqual(self.post("/api/alerts/nope/ack", pin="9999").status_code, 403)   # a disabled user's PIN is refused


class AlertApiTests(ApiTests):
    def test_ack_by_pin_logs_the_user_and_a_wrong_pin_logs_nothing(self):
        self.make_users()
        [(_, alert)] = self.alerts.update("m1", "high", True, self.now)
        before = self.kinds()
        response = self.post(f"/api/alerts/{alert['id']}/ack", pin="0000")
        self.assertEqual((response.status_code, response.get_json()), (403, {"error": "Wrong PIN"}))
        self.assertEqual(self.kinds(), before)
        response = self.post(f"/api/alerts/{alert['id']}/ack", pin=NURSE)
        self.assertEqual((response.status_code, response.get_json()["user"]), (200, "Kari"))
        self.assertEqual(self.kinds("m1"), [("alert acknowledged", "Kari")])
        listed = self.client.get("/api/alerts").get_json()["alerts"]
        self.assertEqual([(a["id"], a["state"], a["name"]) for a in listed], [(alert["id"], "acknowledged", "m1")])
        again = self.post(f"/api/alerts/{alert['id']}/ignore", pin=NURSE)  # already handled
        self.assertEqual((again.status_code, again.get_json()["error"]), (409, "Alert already handled by Kari"))
        self.assertEqual(self.post("/api/alerts/nope/ignore", pin=NURSE).status_code, 409)

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
        self.assertEqual(self.put("/api/mats/m1/meta", pin=ADMIN, room="1").status_code, 429)
        self.now += 61
        self.assertEqual(self.put("/api/mats/m1/meta", pin=ADMIN, room="1").status_code, 200)


class LockoutOffTests(ApiTests):
    def test_never_locked(self):
        self.make_users()
        for _ in range(6):
            self.assertEqual(self.put("/api/mats/m1/meta", pin="0000", room="1").status_code, 403)
        self.assertEqual(self.put("/api/mats/m1/meta", pin=ADMIN, room="1").status_code, 200)


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
        self.assertIsInstance(data["server_time"], float)
        self.assertEqual([r["demo"] for r in rows], [True, False, False])
        self.assertEqual((rows[2]["online"], rows[2]["posture"]), (True, "centred"))
        self.assertEqual(data["open_alerts"], 0)
        self.assertEqual(self.client.get("/api/mats/m1").get_json()["snapshot"]["occupied"], True)
        self.assertEqual(self.client.get("/api/mats/nope").status_code, 404)
        self.assertIn("error", self.client.get("/api/nothing").get_json())

    def test_meta_put_shows_in_the_overview_and_the_log(self):
        self.make_users()
        refused = self.put("/api/mats/m1/meta", pin=NURSE, name="Mine", room="1")   # a nurse cannot rename mats
        self.assertEqual((refused.status_code, refused.get_json()["error"]), (403, "Only an admin can do this"))
        response = self.put("/api/mats/m1/meta", pin=ADMIN, name="Chair 3", room="204", seat="B")
        self.assertEqual((response.status_code, response.get_json()["name"]), (200, "Chair 3"))
        self.put("/api/mats/m1/meta", pin=ADMIN, unit="Ward 2")
        row = next(r for r in self.client.get("/api/overview").get_json()["mats"] if r["id"] == "m1")
        self.assertEqual((row["name"], row["room"], row["seat"], row["unit"]), ("Chair 3", "204", "B", "Ward 2"))
        self.assertEqual(self.put("/api/mats/zzz/meta", pin=ADMIN, room="1").status_code, 404)
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
        segments = self.client.get("/api/mats/m1/timeline?hours=1").get_json()["segments"]
        self.assertEqual([(s["t_start"], s["t_end"], s["posture"]) for s in segments],
                         [(100, 102, "centred"), (102, 102, "left"), (200, 200, "left")])
        self.assertEqual(self.client.get("/api/mats/m1/timeline?hours=x").status_code, 400)
        self.store.log(100, "config changed", "m1")
        self.store.purge(150 + 86400, days=1)
        self.assertEqual(len(self.store.timeline("m1", 0)), 1)
        self.assertEqual(self.store.events("m1"), [])

    def test_health_theme_and_page(self):
        self.assertTrue(self.client.get("/api/health").get_json()["ok"])
        theme = self.client.get("/api/theme").get_json()
        self.assertEqual(theme["light"], branding.PALETTE_LIGHT)
        self.assertEqual(theme["dark"], branding.PALETTE_DARK)
        self.assertEqual(theme["heatmap_stops"][0], [0.0, list(branding.HEATMAP_STOPS[0][1])])
        self.assertEqual(len(theme["heatmap_stops"]), len(branding.HEATMAP_STOPS))
        self.assertEqual(self.client.get("/api/health").headers["Cache-Control"], "no-store")


class StaticFileTests(ApiTests):
    def test_the_page_finds_its_files_at_the_root_and_under_static(self):
        page = self.client.get("/")
        for name in ("manifest.json", "app.js", "style.css", "img/icon-192.png"):
            self.assertIn(name.encode(), page.data)
            for url in ("/" + name, "/static/" + name):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, url)
                response.close()
        page.close()

    def test_unknown_paths_and_api_stay_json_errors(self):
        for url in ("/nope.js", "/img/", "/api/nothing", "/../server/app.py", "/%2e%2e/server/app.py"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 404, url)
            self.assertIn("error", response.get_json())
        self.assertIn("mats", self.client.get("/api/overview").get_json())


class ContractTests(ApiTests):
    """The shapes server/static/app.js reads (design/api-contract.md)"""

    def seat(self, row=10, steps=40):
        for step in range(steps):
            self.engines["m1"].feed(blob(row, 10) / 50 * 1000, self.now - 4 + step * 0.1)

    def test_mat_detail(self):
        self.seat()
        mat = self.client.get("/api/mats/m1").get_json()
        self.assertLessEqual({"id", "name", "room", "seat", "unit", "demo", "online", "risk", "posture",
                              "time_in_position_s", "since_relief_s", "saturated_cells", "open_alerts",
                              "snapshot", "age_s", "stale"}, set(mat))
        snap = mat["snapshot"]
        self.assertEqual(set(snap), {"unit", "scale_max", "grid", "occupied", "hotspots", "indices", "peak_kpa"})
        self.assertEqual((snap["unit"], snap["occupied"], len(snap["grid"]), len(snap["grid"][0])),
                         ("kPa", True, 20, 20))
        self.assertAlmostEqual(snap["peak_kpa"], max(max(row) for row in snap["grid"]), places=1)
        self.assertTrue(all(i["state"] in ("ok", "near", "over") for i in snap["indices"]))
        self.assertEqual((mat["stale"], mat["room"], mat["unit"]), (False, "", ""))
        self.assertAlmostEqual(mat["age_s"], 0.1, places=1)

    def test_forward_is_the_last_row_and_the_front_edge(self):
        self.seat()
        self.assertEqual(self.client.get("/api/mats/m1").get_json()["posture"], "centred")
        self.seat(row=17)   # the load moves towards the last rows
        mat = self.client.get("/api/mats/m1").get_json()
        self.assertEqual(mat["posture"], "forward")
        grid = mat["snapshot"]["grid"]
        self.assertGreater(sum(grid[19]), sum(grid[0]))   # row 0 = back, the last row = front

    def test_stale_mat_keeps_its_last_picture_and_a_new_one_has_none(self):
        self.seat()
        self.now += 60
        mat = self.client.get("/api/mats/m1").get_json()
        self.assertEqual((mat["stale"], mat["online"], mat["risk"], mat["posture"]), (True, False, "offline", "none"))
        self.assertGreater(mat["age_s"], 50)
        self.assertEqual(len(mat["snapshot"]["grid"]), 20)
        fresh = self.client.get("/api/mats/demo-1").get_json()
        self.assertEqual((fresh["snapshot"], fresh["age_s"], fresh["stale"]), (None, None, True))

    def test_unoccupied_mat_reports_how_long_nobody_sat(self):
        for step in range(100):
            self.engines["m1"].feed(np.zeros((20, 20)), self.now - 10 + step * 0.1)
        row = next(r for r in self.client.get("/api/overview").get_json()["mats"] if r["id"] == "m1")
        self.assertEqual((row["risk"], row["posture"]), ("none", "none"))
        self.assertGreater(row["time_in_position_s"], 5)

    def test_alerts_open_count_and_history(self):
        self.make_users()
        [(_, high)] = self.alerts.update("m1", "high", True, self.now - 30)
        [(_, offline)] = self.alerts.update("demo-1", "offline", False, self.now - 20)
        data = self.client.get("/api/overview").get_json()
        self.assertEqual((data["open_alerts"], {r["id"]: r["open_alerts"] for r in data["mats"]}),
                         (2, {"m1": 1, "demo-1": 1}))
        self.assertEqual(self.post(f"/api/alerts/{high['id']}/ack", pin=NURSE).get_json()["user"], "Kari")
        data = self.client.get("/api/overview").get_json()
        self.assertEqual((data["open_alerts"], {r["id"]: r["open_alerts"] for r in data["mats"]}),
                         (1, {"m1": 0, "demo-1": 1}))
        self.alerts.update("m1", "low", True, self.now)   # the condition clears: the handled alert stays listed
        listed = self.client.get("/api/alerts").get_json()["alerts"]
        self.assertEqual([(a["id"], a["kind"], a["state"], a["by"]) for a in listed],
                         [(offline["id"], "offline", "open", None), (high["id"], "high_risk", "acknowledged", "Kari")])
        self.assertLessEqual({"id", "chip_id", "name", "room", "kind", "t_raised", "state", "by"}, set(listed[0]))
        self.assertEqual(self.client.get("/api/overview").get_json()["open_alerts"], 1)

    def test_timeline_markers_come_from_the_event_log(self):
        self.make_users()
        [(_, alert)] = self.alerts.update("m1", "high", True, self.now)
        self.store.record_states(self.now, [("m1", "left", "high")])
        self.now += 5
        self.post(f"/api/alerts/{alert['id']}/ack", pin=NURSE)
        self.store.log(self.now - 7200, "alert acknowledged", "m1", "Old")      # outside the window
        self.store.log(self.now, "config changed", "m1", "Kari")                # not a handling
        self.store.log(self.now, "alert ignored", "demo-1", "Kari")             # another mat
        tl = self.client.get("/api/mats/m1/timeline?hours=1").get_json()
        self.assertEqual(tl["markers"], [{"t": self.now, "kind": "handled", "user": "Kari"}])
        self.assertEqual([(s["posture"], s["risk"]) for s in tl["segments"]], [("left", "high")])
        self.assertEqual(len(self.client.get("/api/mats/m1/timeline?hours=3").get_json()["markers"]), 2)

    def test_meta_edit_checks_the_name_and_answers_with_the_user(self):
        self.make_users()
        self.assertEqual(self.put("/api/mats/m1/meta", pin=ADMIN, name="  ", room="1").status_code, 400)
        response = self.put("/api/mats/m1/meta", pin=ADMIN, name="Chair", room="12", seat="A", unit="Ward")
        self.assertEqual((response.get_json()["ok"], response.get_json()["user"]), (True, "Admin"))

    def test_users_list_and_changes(self):
        self.make_users()
        done = self.put("/api/users/2", pin=ADMIN, active=False)
        self.assertEqual((done.get_json()["ok"], done.get_json()["updated"]["active"]), (True, False))
        self.assertEqual([u["active"] for u in self.client.get("/api/users").get_json()["users"]], [True, False])
        dup = self.post("/api/users", name="Ola", role="user", new_pin=ADMIN, pin=ADMIN)
        self.assertEqual((dup.status_code, dup.get_json()["error"]), (400, "That PIN is already in use, choose another"))


if __name__ == "__main__":
    unittest.main()
