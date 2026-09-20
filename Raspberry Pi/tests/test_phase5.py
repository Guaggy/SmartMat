"""Deterministic state replay, hotspot, movement, and reposition checks."""

import unittest
import tkinter as tk
import time

import numpy as np

from processing.calibration import Calibration, PressureCalibration
from processing.hotspots import HotspotTracker, connected_regions
from processing.motion import MotionAnalyzer
from processing.session_events import apply_state_event, event_is_due
from processing.temporal import TemporalAnalysis
from processing.recording import Recorder
from sources.simulated_source import SimulatedSource


def grid(cells, value=30):
    values = np.zeros((16, 15))
    for cell in cells:
        values[cell] = value
    return values


class StateEventTests(unittest.TestCase):
    def test_tare_and_calibration_apply_at_frame_boundary(self):
        calibration = Calibration()
        pressure = PressureCalibration()
        temporal = TemporalAnalysis()
        baseline = grid({(1, 1)}, 10)
        tare = {"timestamp": 2.2, "frame_index": 3, "kind": "tare_captured",
                "payload": {"baseline": baseline.tolist()}}
        self.assertFalse(event_is_due(tare, 2, 2.5))
        self.assertTrue(event_is_due(tare, 3, 3.0))
        apply_state_event(tare, calibration, pressure, temporal)
        np.testing.assert_array_equal(calibration.baseline, baseline)
        changed = PressureCalibration()
        changed.add_point(1, 1, 100, 10)
        event = {"kind": "calibration_changed", "payload": {"calibration": changed.to_dict()}}
        apply_state_event(event, calibration, pressure, temporal)
        self.assertTrue(pressure.is_calibrated(1, 1))
        apply_state_event({"kind": "baseline_cleared"}, calibration, pressure, temporal)
        self.assertIsNone(calibration.baseline)

    def test_playback_state_is_separate_from_live_objects(self):
        live_calibration = Calibration()
        live_pressure = PressureCalibration()
        live_pressure.add_point(0, 0, 100, 10)
        replay_calibration = Calibration()
        replay_pressure = PressureCalibration()
        apply_state_event({"kind": "tare_captured", "payload": {"baseline": grid({(0, 0)}, 5).tolist()}},
                          replay_calibration, replay_pressure, TemporalAnalysis())
        self.assertIsNone(live_calibration.baseline)
        self.assertTrue(live_pressure.is_calibrated(0, 0))
        self.assertFalse(replay_pressure.is_calibrated(0, 0))

    def test_gui_records_timed_tare_and_calibration_events(self):
        from gui.desktop import DesktopApp
        try:
            app = DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        recorder = Recorder("phase5_state_test")
        try:
            app._handle_new_frame(np.full((16, 15), 10.0), sample_time=1)
            app.recorder = recorder
            app._capture_baseline()
            self.assertEqual(recorder.events[-1]["kind"], "tare_captured")
            self.assertEqual(recorder.events[-1]["frame_index"], 0)
            self.assertEqual(recorder.events[-1]["payload"]["baseline"][0][0], 10)
            app.pressure_calibration.add_point(0, 0, 100, 10)
            app._refresh_calibration("calibration_changed")
            self.assertEqual(recorder.events[-1]["kind"], "calibration_changed")
            self.assertEqual(recorder.events[-1]["payload"]["calibration"]["cells"][0]["row"], 0)
        finally:
            app.recorder = None
            recorder.discard()
            app.root.destroy()

    def test_gui_playback_applies_state_then_restores_live(self):
        from gui.desktop import DesktopApp
        try:
            app = DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        recorder = Recorder("phase5_replay_test", metadata={
            "pressure_calibration": PressureCalibration().to_dict(),
            "baseline_processed": None, "processing_mode": "Live",
            "contact_threshold_kpa": 2.0})
        path = None
        try:
            live_pressure = app.pressure_calibration
            live_pressure.add_point(0, 0, 100, 10)
            for timestamp in (0, 1, 2):
                recorder.add_frame(np.full((16, 15), 10.0), timestamp=timestamp)
            recorder.events.append({"timestamp": 0.5, "frame_index": 1, "kind": "tare_captured",
                                    "payload": {"baseline": grid({(0, 0)}, 5).tolist()}})
            changed = PressureCalibration()
            changed.add_point(0, 0, 100, 20)
            recorder.events.append({"timestamp": 1.5, "frame_index": 2, "kind": "calibration_changed",
                                    "payload": {"calibration": changed.to_dict()}})
            settings = TemporalAnalysis().settings()
            settings["exposure_mode"] = "Above threshold"
            recorder.events.append({"timestamp": 1.5, "frame_index": 2,
                                    "kind": "temporal_parameters_changed",
                                    "payload": {"temporal": settings}})
            recorder.events.append({"timestamp": 1.5, "frame_index": 2,
                                    "kind": "processing_mode_changed",
                                    "payload": {"mode": "Average", "parameter": 2}})
            path = recorder.save()
            app.source_var.set("Simulated")
            app.device_var.set(path.name)
            app._connect()
            self.assertIsNotNone(app.source)
            app.source.stop()
            app._handle_new_frame(np.full((16, 15), 10.0), sample_time=0)
            self.assertIsNone(app.calibration.baseline)
            app._handle_new_frame(np.full((16, 15), 10.0), sample_time=1)
            self.assertEqual(app.calibration.baseline[0, 0], 5)
            self.assertFalse(app.pressure_calibration.is_calibrated(0, 0))
            app._handle_new_frame(np.full((16, 15), 10.0), sample_time=2)
            self.assertEqual(app.pressure_calibration.convert_cell(0, 0, 100), 20)
            self.assertEqual(app.temporal.exposure_mode, "Above threshold")
            self.assertEqual(app.active_mode.label, "Average")
            app._disconnect()
            self.assertIsNone(app.source)
            self.assertIs(app.pressure_calibration, live_pressure)
            self.assertEqual(app.pressure_calibration.convert_cell(0, 0, 100), 10)
            self.assertIsNone(app.calibration.baseline)
            self.assertEqual(app.temporal.exposure_mode, "Full pressure")
            self.assertEqual(app.active_mode.label, "Live")
        finally:
            if app.source is not None:
                app.source.stop()
            app.root.destroy()
            if path is not None:
                path.unlink(missing_ok=True)

    def test_timed_event_is_speed_invariant(self):
        frames = [grid({(1, 1)}) for _ in range(3)]
        timestamps = [0, 0.1, 0.2]
        event = {"kind": "tare_captured", "timestamp": 0.15, "frame_index": 2,
                 "payload": {"baseline": grid({(1, 1)}, 5).tolist()}}
        outcomes = []
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
            finally:
                source.stop()
            calibration = Calibration()
            applied_at = None
            for index, (_values, timestamp) in enumerate(samples[:3]):
                if applied_at is None and event_is_due(event, index, timestamp):
                    apply_state_event(event, calibration, PressureCalibration(), TemporalAnalysis())
                    applied_at = timestamp
            outcomes.append((applied_at, calibration.baseline[1, 1]))
        self.assertEqual(outcomes, [(0.2, 5.0)] * 3)


class HotspotTests(unittest.TestCase):
    def setUp(self):
        self.tracker = HotspotTracker()
        self.tracker.min_cells = 2
        self.tracker.persistence_s = 2
        self.tracker.end_relief_s = 2
        self.temporal = TemporalAnalysis()

    def update(self, values, timestamp):
        self.temporal.update(values, timestamp)
        return self.tracker.update(values, timestamp, self.temporal)

    def test_connected_regions_and_minimum_size(self):
        values = grid({(1, 1), (1, 2), (6, 6), (6, 7), (10, 10)})
        self.assertEqual(sorted(map(len, connected_regions(values > 0))), [1, 2, 2])
        self.update(values, 0)
        self.assertEqual(len(self.tracker.active), 2)

    def test_hysteresis_tracking_persistence_and_end(self):
        first = grid({(1, 1), (1, 2)})
        self.update(first, 0)
        track_id = self.tracker.active[0]["id"]
        self.update(grid({(1, 2), (1, 3)}), 1)
        self.assertEqual(self.tracker.active[0]["id"], track_id)
        events = self.update(grid({(1, 2), (1, 3)}, 17), 2)
        self.assertEqual(self.tracker.active[0]["id"], track_id)
        self.assertTrue(any(kind == "hotspot_persistent" for kind, _id in events))
        self.update(grid({(1, 2), (1, 3)}, 17), 3)
        self.update(grid(set()), 4)
        self.assertEqual(self.tracker.tracks[track_id]["state"], "relieved")
        self.update(grid(set()), 5)
        events = self.update(grid(set()), 6)
        self.assertIn(("hotspot_ended", track_id), events)
        self.assertNotIn(track_id, self.tracker.tracks)

    def test_gap_does_not_end_hotspot(self):
        self.update(grid({(1, 1), (1, 2)}), 0)
        self.tracker.invalidate()
        self.update(grid(set()), 10)
        self.assertEqual(len(self.tracker.active), 1)

    def test_gap_does_not_count_as_relief_duration(self):
        self.update(grid({(1, 1), (1, 2)}), 0)
        self.update(grid(set()), 1)
        track_id = next(iter(self.tracker.tracks))
        self.tracker.invalidate()
        self.update(grid(set()), 100)
        self.update(grid(set()), 101)
        self.assertIn(track_id, self.tracker.tracks)
        self.update(grid(set()), 102)
        self.assertNotIn(track_id, self.tracker.tracks)

    def test_merge_and_split_use_deterministic_ids(self):
        separated = grid({(2, 2), (2, 3), (2, 6), (2, 7)})
        self.update(separated, 0)
        ids = sorted(track["id"] for track in self.tracker.active)
        merged = grid({(2, col) for col in range(2, 8)})
        events = self.update(merged, 1)
        self.assertEqual(len(self.tracker.active), 1)
        self.assertIn(self.tracker.active[0]["id"], ids)
        self.assertTrue(any(kind == "hotspot_merged" for kind, _id in events))
        events = self.update(merged, 2)
        self.assertFalse(any(kind == "hotspot_merged" for kind, _id in events))
        events = self.update(separated, 3)
        self.assertEqual(len(self.tracker.active), 2)
        self.assertTrue(any(track["id"] in ids for track in self.tracker.active))
        self.assertTrue(any(kind == "hotspot_split" for kind, _id in events))

    def test_playback_speed_keeps_hotspot_events(self):
        frames = [grid({(1, 1), (1, 2)})] * 3 + [grid(set())] * 3
        timestamps = [index * 0.1 for index in range(len(frames))]
        sequences = []
        for speed in (0.25, 1, 5):
            source = SimulatedSource(playback_frames=frames, playback_timestamps=timestamps)
            source.set_playback_speed(speed)
            source.start()
            try:
                samples = []
                deadline = time.monotonic() + 4
                while len(samples) < len(frames) and time.monotonic() < deadline:
                    samples.extend(source.latest.take_all())
                    time.sleep(0.01)
                self.assertGreaterEqual(len(samples), len(frames))
            finally:
                source.stop()
            tracker = HotspotTracker()
            tracker.persistence_s = 0.1
            tracker.end_relief_s = 0.1
            temporal = TemporalAnalysis()
            sequence = []
            for values, timestamp in samples[:len(frames)]:
                temporal.update(values, timestamp)
                sequence.extend((kind, round(timestamp, 3)) for kind, _id in
                                tracker.update(values, timestamp, temporal))
            sequences.append(sequence)
        self.assertEqual(sequences[0], sequences[1])
        self.assertEqual(sequences[1], sequences[2])


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.motion = MotionAnalyzer()
        self.motion.before_s = 2
        self.motion.settle_s = 1
        self.motion.after_s = 2
        self.motion.reposition_cooldown_s = 10
        self.motion.reset()
        self.temporal = TemporalAnalysis()
        self.base = grid({(2, 2), (2, 3), (3, 2), (3, 3)})
        self.shifted = grid({(8, 8), (8, 9), (9, 8), (9, 9)})

    def update(self, values, timestamp):
        self.temporal.update(values, timestamp)
        return self.motion.update(values, timestamp, 2, None, [], self.temporal)

    def test_stable_movement_and_invalid_gap(self):
        for timestamp in range(4):
            self.assertEqual(self.update(self.base, timestamp), [])
        self.assertEqual(self.motion.last_score["category"], "Stable")
        self.motion.invalidate()
        self.update(self.shifted, 10)
        self.assertEqual(self.motion.last_score["category"], "Stable")

    def test_reposition_requires_sustained_change_and_cooldown(self):
        for timestamp in range(5):
            self.update(self.base, timestamp)
        events = self.update(self.shifted, 5)
        self.assertEqual(self.motion.last_score["category"], "Major movement")
        self.assertGreater(self.motion.last_score["cop_cells"], 4)
        self.assertTrue(any(kind == "movement" for kind, _payload in events))
        for timestamp in (6, 7, 8):
            events = self.update(self.shifted, timestamp)
        self.assertTrue(any(kind == "reposition_detected" for kind, _payload in events))
        record = self.motion.repositions[-1]
        self.assertAlmostEqual(record["before"]["peak_kpa"], 30)
        self.assertAlmostEqual(record["after"]["peak_kpa"], 30)
        self.assertGreater(record["cop_displacement_cells"], 4)
        self.update(self.base, 9)
        for timestamp in (10, 11, 12):
            self.update(self.base, timestamp)
        self.assertEqual(len(self.motion.repositions), 1)

    def test_brief_disturbance_is_not_reposition(self):
        for timestamp in range(5):
            self.update(self.base, timestamp)
        self.update(self.shifted, 5)
        for timestamp in (6, 7, 8):
            self.update(self.base, timestamp)
        self.assertEqual(len(self.motion.repositions), 0)

    def test_first_load_is_not_a_reposition(self):
        empty = grid(set())
        for timestamp in range(5):
            self.update(empty, timestamp)
        for timestamp in range(5, 9):
            self.update(self.shifted, timestamp)
        self.assertEqual(len(self.motion.repositions), 0)


if __name__ == "__main__":
    unittest.main()
