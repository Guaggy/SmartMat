"""Scripted demo scenario: the loop through the real engine, demo mats at different phases, no push for demo mats,
the history seed tool."""

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import seed_demo_history
from server import __main__ as runner
from server.__main__ import Server, demo_profile
from server.alerts import AlertManager
from server.app import create_app
from server.demo_scenario import DEMO_RELIEF_MIN, PERIOD_S, ScenarioMat, frames, scenario_grid
from server.engine import MatEngine
from server.store import Store


class ScenarioTests(unittest.TestCase):
    def test_the_loop_is_repeatable_and_starts_empty(self):
        self.assertTrue(np.array_equal(scenario_grid(100.0), scenario_grid(100.0 + PERIOD_S)))
        self.assertLess(scenario_grid(5.0).max(), 20)          # below 1 kPa: nobody on the mat
        self.assertGreater(scenario_grid(200.0).max(), 500)    # the left hotspot at its worst
        self.assertEqual(len(frames(seconds=10, fps=2)[0]), 20)

    def test_the_real_engine_goes_through_sit_hotspot_high_relief_and_leave(self):
        engine = MatEngine("demo-1", 20, 20, profile=demo_profile(20, 20))
        engine.configure({"relief_minutes": DEMO_RELIEF_MIN, "near_percent": 80, "posture_hold_s": 3.0, "stale_after_s": 10})
        seen = {}
        t = 0.0
        while t < PERIOD_S:
            engine.clock = lambda: t
            engine.feed(scenario_grid(t), t)
            if int(t * 4) % 20 == 0:
                snap = engine.snapshot(t)
                seen.setdefault((snap["risk"], snap["occupied"]), t)
                if 255 < t < 262:
                    self.assertEqual(snap["risk"], "high")      # the alert condition holds until the lift
                if 276 < t < 300:
                    self.assertEqual(snap["risk"], "low")       # relieved by the lift
            t += 0.25
        for state in (("none", False), ("low", True), ("medium", True), ("high", True)):
            self.assertIn(state, seen)
        self.assertEqual(engine.snapshot(t)["risk"], "none")    # left the mat, ready for the next loop

    def test_mats_play_at_different_phases_and_speed_scales_the_clock(self):
        now = [100.0]
        mats = [ScenarioMat(offset_s=PERIOD_S * i / 3, speed=2.0, wall=lambda: now[0]) for i in range(3)]
        now[0] += 10
        takes = [m.take() for m in mats]
        self.assertEqual({t for _, t in takes}, {120.0})        # 10 s wall at speed 2
        self.assertEqual(len({grid.tobytes() for grid, _ in takes}), 3)


class ServerDemoTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.store = Store(self.dir / "smartmat.db")
        self.addCleanup(self.store.close)

    def server(self, **kwargs):
        alerts = AlertManager(on_change=self.store.save_alert)
        server = Server(self.store, alerts, use_mqtt=False, **kwargs)
        self.addCleanup(server.stop)
        return server

    def test_demo_mats_are_flagged_offset_and_use_the_demo_settings(self):
        server = self.server(demo=4, demo_scenario=True, demo_speed=3.0)
        offsets = [feed.offset_s for feed in server.feeds.values()]
        self.assertEqual(len(set(offsets)), 4)
        self.assertEqual(server.engines["demo-1"].params["relief_minutes"], DEMO_RELIEF_MIN)
        self.assertEqual(server.alerts.chip_holds["demo-1"]["high_risk"], runner.DEMO_SCENARIO_HOLD_S / 3.0)
        server.pump()
        server.tick(time.time())
        client = create_app(self.store, server.alerts, server.engines).test_client()
        rows = client.get("/api/overview").get_json()["mats"]
        self.assertTrue(rows and all(row["demo"] for row in rows))

    def test_the_default_is_the_recording_and_the_speed_is_capped(self):
        server = self.server(demo=1)
        self.assertEqual(server.scenario_mats, set())
        self.assertEqual(self.server(demo=1, demo_scenario=True, demo_speed=99).demo_speed, runner.MAX_DEMO_SPEED)

    def test_demo_alerts_do_not_push_unless_enabled(self):
        server = self.server()
        raised = {"id": "a", "chip_id": "demo-1", "kind": "high_risk"}
        with mock.patch.object(server.alerts, "update", return_value=[("raised", raised)]), \
                mock.patch.object(server.pusher, "notify") as notify:
            server._update_alerts("demo-1", "high", True, 1.0)
            notify.assert_not_called()
            server._update_alerts("sm-101", "high", True, 1.0)
            self.assertEqual(notify.call_count, 1)
            with mock.patch.object(runner, "DEMO_PUSH", True):
                server._update_alerts("demo-1", "high", True, 2.0)
            self.assertEqual(notify.call_count, 2)

    def test_the_alerts_list_marks_demo_alerts(self):
        server = self.server()
        server.alerts.set_holds("demo-1", 0, 0)
        server.alerts.set_holds("sm-1", 0, 0)
        server.alerts.update("demo-1", "high", True, 1.0)
        server.alerts.update("sm-1", "high", True, 1.0)
        rows = create_app(self.store, server.alerts, server.engines).test_client().get("/api/alerts").get_json()["alerts"]
        self.assertEqual({row["chip_id"]: row["demo"] for row in rows}, {"demo-1": True, "sm-1": False})


class SeedTests(unittest.TestCase):
    def test_a_fast_simulation_fills_history_for_demo_mats_only(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        store = Store(folder / "smartmat.db")
        self.addCleanup(store.close)
        end = 1_800_000_000.0
        count = seed_demo_history.seed(store, mats=1, days=0.03, end=end, interval_s=120)   # 43 minutes of the loop
        self.assertGreater(count, 15)
        rows, _ = store.snapshots("demo-1", end - 86400, end, 10000, with_grids=True)
        self.assertIn("periodic", {r["reason"] for r in rows})
        self.assertIn("alert_raised", {r["reason"] for r in rows})
        self.assertIn("alert_cleared", {r["reason"] for r in rows})
        self.assertTrue(all(r["t"] <= end for r in rows))
        self.assertEqual(store.snapshots("sm-101")[0], [])
        self.assertIn("demo history seeded", [e["kind"] for e in store.events()])
        self.assertTrue(any(r["repositions"] for r in rows) or any(r["movements"] for r in rows))


if __name__ == "__main__":
    unittest.main()
