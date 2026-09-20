"""Focused tests for packet quality and temporal pressure analysis."""

import math
import json
import time
import unittest

import numpy as np

from config import TOTAL_ROWS, TOTAL_COLS
from general import parse_frame_text_with_reason
from processing.source_quality import SourceQuality
from processing.recording import RECORDINGS_DIR, Recorder, load_session, load_session_details
from processing.temporal import FULL, LOADED, PARTIAL, UNKNOWN, TemporalAnalysis
from sources.simulated_source import SimulatedSource


def pressure(value):
    return np.full((TOTAL_ROWS, TOTAL_COLS), value, dtype=float)


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.analysis = TemporalAnalysis()
        self.analysis.relief_min_duration_s = 0

    def test_constant_pressure_and_irregular_timestamps(self):
        for timestamp in (0, 10, 25, 40):
            self.analysis.max_gap_s = 30
            self.analysis.update(pressure(12), timestamp)
        self.assertAlmostEqual(self.analysis.exposure[0, 0], 8)

    def test_threshold_and_zero(self):
        self.analysis.exposure_mode = "Above threshold"
        self.analysis.exposure_threshold_kpa = 5
        self.analysis.max_gap_s = 90
        self.analysis.update(pressure(0), 0)
        self.analysis.update(pressure(0), 60)
        self.assertEqual(self.analysis.exposure[0, 0], 0)
        self.analysis.update(pressure(10), 120)
        self.assertEqual(self.analysis.exposure[0, 0], 0)
        self.analysis.update(pressure(10), 180)
        self.assertAlmostEqual(self.analysis.exposure[0, 0], 5)

    def test_gap_and_invalid_sample_do_not_accumulate_or_relieve(self):
        self.analysis.update(pressure(10), 0)
        self.analysis.update(pressure(10), 1)
        before = self.analysis.exposure.copy()
        self.analysis.update(pressure(0), 10)
        self.assertTrue(np.array_equal(before, self.analysis.exposure))
        self.assertEqual(self.analysis.state[0, 0], UNKNOWN)
        self.analysis.invalidate()
        self.analysis.update(pressure(0), 11)
        self.assertTrue(np.array_equal(before, self.analysis.exposure))

    def test_burden_rises_recovers_and_never_negative(self):
        self.analysis.max_gap_s = 60
        self.analysis.update(pressure(12), 0)
        self.analysis.update(pressure(12), 30)
        peak = self.analysis.burden[0, 0]
        self.assertGreater(peak, 0)
        self.analysis.update(pressure(0), 60)
        at_release = self.analysis.burden[0, 0]
        self.analysis.update(pressure(0), 90)
        self.assertLess(self.analysis.burden[0, 0], at_release)
        self.assertGreaterEqual(self.analysis.burden[0, 0], 0)
        faster = TemporalAnalysis()
        faster.max_gap_s = 60
        faster.burden_accumulation_rate = 2
        faster.update(pressure(12), 0)
        faster.update(pressure(12), 30)
        self.assertGreater(faster.burden[0, 0], peak)

    def test_relief_states_and_duration(self):
        self.analysis.max_gap_s = 10
        self.analysis.relief_min_duration_s = 1
        self.analysis.update(pressure(10), 0)
        self.analysis.update(pressure(10), 1)
        self.assertEqual(self.analysis.state[0, 0], LOADED)
        self.analysis.update(pressure(4), 2)
        self.assertEqual(self.analysis.state[0, 0], LOADED)
        self.analysis.update(pressure(4), 3)
        self.assertEqual(self.analysis.state[0, 0], PARTIAL)
        self.analysis.update(pressure(1), 4)
        self.analysis.update(pressure(1), 5)
        self.assertEqual(self.analysis.state[0, 0], FULL)
        self.analysis.update(pressure(1), 6)
        self.assertGreater(self.analysis.cell(0, 0)["relief_percent"], 0)
        self.analysis.invalidate()
        state = self.analysis.state.copy()
        self.assertEqual(state[0, 0], UNKNOWN)
        self.analysis.update(pressure(0), 7)
        self.assertTrue(np.array_equal(state, self.analysis.state))

    def test_rolling_and_roi(self):
        self.analysis.max_gap_s = 60
        self.analysis.update(pressure(10), 0)
        for timestamp in (30, 60, 90):
            self.analysis.update(pressure(10), timestamp)
        session = self.analysis.exposure[0, 0]
        recent = self.analysis.rolling(1)[0][0, 0]
        self.assertGreater(session, recent)
        self.assertAlmostEqual(self.analysis.roi((0, 1, 0, 1))["mean_exposure"], session)
        self.analysis.reset_exposure()
        self.assertEqual(self.analysis.exposure[0, 0], 0)
        self.assertGreater(self.analysis.rolling(1)[2][0, 0], 0)

    def test_rolling_storage_is_bounded(self):
        self.analysis.max_gap_s = 20
        for timestamp in range(0, 4000, 10):
            self.analysis.update(pressure(10), timestamp)
        self.assertLessEqual(len(self.analysis._buckets), 360)

    def test_playback_speed_does_not_change_physical_exposure(self):
        frames = [pressure(12) for _ in range(3)]
        timestamps = [0, 0.1, 0.2]
        results = []
        for speed in (0.25, 1, 5):
            source = SimulatedSource(playback_frames=frames, playback_timestamps=timestamps)
            source.set_playback_speed(speed)
            source.start()
            try:
                samples = []
                deadline = time.monotonic() + 3
                while len(samples) < 3 and time.monotonic() < deadline:
                    samples.extend(source.latest.take_all())
                    time.sleep(0.01)
                self.assertGreaterEqual(len(samples), 3)
                analysis = TemporalAnalysis()
                for frame, timestamp in samples[:3]:
                    analysis.update(frame, timestamp)
                results.append(analysis.exposure[0, 0])
                source.pause()
                source.latest.take_all()
                before = analysis.exposure[0, 0]
                time.sleep(0.04)
                self.assertEqual(source.latest.take_all(), [])
                self.assertEqual(before, analysis.exposure[0, 0])
            finally:
                source.stop()
        self.assertAlmostEqual(results[0], results[1])
        self.assertAlmostEqual(results[1], results[2])


class QualityTests(unittest.TestCase):
    def test_rejection_reasons_and_counters(self):
        self.assertEqual(parse_frame_text_with_reason("1,2")[1], "grid_size")
        self.assertEqual(parse_frame_text_with_reason(",".join(["2000"] * (TOTAL_ROWS * TOTAL_COLS)))[1], "out_of_range")
        quality = SourceQuality()
        quality.packet("grid_size", timestamp=False)
        quality.packet("out_of_range", timestamp=False)
        quality.packet()
        quality.drop()
        data = quality.snapshot()
        self.assertEqual((data["received"], data["valid"], data["malformed"], data["dropped"]), (3, 1, 2, 1))
        self.assertEqual(data["unexpected_grid_size"], 1)
        self.assertTrue(math.isfinite(data["age_s"]))

    def test_new_and_old_recordings(self):
        recorder = Recorder("phase4_test", metadata={"temporal": {"exposure_mode": "Full pressure"}})
        recorder.add_frame(pressure(1), timestamp=1)
        recorder.add_frame(pressure(2), timestamp=2)
        recorder.events.append({"timestamp": 1.5, "kind": "user_marker", "note": "load"})
        path = recorder.save()
        try:
            frames, timestamps = load_session(path, with_timestamps=True)
            metadata, events = load_session_details(path)
            self.assertEqual(timestamps, [1, 2])
            self.assertEqual(len(frames), 2)
            self.assertEqual(events[0]["note"], "load")
            self.assertIn("temporal", metadata)
        finally:
            path.unlink()
        old = RECORDINGS_DIR / "phase4_old_test.json"
        try:
            old.write_text(json.dumps({"frames": [pressure(3).tolist()]}))
            self.assertEqual(load_session(old)[0][0, 0], 3)
        finally:
            old.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
