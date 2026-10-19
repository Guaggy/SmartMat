"""An admin removes a retired mat from the dashboard and can bring it back; only admins edit mat details."""

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from server.__main__ import Server
from server.alerts import AlertManager
from server.app import create_app
from server.engine import MatEngine
from server.store import Store

from test_server_app import ADMIN, NURSE


class RemoveMatTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.store = Store(self.dir / "smartmat.db")
        self.addCleanup(self.store.close)
        self.now = 1000.0
        self.alerts = AlertManager(high_hold_s=0, offline_hold_s=0, on_change=self.store.save_alert)
        self.server = Server(self.store, self.alerts, demo=1, use_mqtt=False)   # demo-1: live
        self.addCleanup(self.server.stop)
        self.old = MatEngine("old-mat", 20, 20)                                  # never reported: offline
        self.old.clock = lambda: self.now
        self.server._add("old-mat", self.old, feed=mock.Mock(spec=["take", "stop"], **{"take.return_value": None}))
        self.server.pump()
        self.client = create_app(self.store, self.alerts, self.server.engines, clock=lambda: self.now,
                                 settings=self.server.settings, control=self.server).test_client()
        self.client.post("/api/users", json={"name": "Admin", "role": "admin", "new_pin": ADMIN})
        self.client.post("/api/users", json={"name": "Kari", "role": "user", "new_pin": NURSE, "pin": ADMIN})

    def post(self, url, **json):
        return self.client.post(url, json=json)

    def ids(self):
        return {row["id"] for row in self.client.get("/api/overview").get_json()["mats"]}

    def test_an_offline_mat_is_removed_everywhere_and_its_alerts_close(self):
        self.store.set_meta("old-mat", {"name": "Chair 7", "room": "12"})
        [(_, alert)] = self.alerts.update("old-mat", "offline", False, self.now)
        feed = self.server.feeds["old-mat"]
        self.assertIn("old-mat", self.ids())
        response = self.post("/api/mats/old-mat/hide", pin=ADMIN)
        self.assertEqual((response.status_code, response.get_json()["user"]), (200, "Admin"))
        self.assertNotIn("old-mat", self.ids())
        self.assertEqual(self.client.get("/api/mats/old-mat").status_code, 404)
        self.assertNotIn("old-mat", self.server.engines)
        feed.stop.assert_called_once()
        self.assertEqual(self.alerts.open_alerts(), [])
        self.assertEqual(self.client.get("/api/overview").get_json()["open_alerts"], 0)
        saved = self.store._rows("SELECT t_cleared FROM alerts WHERE id = ?", (alert["id"],))
        self.assertEqual(saved[0]["t_cleared"], self.now)
        kinds = [(e["kind"], e["user"]) for e in self.store.events("old-mat")]
        self.assertIn(("mat removed", "Admin"), kinds)
        self.assertIn(("alert cleared", None), kinds)

    def test_the_removed_mat_is_listed_for_a_restore_with_its_name(self):
        self.store.set_meta("old-mat", {"name": "Chair 7", "room": "12"})
        self.post("/api/mats/old-mat/hide", pin=ADMIN)
        [row] = self.client.get("/api/hidden-mats").get_json()["mats"]
        self.assertEqual((row["id"], row["name"], row["room"]), ("old-mat", "Chair 7", "12"))

    def test_a_mat_that_is_online_cannot_be_removed(self):
        response = self.post("/api/mats/demo-1/hide", pin=ADMIN)
        self.assertEqual((response.status_code, response.get_json()["error"]),
                         (409, "Only a mat that is offline can be removed"))
        self.assertIn("demo-1", self.ids())
        self.assertEqual(self.store.hidden_mats(), set())

    def test_only_an_admin_with_a_pin_can_remove_or_restore(self):
        self.assertEqual(self.post("/api/mats/old-mat/hide").status_code, 401)
        self.assertEqual(self.post("/api/mats/old-mat/hide", pin=NURSE).status_code, 403)
        self.assertEqual(self.post("/api/mats/old-mat/hide", pin="0000").status_code, 403)
        self.assertIn("old-mat", self.ids())
        self.post("/api/mats/old-mat/hide", pin=ADMIN)
        self.assertEqual(self.post("/api/mats/old-mat/show", pin=NURSE).status_code, 403)
        self.assertEqual(self.post("/api/mats/nope/hide", pin=ADMIN).status_code, 404)

    def test_restore_brings_the_mat_back_to_discovery_and_the_lists(self):
        self.post("/api/mats/old-mat/hide", pin=ADMIN)
        response = self.post("/api/mats/old-mat/show", pin=ADMIN)
        self.assertEqual((response.status_code, response.get_json()["user"]), (200, "Admin"))
        self.assertEqual(self.client.get("/api/hidden-mats").get_json()["mats"], [])
        self.assertEqual(self.post("/api/mats/old-mat/show", pin=ADMIN).status_code, 404)   # not removed any more
        self.assertIn(("mat restored", "Admin"), [(e["kind"], e["user"]) for e in self.store.events("old-mat")])

    def test_discovery_skips_a_removed_mat_until_it_is_restored(self):
        opened = []
        self.server.discovery = SimpleNamespace(mats={"old-mat": (20, 20)}, status={}, presets={}, value_maxes={},
                                                stop=lambda: None)
        self.server.engines.pop("old-mat")
        self.server.feeds.pop("old-mat")
        with mock.patch.object(self.server, "_open_mqtt", side_effect=opened.append), \
                mock.patch("server.__main__.threading.Thread", side_effect=lambda target, args, daemon: SimpleNamespace(
                    start=lambda: target(*args))):
            self.server.hide("old-mat", self.now)
            self.server._discover(100.0)
            self.assertEqual(opened, [])
            self.server.show("old-mat")
            self.server._discover(101.0)    # right away, not after the retry delay
            self.assertEqual(opened, ["old-mat"])

    def test_a_restart_remembers_the_removed_mats(self):
        self.post("/api/mats/old-mat/hide", pin=ADMIN)
        again = Server(self.store, AlertManager(), demo=0, use_mqtt=False)
        self.addCleanup(again.stop)
        self.assertEqual(again.hidden, {"old-mat"})

    def test_pumping_after_a_removal_is_quiet(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.post("/api/mats/old-mat/hide", pin=ADMIN)
            self.server.pump()
            self.server.tick(self.now)
        self.assertEqual(out.getvalue(), "")

    def test_without_a_runner_removing_is_refused(self):
        client = create_app(self.store, self.alerts, self.server.engines, clock=lambda: self.now).test_client()
        response = client.post("/api/mats/old-mat/hide", json={"pin": ADMIN})
        self.assertEqual(response.status_code, 501)


if __name__ == "__main__":
    unittest.main()
