"""Snapshot history, CSV exports, forgetting a retired mat, open alerts across a restart (server/history.py, store.py, app.py)."""

import csv
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from server.__main__ import Server
from server.alerts import AlertManager
from server.app import create_app
from server.engine import MatEngine
from server.history import HistoryRecorder
from server.store import Store

from test_server_app import ADMIN, NURSE
from test_server_engine import blob, profile


def fed_engine(chip_id="m1", kpa_blob=True):
    """A calibrated mat that has seen a few seconds of a loaded seat"""
    engine = MatEngine(chip_id, 20, 20, profile=profile())
    for i in range(12):
        engine.feed(blob(9, 10, kpa=400.0) if kpa_blob else np.zeros((20, 20)), 100.0 + i * 0.5)
    engine.clock = lambda: engine.last_t
    return engine


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.store = Store(self.dir / "smartmat.db")
        self.addCleanup(self.store.close)


class RecorderTests(Base):
    def test_a_periodic_snapshot_holds_the_grid_the_peak_grid_and_the_numbers(self):
        engine = fed_engine()
        recorder = HistoryRecorder(self.store, interval_s=300)
        snap = engine.snapshot()
        recorder.observe("m1", snap, engine, 1000.0)               # first sight starts the interval
        self.assertEqual(self.store.snapshots("m1")[0], [])
        gone = dict(snap, grid=[[0.0] * 20 for _ in range(20)])    # the load leaves, the peak must remember it
        recorder.observe("m1", gone, engine, 1100.0)
        recorder.observe("m1", gone, engine, 1300.0)
        [row], more = self.store.snapshots("m1", with_grids=True)
        self.assertFalse(more)
        self.assertEqual((row["reason"], row["t"], row["rows"], row["cols"], row["unit"]), ("periodic", 1300.0, 20, 20, "kPa"))
        self.assertEqual(max(map(max, row["grid"])), 0)
        self.assertGreater(max(map(max, row["peak_grid"])), 0)
        self.assertEqual(len(row["grid"]), 20)
        self.assertEqual(row["risk"], snap["risk"])
        self.assertTrue(snap["peak_kpa"])

    def test_the_numbers_come_from_the_engine(self):
        engine = fed_engine()
        recorder = HistoryRecorder(self.store, interval_s=10)
        recorder.observe("m1", engine.snapshot(), engine, 1000.0)
        recorder.observe("m1", engine.snapshot(), engine, 1010.0)
        [row], _ = self.store.snapshots("m1")
        self.assertGreater(row["contact_cells"], 0)
        self.assertIsNotNone(row["peak_kpa"])
        for key in ("score", "posture", "occupied", "hotspots", "time_in_position_s", "since_movement_s", "movements",
                    "repositions", "load_kg", "contact_area_cm2"):
            self.assertIn(key, row)
        self.assertEqual(row["contact_cells"], int(((np.array(engine.snapshot()["grid"], dtype=float)) >= engine.contact_threshold_kpa).sum()))

    def test_an_alert_writes_a_snapshot_and_an_offline_mat_without_engine_still_does(self):
        engine = fed_engine()
        recorder = HistoryRecorder(self.store)
        recorder.alert("raised", {"id": "a1", "chip_id": "m1", "kind": "high_risk"}, engine.snapshot(), engine, 2000.0)
        recorder.alert("cleared", {"id": "a2", "chip_id": "gone", "kind": "offline"}, None, None, 2001.0)
        [raised], _ = self.store.snapshots("m1")
        self.assertEqual((raised["reason"], raised["alert_id"], raised["alert_kind"]), ("alert_raised", "a1", "high_risk"))
        self.assertIsNone(self.store.snapshot("m1", raised["id"])["peak_grid"])
        [cleared], _ = self.store.snapshots("gone", with_grids=True)
        self.assertEqual((cleared["reason"], cleared["grid"], cleared["risk"]), ("alert_cleared", None, "offline"))

    def test_an_offline_mat_gets_no_periodic_snapshot_and_the_interval_restarts_when_it_is_back(self):
        engine = fed_engine()
        recorder = HistoryRecorder(self.store, interval_s=10)
        snap = engine.snapshot()
        recorder.observe("m1", snap, engine, 0.0)
        recorder.observe("m1", dict(snap, online=False), engine, 20.0)
        recorder.observe("m1", snap, engine, 21.0)
        self.assertEqual(self.store.snapshots("m1")[0], [])
        recorder.observe("m1", snap, engine, 31.0)
        self.assertEqual(len(self.store.snapshots("m1")[0]), 1)

    def test_disabled_writes_nothing(self):
        engine = fed_engine()
        recorder = HistoryRecorder(self.store, enabled=False, interval_s=0)
        recorder.observe("m1", engine.snapshot(), engine, 0.0)
        recorder.observe("m1", engine.snapshot(), engine, 5.0)
        recorder.alert("raised", {"id": "a", "chip_id": "m1", "kind": "high_risk"}, engine.snapshot(), engine, 6.0)
        self.assertEqual(self.store.snapshots("m1")[0], [])

    def test_a_snapshot_is_small_and_retention_removes_old_ones(self):
        engine = fed_engine()
        recorder = HistoryRecorder(self.store, interval_s=1)
        recorder.observe("m1", engine.snapshot(), engine, 0.0)
        recorder.observe("m1", engine.snapshot(), engine, 1.0)
        with self.store._lock:
            size = self.store._db.execute("SELECT LENGTH(grid) + LENGTH(peak_grid) + LENGTH(data) FROM snapshots").fetchone()[0]
        self.assertLess(size, 1500)
        self.store.purge(40 * 86400, days=30)
        self.assertEqual(self.store.snapshots("m1")[0], [])

    def test_a_failing_store_does_not_stop_the_tick(self):
        engine = fed_engine()
        recorder = HistoryRecorder(self.store, interval_s=0)
        with mock.patch.object(self.store, "add_snapshot", side_effect=RuntimeError("disk full")), \
                mock.patch("builtins.print"):
            recorder.observe("m1", engine.snapshot(), engine, 0.0)
            recorder.observe("m1", engine.snapshot(), engine, 1.0)


class ApiBase(Base):
    def setUp(self):
        super().setUp()
        self.now = 10000.0
        self.alerts = AlertManager(high_hold_s=0, offline_hold_s=0, on_change=self.store.save_alert)
        self.server = Server(self.store, self.alerts, demo=0, use_mqtt=False)
        self.addCleanup(self.server.stop)
        self.engine = fed_engine()
        self.server._add("m1", self.engine, feed=mock.Mock(spec=["take", "stop"], **{"take.return_value": None}))
        self.client = create_app(self.store, self.alerts, self.server.engines, clock=lambda: self.now,
                                 settings=self.server.settings, control=self.server).test_client()
        self.client.post("/api/users", json={"name": "Admin", "role": "admin", "new_pin": ADMIN})
        self.client.post("/api/users", json={"name": "Kari", "role": "user", "new_pin": NURSE, "pin": ADMIN})
        recorder = HistoryRecorder(self.store, interval_s=300)
        for i in range(5):    # 5 periodic snapshots 5 minutes apart
            recorder.observe("m1", self.engine.snapshot(), self.engine, 9000.0 + i * 300)
            recorder.observe("m1", self.engine.snapshot(), self.engine, 9000.0 + i * 300 + 300)

    def post(self, url, **json):
        return self.client.post(url, json=json)


class HistoryApiTests(ApiBase):
    def test_list_has_no_grids_and_is_oldest_first(self):
        data = self.client.get("/api/mats/m1/history?from=9000&to=11000").get_json()
        self.assertTrue(data["enabled"])
        times = [s["t"] for s in data["snapshots"]]
        self.assertEqual(times, sorted(times))
        self.assertGreaterEqual(len(times), 4)
        self.assertNotIn("grid", data["snapshots"][0])
        self.assertFalse(data["truncated"])
        self.assertEqual(data["snapshots"][0]["reason"], "periodic")

    def test_limit_marks_truncation_and_after_pages_on(self):
        first = self.client.get("/api/mats/m1/history?from=0&to=20000&limit=2").get_json()
        self.assertTrue(first["truncated"])
        self.assertEqual(first["next_from"], first["snapshots"][-1]["t"])
        second = self.client.get(f"/api/mats/m1/history?from={first['next_from']}&after=1&limit=2").get_json()
        self.assertTrue(set(s["id"] for s in first["snapshots"]).isdisjoint(s["id"] for s in second["snapshots"]))

    def test_bulk_form_carries_grids_and_is_capped(self):
        data = self.client.get("/api/mats/m1/history?from=0&to=20000&with_grids=1&limit=99999").get_json()
        first = data["snapshots"][0]
        self.assertEqual((len(first["grid"]), len(first["grid"][0])), (20, 20))
        self.assertEqual(len(first["peak_grid"]), 20)
        self.assertLessEqual(len(data["snapshots"]), 300)

    def test_detail_and_errors(self):
        snap_id = self.client.get("/api/mats/m1/history?from=0&to=20000").get_json()["snapshots"][0]["id"]
        detail = self.client.get(f"/api/mats/m1/history/{snap_id}").get_json()
        self.assertEqual(len(detail["grid"]), 20)
        self.assertEqual(self.client.get("/api/mats/m1/history/9999").status_code, 404)
        self.assertEqual(self.client.get("/api/mats/nope/history").status_code, 404)
        self.assertEqual(self.client.get("/api/mats/m1/history?from=abc").status_code, 400)
        self.server.engines["m2"] = MatEngine("m2", 20, 20)
        self.assertEqual(self.client.get(f"/api/mats/m2/history/{snap_id}").status_code, 404)   # another mat's snapshot


class ExportTests(ApiBase):
    def rows(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.mimetype == "text/csv")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        return list(csv.reader(io.StringIO(response.get_data(as_text=True))))

    def test_history_csv(self):
        rows = self.rows("/api/mats/m1/history.csv?from=0&to=20000")
        self.assertEqual(rows[0][:4], ["time_iso", "t", "reason", "risk"])
        self.assertGreaterEqual(len(rows), 5)
        self.assertTrue(rows[1][0].endswith("Z"))
        self.assertEqual(self.client.get("/api/mats/nope/history.csv").status_code, 404)

    def test_repositioning_csv_has_moves_per_hour_from_the_counter(self):
        self.store.add_snapshot(100.0, "m1", "periodic", {"posture": "left", "occupied": True, "repositions": 2, "movements": 5,
                                                          "since_movement_s": 40.0, "since_reposition_s": 900.0})
        self.store.add_snapshot(1900.0, "m1", "periodic", {"posture": "right", "occupied": True, "repositions": 3, "movements": 9,
                                                           "since_movement_s": 10.0, "since_reposition_s": 60.0})
        self.store.add_snapshot(2000.0, "m1", "alert_raised", {"posture": "right"})   # alert rows are not in this file
        self.store.add_snapshot(5500.0, "m1", "periodic", {"posture": "right", "occupied": True, "repositions": 1})   # counter restarted
        rows = self.rows("/api/mats/m1/repositioning.csv?from=50&to=6000")
        self.assertEqual(rows[0][-1], "repositions_per_hour")
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[1][-1], "")
        self.assertEqual(float(rows[2][-1]), 2.0)          # 1 repositioning in half an hour
        self.assertEqual(float(rows[3][-1]), round(1 / (3600 / 3600), 2))   # restart: counted from zero, one hour

    def test_audit_csv_lists_who_when_why(self):
        self.client.put("/api/settings", json={"pin": ADMIN, "values": {"near_percent": 70}, "reason": "softer cushion"})
        rows = self.rows("/api/export/audit.csv")
        self.assertEqual(rows[0], ["time_iso", "t", "kind", "mat", "user", "reason", "detail"])
        changed = next(r for r in rows if r[2] == "config changed")
        self.assertEqual((changed[4], changed[5]), ("Admin", "softer cushion"))
        self.assertEqual(len(self.rows("/api/export/audit.csv?from=1&to=2")), 1)    # header only


class ForgetTests(ApiBase):
    def setUp(self):
        super().setUp()
        self.old = MatEngine("old-mat", 20, 20)
        self.old.clock = lambda: self.now
        self.server._add("old-mat", self.old, feed=mock.Mock(spec=["take", "stop"], **{"take.return_value": None}))
        self.alerts.set_holds("old-mat", 0, 0)
        self.alerts.update("old-mat", "offline", False, self.now)

    def ids(self):
        return {row["id"] for row in self.client.get("/api/overview").get_json()["mats"]}

    def test_forget_removes_closes_alerts_clears_the_broker_and_logs_why(self):
        self.server.discovery = SimpleNamespace(mats={"old-mat": (20, 20)}, status={}, presets={}, value_maxes={}, stop=lambda: None)
        with mock.patch("paho.mqtt.publish.multiple") as publish:
            response = self.post("/api/mats/old-mat/forget", pin=ADMIN, reason="chair scrapped")
        self.assertEqual(response.get_json(), {"ok": True, "user": "Admin", "broker_cleared": True})
        [call] = publish.call_args_list
        self.assertEqual([(m["topic"], m["payload"], m["retain"]) for m in call.args[0]],
                         [("smartmat/old-mat/meta", b"", True), ("smartmat/old-mat/status", b"", True)])
        self.assertNotIn("old-mat", self.ids())
        self.assertEqual(self.alerts.open_alerts("old-mat"), [])
        self.assertNotIn("old-mat", self.server.discovery.mats)
        event = next(e for e in self.store.events("old-mat") if e["kind"] == "mat forgotten")
        self.assertEqual((event["user"], event["detail"]["reason"]), ("Admin", "chair scrapped"))
        self.assertEqual(event["detail"]["broker_cleared"], True)
        self.assertIn("old-mat", [m["id"] for m in self.client.get("/api/hidden-mats").get_json()["mats"]])

    def test_an_unreachable_broker_still_forgets_the_mat(self):
        self.server.discovery = SimpleNamespace(mats={}, status={}, presets={}, value_maxes={}, stop=lambda: None)
        with mock.patch("paho.mqtt.publish.multiple", side_effect=OSError("no broker")), mock.patch("builtins.print"):
            response = self.post("/api/mats/old-mat/forget", pin=ADMIN)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["broker_cleared"])
        self.assertNotIn("old-mat", self.ids())

    def test_restore_brings_it_back_like_show(self):
        with mock.patch("paho.mqtt.publish.multiple"):
            self.post("/api/mats/old-mat/forget", pin=ADMIN)
        self.assertEqual(self.post("/api/mats/old-mat/restore", pin=NURSE).status_code, 403)
        self.assertEqual(self.post("/api/mats/old-mat/restore", pin=ADMIN).status_code, 200)
        self.assertEqual(self.post("/api/mats/old-mat/restore", pin=ADMIN).status_code, 404)
        self.assertNotIn("old-mat", self.server.hidden)

    def test_pin_rules_and_refusals(self):
        self.assertEqual(self.post("/api/mats/old-mat/forget").status_code, 401)
        self.assertEqual(self.post("/api/mats/old-mat/forget", pin=NURSE).status_code, 403)
        self.assertEqual(self.post("/api/mats/nope/forget", pin=ADMIN).status_code, 404)
        self.assertEqual(self.post("/api/mats/old-mat/forget", pin=ADMIN, reason="x" * 201).status_code, 400)
        self.now += 1
        self.engine.status = None
        self.assertEqual(self.post("/api/mats/m1/forget", pin=ADMIN).status_code, 409)    # m1 is live
        bare = create_app(self.store, self.alerts, self.server.engines, clock=lambda: self.now).test_client()
        self.assertEqual(bare.post("/api/mats/old-mat/forget", json={"pin": ADMIN}).status_code, 501)


class TickIntegrationTests(Base):
    def test_the_tick_writes_periodic_and_alert_snapshots(self):
        alerts = AlertManager(high_hold_s=0, offline_hold_s=0, on_change=self.store.save_alert)
        server = Server(self.store, alerts, demo=0, use_mqtt=False, history=HistoryRecorder(self.store, interval_s=2))
        self.addCleanup(server.stop)
        engine = fed_engine()
        server._add("m1", engine, feed=mock.Mock(spec=["take", "stop"], **{"take.return_value": None}))
        engine.clock = lambda: engine.last_t + 1
        alerts.set_holds("m1", 0, 0)
        with mock.patch.object(server.pusher, "notify"):
            for second in range(4):
                server.tick(500.0 + second)
        reasons = [s["reason"] for s in self.store.snapshots("m1")[0]]
        self.assertIn("periodic", reasons)
        server.engines["m1"].status = "offline"
        server.tick(510.0)
        self.assertIn("alert_raised", [s["reason"] for s in self.store.snapshots("m1")[0]])   # the offline alert


class RestartTests(Base):
    def test_a_restarted_server_keeps_an_open_alert_and_pushes_nothing(self):
        alerts = AlertManager(high_hold_s=0, offline_hold_s=0, on_change=self.store.save_alert)
        server = Server(self.store, alerts, demo=0, use_mqtt=False)
        engine = fed_engine()
        engine.status = "offline"
        server._add("m1", engine, feed=mock.Mock(spec=["take", "stop"], **{"take.return_value": None}))
        alerts.set_holds("m1", 0, 0)
        with mock.patch.object(server.pusher, "notify") as notify:
            server.tick(500.0)
            self.assertEqual(notify.call_count, 1)
        [first] = alerts.open_alerts()
        server.stop()
        again = AlertManager(high_hold_s=0, offline_hold_s=0, on_change=self.store.save_alert)
        again.restore(self.store.saved_alerts(), 600.0)
        second = Server(self.store, again, demo=0, use_mqtt=False)
        self.addCleanup(second.stop)
        with mock.patch.object(second.pusher, "notify") as notify:
            second.tick(610.0)      # no engine yet, inside the grace time
            second.tick(620.0)
            notify.assert_not_called()
        [restored] = again.open_alerts()
        self.assertEqual((restored["id"], restored["t_raised"]), (first["id"], first["t_raised"]))
        self.assertEqual([e["kind"] for e in self.store.events("m1") if e["kind"] == "alert raised"], ["alert raised"])


if __name__ == "__main__":
    unittest.main()
