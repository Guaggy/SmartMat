"""Perf rewrites must not change results: the previous implementations are kept here as references and compared with
the current ones on the bundled seat recording (exact equality, not a tolerance)."""

from pathlib import Path
import unittest

import numpy as np

import config
from config import (
    VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT,
    HEALTH_UNLOADED_MAX, HEALTH_UNLOADED_DELTA,
    HEALTH_NOISE_STD, HEALTH_DRIFT_DELTA, HEALTH_DRIFT_MIN_S,
    HEALTH_SATURATION_MARGIN, HEALTH_SATURATION_FRAMES,
    HEALTH_STUCK_STD, HEALTH_STUCK_NEIGHBOR_STD, HEALTH_STUCK_FRAMES,
    HEALTH_INVALID_FRAMES,
)
import processing.hotspots as hotspots_module
from processing.calibration import Calibration, PressureCalibration
from processing.frames import process_frame
from processing.hotspots import HotspotTracker, connected_regions
from processing.modes import LiveMode
from processing.recording import load_session
from processing.sensor_health import SensorHealth, _rolling_stats
from processing.temporal import TemporalAnalysis

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "seat_take1.json"
STATE_FIELDS = ("current", "mean", "variance", "noise", "drift", "baseline_offset", "states",
                "invalid_streak", "missing_streak", "saturation_streak", "reference_sum", "reference_count",
                "reference_time", "calibrated")


class LegacySensorHealth(SensorHealth):
    """SensorHealth.update as it was before the perf pass: per-cell is_calibrated calls, masks rebuilt per window pass"""

    def update(self, raw, timestamp, baseline=None, pressure=None,
               contact_threshold_kpa=0, pressure_calibration=None):
        if raw.shape != (config.TOTAL_ROWS, config.TOTAL_COLS):
            raise ValueError("Sensor health grid size does not match configuration")
        self.current = raw.copy()
        finite = np.isfinite(raw)
        in_range = finite & (raw >= VALUE_MIN_DEFAULT) & (raw <= VALUE_MAX_DEFAULT)
        missing = ~finite
        invalid = finite & ~in_range
        self.missing_streak = np.where(missing, self.missing_streak + 1, 0)
        self.invalid_streak = np.where(invalid, self.invalid_streak + 1, 0)
        saturated = in_range & (raw >= VALUE_MAX_DEFAULT - HEALTH_SATURATION_MARGIN)
        self.saturation_streak = np.where(saturated, self.saturation_streak + 1, 0)

        if pressure is not None:
            unloaded = in_range & ~(np.isfinite(pressure) & (pressure > contact_threshold_kpa))
        elif baseline is not None:
            unloaded = in_range & (raw - baseline <= HEALTH_UNLOADED_DELTA)
        else:
            unloaded = in_range & (raw <= HEALTH_UNLOADED_MAX)
        values = np.where(in_range, raw, np.nan)
        self.history.append((values, unloaded))
        recent = np.stack([item[0] for item in self.history])
        unloaded_recent = np.stack([np.where(item[1], item[0], np.nan) for item in self.history])
        count, mean, variance = _rolling_stats(recent)
        unloaded_count, unloaded_mean, unloaded_variance = _rolling_stats(unloaded_recent)
        self.mean = np.where(count > 0, mean, np.nan)
        self.variance = np.where(count > 1, variance, np.nan)
        self.noise = np.where(unloaded_count >= 5, np.sqrt(unloaded_variance), np.nan)

        collecting_reference = unloaded & (self.reference_count < 10)
        self.reference_sum += np.where(collecting_reference, raw, 0)
        self.reference_count += collecting_reference.astype(int)
        new_reference = collecting_reference & (self.reference_count == 10)
        self.reference_time[new_reference] = timestamp
        reference = np.divide(self.reference_sum, self.reference_count,
                              out=np.zeros_like(raw), where=self.reference_count > 0)
        self.baseline_offset = baseline.copy() if baseline is not None else np.where(
            self.reference_count >= 10, reference, np.nan)
        self.drift = np.where(unloaded & (unloaded_count >= 5) & (self.reference_count >= 10),
                              unloaded_mean - reference, np.nan)

        if pressure_calibration is not None:
            self.calibrated = np.asarray([
                [pressure_calibration.is_calibrated(row, col) for col in range(config.TOTAL_COLS)]
                for row in range(config.TOTAL_ROWS)
            ])
        self.states = np.where(self.calibrated, 0, 7)
        self.states = np.where((unloaded_count >= 20) & (self.noise > HEALTH_NOISE_STD), 1, self.states)
        drift_ready = (timestamp - self.reference_time >= HEALTH_DRIFT_MIN_S) & unloaded
        self.states = np.where(drift_ready & (np.abs(self.drift) > HEALTH_DRIFT_DELTA), 2, self.states)

        recent_std = np.sqrt(np.nan_to_num(self.variance))
        neighbor_std = np.zeros_like(recent_std)
        neighbor_std[1:] = np.maximum(neighbor_std[1:], recent_std[:-1])
        neighbor_std[:-1] = np.maximum(neighbor_std[:-1], recent_std[1:])
        neighbor_std[:, 1:] = np.maximum(neighbor_std[:, 1:], recent_std[:, :-1])
        neighbor_std[:, :-1] = np.maximum(neighbor_std[:, :-1], recent_std[:, 1:])
        extreme = (raw <= VALUE_MIN_DEFAULT + 1) | (raw >= VALUE_MAX_DEFAULT - HEALTH_SATURATION_MARGIN)
        stuck = (count >= HEALTH_STUCK_FRAMES) & (recent_std < HEALTH_STUCK_STD)
        stuck &= extreme & (neighbor_std > HEALTH_STUCK_NEIGHBOR_STD)
        self.states = np.where(stuck, 4, self.states)
        self.states = np.where(self.saturation_streak >= HEALTH_SATURATION_FRAMES, 3, self.states)
        self.states = np.where(self.invalid_streak >= HEALTH_INVALID_FRAMES, 6, self.states)
        self.states = np.where(self.missing_streak >= HEALTH_INVALID_FRAMES, 5, self.states)


def legacy_connected_regions(mask):
    """The original: min(unseen) each time a region starts"""
    unseen = set(zip(*np.nonzero(mask)))
    regions = []
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        region = {start}
        pending = [start]
        while pending:
            row, col = pending.pop()
            for neighbor in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    region.add(neighbor)
                    pending.append(neighbor)
        regions.append(region)
    return regions


class PerfEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.frames, self.timestamps, _metadata, _ = load_session(SAMPLE, with_details=True)
        self.addCleanup(setattr, config, "TOTAL_ROWS", config.TOTAL_ROWS)
        self.addCleanup(setattr, config, "TOTAL_COLS", config.TOTAL_COLS)
        config.TOTAL_ROWS, config.TOTAL_COLS = self.frames[0].shape  # the recording's grid, as the pipeline sets it

    def test_sensor_health_identical_every_frame(self):
        new, old = SensorHealth(), LegacySensorHealth()
        mode, calibration, pressure_calibration = LiveMode(), Calibration(), PressureCalibration.default()
        for index, (grid, stamp) in enumerate(zip(self.frames, self.timestamps)):
            if index == 150:  # a partly uncalibrated cell table half way through
                pressure_calibration.individual.cells.pop((3, 4), None)
                pressure_calibration.individual._touch()
            frame = process_frame(grid, mode, calibration, pressure_calibration)
            args = dict(baseline=calibration.baseline, pressure=frame["pressure"],
                        contact_threshold_kpa=config.CONTACT_THRESHOLD_KPA, pressure_calibration=pressure_calibration)
            new.update(frame["raw"], stamp, **args)
            old.update(frame["raw"], stamp, **args)
            for name in STATE_FIELDS:
                np.testing.assert_array_equal(getattr(new, name), getattr(old, name), err_msg=f"{name} @ {index}")
        self.assertFalse(new.calibrated.all())

    def test_sensor_health_without_calibrated_mask_method_still_works(self):
        class Plain:  # only the per-cell call, like a test double
            def is_calibrated(self, row, col):
                return (row + col) % 2 == 0
        health = SensorHealth()
        health.update(self.frames[0], self.timestamps[0], pressure_calibration=Plain())
        self.assertEqual(int(health.calibrated.sum()), self.frames[0].size // 2)

    def test_calibrated_mask_matches_is_calibrated(self):
        pressure_calibration = PressureCalibration.default()
        pressure_calibration.individual.cells.pop((0, 0), None)
        pressure_calibration.individual._touch()
        rows, cols = config.TOTAL_ROWS, config.TOTAL_COLS
        expected = np.asarray([[pressure_calibration.is_calibrated(r, c) for c in range(cols)] for r in range(rows)])
        np.testing.assert_array_equal(pressure_calibration.calibrated_mask(), expected)
        pressure_calibration.use("uniform")
        np.testing.assert_array_equal(pressure_calibration.calibrated_mask(),
                                      np.full((rows, cols), pressure_calibration.uniform.exists))

    def test_connected_regions_same_regions_same_order(self):
        rng = np.random.default_rng(3)
        for density in (0.1, 0.3, 0.5, 0.7):
            for _ in range(40):
                mask = rng.random((20, 20)) < density
                self.assertEqual(connected_regions(mask), legacy_connected_regions(mask))
        self.assertEqual(connected_regions(np.zeros((4, 4), dtype=bool)), [])

    def test_hotspot_tracking_identical_with_either_region_finder(self):
        results = []
        for finder in (connected_regions, legacy_connected_regions):
            hotspots_module.connected_regions = finder
            try:
                temporal, tracker = TemporalAnalysis(), HotspotTracker()
                mode, calibration, pressure_calibration = LiveMode(), Calibration(), PressureCalibration.default()
                log = []
                for grid, stamp in zip(self.frames, self.timestamps):
                    pressure = process_frame(grid, mode, calibration, pressure_calibration)["pressure"]
                    temporal.update(pressure, stamp)
                    events = tracker.update(pressure, stamp, temporal, 0.0003)
                    log.append((events, sorted((t["id"], sorted(t["cells"]), t["active_s"]) for t in tracker.active)))
                results.append(log)
            finally:
                hotspots_module.connected_regions = connected_regions
        self.assertEqual(results[0], results[1])
        self.assertTrue(any(events for events, _ in results[0]))


if __name__ == "__main__":
    unittest.main()
