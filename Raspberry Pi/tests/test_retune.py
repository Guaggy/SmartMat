"""Retuned defaults on the one real seat take, and the relative hotspot rule / relief grace."""

from pathlib import Path
import runpy
import sys
import unittest

import numpy as np

import config

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR / "tools"))

from replay_tune import replay  # noqa: E402
from processing.hotspots import HotspotTracker  # noqa: E402
from processing.settings import default_settings, validate_settings  # noqa: E402
from processing.temporal import TemporalAnalysis  # noqa: E402

SAMPLE = APP_DIR / "samples" / "seat_take1.json"
TUNED = ("CONTACT_THRESHOLD_KPA", "HOTSPOT_ACTIVATE_KPA", "HOTSPOT_DEACTIVATE_KPA", "HOTSPOT_ACTIVATE_FRACTION",
         "HOTSPOT_DEACTIVATE_FRACTION", "HOTSPOT_MIN_CELLS", "HOTSPOT_END_RELIEF_S", "HOTSPOT_RELIEF_GRACE_S",
         "HEALTH_STUCK_NEIGHBOR_STD", "HEALTH_SATURATION_FRAMES")
# the defaults before the retune, as most existing config.py files still have them
OLD = {"CONTACT_THRESHOLD_KPA": 2.0, "HOTSPOT_ACTIVATE_FRACTION": 0.0, "HOTSPOT_DEACTIVATE_FRACTION": 0.0,
       "HOTSPOT_MIN_CELLS": 2, "HOTSPOT_END_RELIEF_S": 3.0, "HOTSPOT_RELIEF_GRACE_S": 0.0,
       "HEALTH_STUCK_NEIGHBOR_STD": 15, "HEALTH_SATURATION_FRAMES": 5}


def shipped_defaults():
    """The tuned values from config.example.py, so the test checks the shipped defaults, not a local config.py"""
    example = runpy.run_path(str(APP_DIR / "config.example.py"))
    return {name: example[name] for name in TUNED}


@unittest.skipUnless(SAMPLE.exists(), "seat take sample missing")
class SeatTakeTest(unittest.TestCase):
    """One 40 s take (idle ~4 s, then sitting down and shifting); slack because it is one take only"""

    @classmethod
    def setUpClass(cls):
        cls.new = replay(SAMPLE, shipped_defaults())
        cls.old = replay(SAMPLE, OLD)

    def test_idle_shows_no_contact_hotspot_or_noisy_cells(self):
        idle = self.new["idle"]
        self.assertGreaterEqual(idle["frames"], 30)
        self.assertEqual((idle["hotspots"], idle["noisy_cells"], idle["occupied_frames"]), (0, 0, 0))

    def test_seated_hotspots_do_not_flap(self):
        self.assertLessEqual(self.new["settled_new_hotspots_per_min"], 3.0)
        events = self.new["events"]
        self.assertLessEqual(events.get("hotspot_started", 0), 4)
        self.assertLessEqual(events.get("hotspot_relief_started", 0) + events.get("hotspot_resumed", 0), 10)
        old = self.old["events"]  # the old defaults flapped about every 0.5 s
        self.assertGreaterEqual(old["hotspot_relief_started"] + old["hotspot_resumed"], 20)

    def test_one_major_movement_at_sit_down(self):
        self.assertEqual(self.new["events"].get("Major movement", 0), 1)
        self.assertEqual(self.new["events"].get("occupancy_changes", 0), 1)

    def test_health_states_do_not_churn(self):
        self.assertLess(self.new["per_min"]["health_cell_changes"], 300)  # 400 cells; old defaults ~800/min
        self.assertGreater(self.old["per_min"]["health_cell_changes"], 2 * self.new["per_min"]["health_cell_changes"])
        self.assertGreater(self.new["health_share"]["Healthy"], 0.98)

    def test_stream_rate_of_the_take(self):
        self.assertAlmostEqual(self.new["fps"], 7.7, delta=0.3)  # recorded before the averaging-window fix


def seat(peak_row=5):
    """10 x 10 loaded at 20 kPa with one 2 x 2 concentration at 40 kPa, on the configured grid"""
    pressure = np.zeros((config.TOTAL_ROWS, config.TOTAL_COLS))
    pressure[2:12, 2:12] = 20.0
    pressure[peak_row:peak_row + 2, 5:7] = 40.0
    return pressure


class RelativeHotspotTest(unittest.TestCase):
    def tracker(self, **settings):
        tracker = HotspotTracker()
        tracker.activate_kpa, tracker.deactivate_kpa, tracker.min_cells = 10.0, 8.0, 2
        tracker.relief_grace_s = 0.0
        for key, value in settings.items():
            setattr(tracker, key, value)
        return tracker

    def test_fraction_off_keeps_the_absolute_rule(self):
        tracker = self.tracker(activate_fraction=0.0, deactivate_fraction=0.0)
        tracker.update(seat(), 0.0, TemporalAnalysis())
        self.assertEqual([len(track["cells"]) for track in tracker.active], [100])  # the whole seat

    def test_fraction_finds_the_concentration_only(self):
        tracker = self.tracker(activate_fraction=1.7, deactivate_fraction=1.2)
        self.assertAlmostEqual(tracker.thresholds(seat())[0], 1.7 * (96 * 20 + 4 * 40) / 100)
        tracker.update(seat(), 0.0, TemporalAnalysis())
        self.assertEqual([sorted(track["cells"]) for track in tracker.active], [[(5, 5), (5, 6), (6, 5), (6, 6)]])

    def test_absolute_values_stay_a_floor(self):
        tracker = self.tracker(activate_fraction=1.7, deactivate_fraction=1.2, activate_kpa=50.0, deactivate_kpa=45.0)
        self.assertEqual(tracker.thresholds(seat()), (50.0, 45.0))
        self.assertEqual(tracker.update(seat(), 0.0, TemporalAnalysis()), [])

    def test_relief_grace_ignores_a_short_dropout(self):
        empty = np.zeros_like(seat())
        for grace, expected in ((0.0, ["hotspot_relief_started", "hotspot_resumed"]), (1.0, [])):
            tracker, temporal = self.tracker(relief_grace_s=grace), TemporalAnalysis()
            kinds = []
            for timestamp, pressure in ((0.0, seat()), (0.1, empty), (0.2, seat())):
                temporal.update(pressure, timestamp)
                kinds += [kind for kind, _ in tracker.update(pressure, timestamp, temporal)]
            self.assertEqual(kinds, ["hotspot_started"] + expected, grace)

    def test_presets_without_the_new_keys_keep_the_old_behaviour(self):
        settings = default_settings()
        for key in ("activate_fraction", "deactivate_fraction", "relief_grace_s"):
            del settings["hotspots"][key]
        hotspots = validate_settings(settings)["hotspots"]
        self.assertEqual((hotspots["activate_fraction"], hotspots["deactivate_fraction"],
                          hotspots["relief_grace_s"]), (0.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()


class RelativeCeilingTests(unittest.TestCase):
    def test_hard_loaded_seat_can_still_activate(self):
        import numpy as np
        from processing.hotspots import HotspotTracker
        tracker = HotspotTracker()
        tracker.activate_fraction, tracker.deactivate_fraction = 1.7, 1.2
        pressure = np.full((20, 20), 45.0)   # mean 45 kPa -> 1.7 x mean = 76 kPa, above the 50 kPa peak
        pressure[5:7, 5:7] = 50.0
        activate, deactivate = tracker.thresholds(pressure)
        self.assertLessEqual(activate, 50.0)
        self.assertLessEqual(deactivate, activate)
