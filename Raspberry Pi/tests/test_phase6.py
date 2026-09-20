"""Focused checks for engineering validation and reproducible re-analysis."""

import json
import unittest
from pathlib import Path
import tkinter as tk

import numpy as np

from processing.calibration import PressureCalibration
from processing.hotspots import HotspotTracker
from processing.reanalysis import analyze_recording, compare_recording
from processing.settings import builtin_preset, load_preset, save_preset, validate_settings
from processing.session_events import apply_state_event
from processing.calibration import Calibration
from processing.motion import MotionAnalyzer
from processing.session_state import initial_session_state
from processing.temporal import TemporalAnalysis
from processing.timeline import EventTimeline
from processing.validation import reposition_validation


def calibrated():
    calibration = PressureCalibration()
    calibration.add_point(0, 0, 100, 100)
    calibration.copy_cell_to_all(0, 0)
    return calibration


class Phase6Tests(unittest.TestCase):
    def test_loaded_start_keeps_prior_duration_and_relief_unknown(self):
        temporal = TemporalAnalysis()
        tracker = HotspotTracker()
        values = np.zeros((16, 15))
        values[2:6, 4:8] = 40
        temporal.update(values, 10)
        tracker.update(values, 10, temporal)
        self.assertTrue(tracker.active)
        track = tracker.active[0]
        self.assertTrue(track["started_before_session"])
        self.assertIsNone(track["prior_duration_s"])
        self.assertEqual(track["total_active_s"], 0)
        state = initial_session_state(10, "test", values, values, calibrated(),
                                      None, 5, tracker)
        self.assertEqual(state["occupancy"], "loaded")
        self.assertFalse(state["prior_relief_history_known"])
        temporal.update(values, 12)
        tracker.update(values, 12, temporal)
        self.assertAlmostEqual(tracker.active[0]["total_active_s"], 2)
        self.assertIsNone(tracker.active[0]["prior_duration_s"])

    def test_annotations_keep_notes_and_validation_is_one_to_one(self):
        timeline = EventTimeline()
        timeline.add(10, "annotation", "turned left",
                     {"type": "Known reposition", "before_note": "back", "after_note": "left"})
        timeline.add(50, "annotation", "turned right", {"type": "Known reposition"})
        restored = EventTimeline(json.loads(json.dumps(timeline.events)))
        self.assertEqual(restored.events[0]["payload"]["after_note"], "left")
        result = reposition_validation(restored.events,
                                       [{"timestamp": 12}, {"timestamp": 13}, {"timestamp": 100}], 5)
        self.assertEqual((result["matched"], result["missed"], result["unpaired"]), (1, 1, 2))
        self.assertEqual(result["matches"][0]["timing_error_s"], 2)

    def test_presets_roundtrip_and_reject_invalid_integer(self):
        settings = builtin_preset("Sensitive")
        path = Path(__file__).parent / "phase6_preset_roundtrip.json"
        try:
            save_preset(path, settings, "Test")
            self.assertEqual(load_preset(path), ("Test", settings))
            settings["hotspots"]["min_cells"] = "2.5"
            with self.assertRaises(ValueError):
                validate_settings(settings)
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_preset(path)
        finally:
            path.unlink(missing_ok=True)

    def test_reanalysis_deterministic_and_does_not_mutate_recording(self):
        pressure = calibrated()
        metadata = {"pressure_calibration": pressure.to_dict(), "processing_mode": "Live"}
        frames = []
        for _ in range(4):
            frame = np.zeros((16, 15))
            frame[2:6, 4:8] = 40
            frames.append(frame)
        times = [1, 1.5, 2, 2.5]
        snapshot = json.dumps(metadata)
        original = analyze_recording(frames, times, metadata, [])
        self.assertEqual(original, analyze_recording(frames, times, metadata, []))
        tuned = builtin_preset("Default")
        tuned["hotspots"]["activate_kpa"] = 90
        tuned["hotspots"]["deactivate_kpa"] = 80
        comparison = compare_recording(frames, times, metadata, [], tuned)
        self.assertGreater(comparison["recorded_settings"]["hotspots"],
                           comparison["current_settings"]["hotspots"])
        self.assertEqual(json.dumps(metadata), snapshot)

    def test_timed_settings_apply_and_live_state_restores(self):
        settings = builtin_preset("Default")
        settings["hotspots"]["activate_kpa"] = 70
        settings["hotspots"]["deactivate_kpa"] = 60
        temporal, hotspots, motion = TemporalAnalysis(), HotspotTracker(), MotionAnalyzer()
        event = {"kind": "algorithm_settings_changed", "payload": {"settings": settings}}
        threshold = apply_state_event(event, Calibration(), calibrated(),
                                      temporal, hotspots, motion)
        self.assertEqual(hotspots.activate_kpa, 70)
        self.assertEqual(threshold, settings["contact_threshold_kpa"])
        from gui.desktop import DesktopApp
        try:
            app = DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        try:
            original = app.hotspots
            original_preset = app.preset_name
            app._live_state = (app.calibration, app.pressure_calibration, app.temporal,
                               app.hotspots, app.motion, app.active_mode.label,
                               app.mode_param_var.get(), app.contact_threshold_kpa,
                               original_preset, app.experiment_info.copy())
            app.hotspots = hotspots
            app.preset_name = "Recorded"
            app._restore_live_state()
            self.assertIs(app.hotspots, original)
            self.assertEqual(app.preset_name, original_preset)
        finally:
            app.root.destroy()


if __name__ == "__main__":
    unittest.main()
