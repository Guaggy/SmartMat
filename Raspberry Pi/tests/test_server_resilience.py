"""Server loops keep going when one mat fails, do not raise false alerts after a clock jump, and the database
is set up for an SD card that loses power."""

import contextlib
import io
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from server.__main__ import REPORT_EVERY_S, Server
from server.alerts import AlertManager
from server.store import Store


class ServerLoopTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.store = Store(self.dir / "smartmat.db")
        self.addCleanup(self.store.close)

    def server(self, demo=2, **alert_args):
        server = Server(self.store, AlertManager(**alert_args), demo=demo, use_mqtt=False)
        self.addCleanup(server.stop)
        return server

    def run_quietly(self, function, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            function(*args)
        return out.getvalue()

    def test_a_mat_that_fails_to_read_does_not_stop_the_others(self):
        server = self.server(3)

        class Broken:
            def take(self):
                raise RuntimeError("port gone")

        server.feeds["demo-1"] = Broken()   # first in the dict: the others used to be skipped
        output = self.run_quietly(server.pump)
        self.assertIn("pump demo-1: RuntimeError: port gone", output)
        self.assertIsNone(server.engines["demo-1"].last_t)
        self.assertIsNotNone(server.engines["demo-2"].last_t)
        self.assertIsNotNone(server.engines["demo-3"].last_t)

    def test_a_mat_that_fails_to_analyse_does_not_stop_the_others(self):
        server = self.server(3)
        self.run_quietly(server.pump)

        def broken(*_):
            raise ValueError("bad grid")

        server.engines["demo-1"].snapshot = broken
        output = self.run_quietly(server.tick, time.time())
        self.assertIn("tick demo-1: ValueError: bad grid", output)
        self.assertEqual({row["chip_id"] for row in self.store._rows("SELECT chip_id FROM timeline")}, {"demo-2", "demo-3"})

    def test_a_repeating_fault_is_printed_once_a_minute(self):
        server = self.server(1)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for second in range(0, 2 * REPORT_EVERY_S, 5):
                server._report("m1", "pump", RuntimeError("x"), now=1000 + second)
        self.assertEqual(out.getvalue().count("pump m1"), 2)
        with contextlib.redirect_stdout(out):
            server._report("m2", "pump", RuntimeError("x"), now=1000)   # another mat is reported at once
        self.assertEqual(out.getvalue().count("pump m2"), 1)

    def test_a_clock_jump_does_not_raise_alerts_for_mats_that_were_just_offline(self):
        server = self.server(1, offline_hold_s=30)   # the demo mat has not been fed: offline
        server.tick(1000)                            # a Pi that has not synced its clock yet
        server.tick(1000 + 6 * 3600)                 # NTP sets the clock hours forward
        self.assertEqual(server.alerts.open_alerts(), [])
        for second in range(1, 32):                  # still offline 31 s later: now it is a real alert
            server.tick(1000 + 6 * 3600 + second)
        self.assertEqual([a["kind"] for a in server.alerts.open_alerts()], ["offline"])

    def test_without_a_jump_an_offline_mat_raises_its_alert_on_time(self):
        server = self.server(1, offline_hold_s=30)
        for second in range(0, 40, 1):
            server.tick(1000 + second)
        self.assertEqual([a["kind"] for a in server.alerts.open_alerts()], ["offline"])


class RestoredAlertWithoutAMatTests(unittest.TestCase):
    def test_an_alert_for_a_mat_that_never_comes_back_follows_the_offline_rules(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        store = Store(folder / "smartmat.db")
        self.addCleanup(store.close)
        before = AlertManager(high_hold_s=0, offline_hold_s=0, on_change=store.save_alert)
        before.update("ghost", "high", True, 0)                       # saved as open
        alerts = AlertManager(high_hold_s=0, offline_hold_s=30, on_change=store.save_alert, grace_s=60)
        alerts.restore(store.saved_alerts(), 100)
        server = Server(store, alerts, demo=0, use_mqtt=False)
        self.addCleanup(server.stop)
        for second in range(0, 29):                                   # inside the grace and the offline hold: only the saved one
            server.tick(100 + second)
        self.assertEqual([a["kind"] for a in alerts.open_alerts()], ["high_risk"])
        for second in range(29, 59):                                  # the mat has been offline for 30 s: that opens too
            server.tick(100 + second)
        self.assertEqual(sorted(a["kind"] for a in alerts.open_alerts()), ["high_risk", "offline"])
        for second in range(59, 100):                                 # grace over: the high-risk one closes
            server.tick(100 + second)
        self.assertEqual([a["kind"] for a in alerts.open_alerts()], ["offline"])
        self.assertIn("alert raised", [e["kind"] for e in store.events("ghost")])


class AlertHoldResetTests(unittest.TestCase):
    def test_reset_holds_restarts_the_count_and_keeps_open_alerts(self):
        alerts = AlertManager(high_hold_s=10, offline_hold_s=10)
        alerts.update("m1", "high", True, 0)
        [(_, raised)] = alerts.update("m1", "high", True, 10)
        alerts.update("m2", "high", True, 0)
        alerts.reset_holds()
        self.assertEqual([a["id"] for a in alerts.open_alerts()], [raised["id"]])
        self.assertEqual(alerts.update("m2", "high", True, 10), [])      # would have been raised without the reset
        self.assertEqual(len(alerts.update("m2", "high", True, 20)), 1)


class DatabaseTests(unittest.TestCase):
    def test_the_database_uses_a_write_ahead_log(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        store = Store(folder / "smartmat.db")
        self.addCleanup(store.close)
        self.assertEqual(store._rows("PRAGMA journal_mode")[0]["journal_mode"], "wal")
        store.record_states(1.0, [("m1", "left", "low")])
        self.assertEqual(len(store.timeline("m1", 0)), 1)


if __name__ == "__main__":
    unittest.main()
