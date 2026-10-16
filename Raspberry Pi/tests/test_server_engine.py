"""Server pipeline without a GUI: posture, risk, the mat engine on the seat recording, alerts."""

import json
import unittest
from pathlib import Path

import numpy as np

import config
from processing.calibration import IndividualCalibration, UniformCalibration
from processing.posture import PostureTracker, classify_posture, risk_from, risk_sort_key
from server.alerts import AlertManager
from server.engine import MatEngine, grid_shape

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "seat_take1.json"


def load_sample():
    data = json.loads(SAMPLE.read_text())
    return [(np.asarray(f["raw"], dtype=float), f["timestamp"]) for f in data["frames"]]


def blob(row, col, rows=20, cols=20, kpa=30.0):
    grid = np.zeros((rows, cols))
    grid[row - 2:row + 3, col - 2:col + 3] = kpa
    return grid


def profile(rows=20, cols=20, mirror_h=False):
    with grid_shape(rows, cols):
        return {"format": "smartmat_mat_profile_v1", "grid_shape": [rows, cols],
                "orientation": {"rotation": 0, "mirror_h": mirror_h, "mirror_v": False},
                "baseline": None, "active": "individual",
                "individual": IndividualCalibration.default().to_dict(), "uniform": UniformCalibration().to_dict()}


class PostureTests(unittest.TestCase):
    def test_classes_from_centre_of_pressure(self):
        self.assertEqual(classify_posture(blob(9, 3), True, 2.0), "left")
        self.assertEqual(classify_posture(blob(9, 16), True, 2.0), "right")
        self.assertEqual(classify_posture(blob(16, 10), True, 2.0), "forward")
        self.assertEqual(classify_posture(blob(10, 10), True, 2.0), "centred")
        self.assertEqual(classify_posture(blob(10, 10), False, 2.0), "none")
        self.assertEqual(classify_posture(np.zeros((20, 20)), True, 2.0), "none")

    def test_debounce_and_time_in_position(self):
        tracker = PostureTracker(hold_s=3)
        tracker.update("centred", 0)
        tracker.update("left", 1)
        self.assertEqual(tracker.update("left", 3.9), "centred")   # not held long enough
        self.assertEqual(tracker.time_in_position(3.9), 3.9)
        tracker.update("centred", 4)                              # flicker back: no change
        tracker.update("left", 5)
        self.assertEqual(tracker.update("left", 8), "left")
        self.assertEqual(tracker.time_in_position(10), 2)
        tracker.update("left", 20, reposition=True)               # a reposition restarts the count
        self.assertEqual(tracker.time_in_position(21), 1)
        tracker.update("none", 22)
        tracker.update("none", 25)
        self.assertIsNone(tracker.time_in_position(26))

    def test_risk_levels_and_sort_order(self):
        self.assertEqual(risk_from(["over", "ok"], True, True), "high")
        self.assertEqual(risk_from(["near"], True, True), "medium")
        self.assertEqual(risk_from(["ok", "inactive"], True, True), "low")
        self.assertEqual(risk_from(["over"], False, True), "none")
        self.assertEqual(risk_from(["over"], True, False), "offline")
        rows = [{"risk": "low", "time_in_position_s": 5}, {"risk": "none", "time_in_position_s": None},
                {"risk": "high", "time_in_position_s": 1}, {"risk": "low", "time_in_position_s": 50},
                {"risk": "offline", "time_in_position_s": None}, {"risk": "medium", "time_in_position_s": 2}]
        self.assertEqual([(r["risk"], r["time_in_position_s"]) for r in sorted(rows, key=risk_sort_key)],
                         [("offline", None), ("high", 1), ("medium", 2), ("low", 50), ("low", 5), ("none", None)])


class EngineTests(unittest.TestCase):
    def test_seat_recording_becomes_occupied_and_reports_a_snapshot(self):
        engine = MatEngine("maxraysusb", 20, 20, 255)
        frames = load_sample()
        start = frames[0][1]
        for grid, t in frames[:20]:
            engine.feed(grid, t)
        self.assertFalse(engine.snapshot(frames[19][1])["occupied"])
        for grid, t in frames[20:]:
            engine.feed(grid, t)
        snap = engine.snapshot(frames[-1][1])
        self.assertTrue(snap["occupied"])
        self.assertTrue(snap["online"])
        self.assertIn(snap["posture"], ("left", "right", "forward", "centred"))
        self.assertIn(snap["risk"], ("high", "medium", "low"))
        self.assertGreater(snap["time_in_position_s"], 0)
        self.assertLessEqual(snap["time_in_position_s"], frames[-1][1] - start)
        self.assertEqual(snap["unit"], "kPa")
        self.assertEqual(len(snap["grid"]), 20)
        self.assertGreaterEqual(snap["saturated_cells"], 1)  # the last frame has cells at 1000
        self.assertIsNotNone(snap["since_relief_s"])
        json.dumps(snap)  # JSON-ready
        stale = engine.snapshot(frames[-1][1] + config.STALE_AFTER_S + 1)
        self.assertEqual((stale["online"], stale["risk"], stale["posture"]), (False, "offline", "none"))

    def test_orientation_from_the_profile_is_respected(self):
        left = blob(9, 3) / 50 * 1000  # default curve: 1000 = 50 kPa
        for mirror, expected in ((False, "left"), (True, "right")):
            engine = MatEngine("abc", 20, 20, profile=profile(mirror_h=mirror))
            for step in range(60):
                engine.feed(left, step * 0.1)
            self.assertEqual(engine.snapshot(6.0)["posture"], expected)

    def test_profile_for_another_grid_is_refused_or_ignored(self):
        engine = MatEngine("abc", 16, 15, profile=profile())
        self.assertIsNotNone(engine.profile_error)
        with self.assertRaises(ValueError):
            engine.set_profile(profile())
        engine.set_profile(dict(profile(16, 15), version=3))
        self.assertEqual(engine.profile_version, 3)

    def test_time_going_back_starts_over(self):
        engine = MatEngine("abc", 20, 20)
        grid = blob(10, 10) / 50 * 1000
        for step in range(50):
            engine.feed(grid, 100 + step * 0.1)
        self.assertTrue(engine.snapshot(105)["occupied"])
        engine.feed(grid, 1.0)
        self.assertEqual(engine.posture.changed_at, 1.0)   # fresh trackers, not a negative interval
        self.assertEqual(engine.snapshot(1.0)["time_in_position_s"], 0)


class AlertTests(unittest.TestCase):
    def test_high_risk_raises_after_the_hold_and_clears(self):
        alerts = AlertManager(high_hold_s=30, offline_hold_s=30)
        self.assertEqual(alerts.update("m1", "high", True, 0), [])
        self.assertEqual(alerts.update("m1", "high", True, 29), [])
        [(kind, alert)] = alerts.update("m1", "high", True, 30)
        self.assertEqual((kind, alert["kind"], alert["chip_id"]), ("raised", "high", "m1"))
        self.assertEqual(alerts.update("m1", "high", True, 40), [])  # one alert per episode
        self.assertEqual(len(alerts.open_alerts()), 1)
        handled = alerts.acknowledge(alert["id"], "Kari", 41)
        self.assertEqual((handled["state"], handled["user"]), ("acknowledged", "Kari"))
        self.assertEqual(alerts.open_alerts()[0]["state"], "acknowledged")  # open until the condition clears
        [(kind, cleared)] = alerts.update("m1", "medium", True, 50)
        self.assertEqual((kind, cleared["id"], cleared["t_cleared"]), ("cleared", alert["id"], 50))
        self.assertEqual(alerts.open_alerts(), [])
        with self.assertRaises(KeyError):
            alerts.ignore(alert["id"], "Kari", 51)

    def test_a_dip_restarts_the_hold_and_offline_has_its_own_alert(self):
        alerts = AlertManager(high_hold_s=30, offline_hold_s=10)
        alerts.update("m1", "high", True, 0)
        alerts.update("m1", "low", True, 20)
        self.assertEqual(alerts.update("m1", "high", True, 45), [])
        self.assertEqual(alerts.update("m1", "offline", False, 46), [])
        [(kind, alert)] = alerts.update("m1", "offline", False, 56)
        self.assertEqual((kind, alert["kind"]), ("raised", "offline"))
        self.assertEqual(alerts.open_alerts("m2"), [])
        ignored = alerts.ignore(alert["id"], "Ola", 57)
        self.assertEqual((ignored["state"], ignored["user"]), ("ignored", "Ola"))


if __name__ == "__main__":
    unittest.main()
