"""Alerts survive a server restart: saved to the database, restored open, not raised (or pushed) a second time."""

import shutil
import tempfile
import unittest
from pathlib import Path

from server.alerts import AlertManager
from server.store import Store


class AlertPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.stores = []

    def open_server(self, now):
        """A 'started' server: a store on the same file and a manager restored from it"""
        store = Store(self.dir / "smartmat.db")
        self.stores.append(store)
        alerts = AlertManager(high_hold_s=10, offline_hold_s=10, on_change=store.save_alert, grace_s=60)
        alerts.restore(store.saved_alerts(), now)
        return store, alerts

    def tearDown(self):
        for store in self.stores:
            store.close()

    def test_raise_handle_and_clear_are_saved(self):
        store, alerts = self.open_server(0)
        alerts.update("m1", "high", True, 0)
        [(_, alert)] = alerts.update("m1", "high", True, 10)
        self.assertEqual([a["id"] for a in store.saved_alerts()], [alert["id"]])
        alerts.acknowledge(alert["id"], "Kari", 12)
        saved = store.saved_alerts()[0]
        self.assertEqual((saved["state"], saved["by"], saved["t_cleared"]), ("acknowledged", "Kari", None))
        alerts.update("m1", "low", True, 20)
        saved = store.saved_alerts()[0]
        self.assertEqual((saved["state"], saved["t_cleared"]), ("acknowledged", 20))

    def test_a_restart_keeps_an_open_alert_and_does_not_raise_it_again(self):
        _, alerts = self.open_server(0)
        alerts.update("m1", "high", True, 0)
        [(_, alert)] = alerts.update("m1", "high", True, 10)
        _, restarted = self.open_server(100)
        self.assertEqual([a["id"] for a in restarted.open_alerts()], [alert["id"]])
        self.assertEqual(restarted.update("m1", "high", True, 110), [])   # still high: same alert, nothing raised
        self.assertEqual([a["id"] for a in restarted.open_alerts()], [alert["id"]])

    def test_an_acknowledgement_survives_a_restart(self):
        _, alerts = self.open_server(0)
        alerts.update("m1", "high", True, 0)
        [(_, alert)] = alerts.update("m1", "high", True, 10)
        alerts.acknowledge(alert["id"], "Kari", 11)
        _, restarted = self.open_server(100)
        [again] = restarted.open_alerts()
        self.assertEqual((again["state"], again["by"]), ("acknowledged", "Kari"))
        self.assertEqual(restarted.update("m1", "high", True, 105), [])

    def test_a_restored_alert_is_kept_while_the_mat_is_silent_after_the_restart(self):
        _, alerts = self.open_server(0)
        alerts.update("m1", "high", True, 0)
        alerts.update("m1", "high", True, 10)
        _, restarted = self.open_server(100)
        restarted.update("m1", "offline", False, 101)    # no frame yet, so the engine reports offline
        restarted.update("m1", "offline", False, 105)
        self.assertEqual([a["kind"] for a in restarted.open_alerts()], ["high_risk"])

    def test_a_restored_alert_clears_when_the_mat_reports_a_better_state(self):
        _, alerts = self.open_server(0)
        alerts.update("m1", "high", True, 0)
        alerts.update("m1", "high", True, 10)
        store, restarted = self.open_server(100)
        [(kind, cleared)] = restarted.update("m1", "low", True, 105)
        self.assertEqual((kind, restarted.open_alerts()), ("cleared", []))
        self.assertEqual(store.saved_alerts(), [])   # cleared and never handled: nothing to keep
        self.assertEqual([row["t_cleared"] for row in store._rows("SELECT t_cleared FROM alerts")], [105])

    def test_a_restored_alert_clears_when_the_mat_never_reports_again(self):
        _, alerts = self.open_server(0)
        alerts.update("m1", "high", True, 0)
        alerts.update("m1", "high", True, 10)
        _, restarted = self.open_server(100)
        restarted.update("m1", "offline", False, 150)
        events = restarted.update("m1", "offline", False, 161)   # grace over: the high-risk alert goes, an offline one starts
        self.assertEqual([(kind, alert["kind"]) for kind, alert in events], [("cleared", "high_risk"), ("raised", "offline")])
        self.assertEqual([a["kind"] for a in restarted.open_alerts()], ["offline"])

    def test_handled_and_cleared_alerts_come_back_as_history(self):
        _, alerts = self.open_server(0)
        alerts.update("m1", "high", True, 0)
        [(_, alert)] = alerts.update("m1", "high", True, 10)
        alerts.ignore(alert["id"], "Ola", 11)
        alerts.update("m1", "low", True, 20)
        _, restarted = self.open_server(100)
        [shown] = restarted.recent()
        self.assertEqual((shown["id"], shown["state"], shown["t_cleared"]), (alert["id"], "ignored", 20))
        self.assertEqual(restarted.open_alerts(), [])

    def test_purge_drops_old_cleared_alerts_only(self):
        store, alerts = self.open_server(0)
        alerts.update("m1", "high", True, 0)
        [(_, old)] = alerts.update("m1", "high", True, 10)
        alerts.ignore(old["id"], "Ola", 11)
        alerts.update("m1", "low", True, 20)
        alerts.update("m2", "high", True, 0)
        [(_, current)] = alerts.update("m2", "high", True, 10)
        store.purge(40 * 86400, days=30)
        self.assertEqual([a["id"] for a in store.saved_alerts()], [current["id"]])

    def test_without_a_callback_nothing_is_saved(self):
        alerts = AlertManager(high_hold_s=0)
        [(kind, _)] = alerts.update("m1", "high", True, 0)
        self.assertEqual(kind, "raised")


if __name__ == "__main__":
    unittest.main()
