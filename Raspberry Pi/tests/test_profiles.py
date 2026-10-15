"""Per-mat profiles: tare, pressure calibration and orientation saved per mat_id."""

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import config
from processing import calibration
from processing.calibration import (Calibration, PressureCalibration, apply_profile, load_profile,
                                    profile_path, save_profile)
from sources.serial_source import Port, SerialSource

DEFAULT_SHAPE = (config.TOTAL_ROWS, config.TOTAL_COLS)
ORIENTATION = {"rotation": 0, "mirror_h": True, "mirror_v": False}


class ProfileFileTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(calibration, "PROFILES_DIR", Path(folder) / "profiles"))

    def test_round_trip(self):
        tare, pressure = Calibration(), PressureCalibration()
        tare.capture_baseline(np.full(DEFAULT_SHAPE, 7.0))
        pressure.uniform.set_offset(10)
        pressure.uniform.add_point(500, 20)
        pressure.use("uniform")
        save_profile("/dev/ttyUSB0", tare.baseline, pressure, ORIENTATION)
        self.assertEqual(profile_path("/dev/ttyUSB0").name, "_dev_ttyUSB0.json")

        data = load_profile("/dev/ttyUSB0")
        self.assertEqual(data["orientation"], ORIENTATION)
        tare2, pressure2 = Calibration(), PressureCalibration()
        apply_profile(data, tare2, pressure2)
        np.testing.assert_array_equal(tare2.baseline, tare.baseline)
        self.assertEqual(pressure2.active_name, "uniform")
        self.assertEqual(pressure2.uniform.get_curve(), pressure.uniform.get_curve())

    def test_missing_corrupt_or_mismatched_profile(self):
        self.assertIsNone(load_profile("nope"))
        calibration.PROFILES_DIR.mkdir()
        profile_path("bad").write_text("{not json")
        self.assertIsNone(load_profile("bad"))
        save_profile("small", None, PressureCalibration(), ORIENTATION)
        data = load_profile("small")
        tare, pressure = Calibration(), PressureCalibration()
        tare.baseline = "untouched"
        with mock.patch.object(config, "TOTAL_ROWS", 3), mock.patch.object(config, "TOTAL_COLS", 3):
            with self.assertRaises(ValueError):
                apply_profile(data, tare, pressure)
        self.assertEqual(tare.baseline, "untouched")  # all-or-nothing


class DesktopProfileTests(unittest.TestCase):
    def setUp(self):
        from gui import desktop
        self.addCleanup(setattr, config, "TOTAL_ROWS", DEFAULT_SHAPE[0])
        self.addCleanup(setattr, config, "TOTAL_COLS", DEFAULT_SHAPE[1])
        folder = self.enterContext(tempfile.TemporaryDirectory())
        for patch in (mock.patch.object(calibration, "PROFILES_DIR", Path(folder)),
                      mock.patch.object(desktop, "list_ports",
                                        return_value=[Port("COM3", "COM3 - mat A"), Port("COM4", "COM4 - mat B")]),
                      mock.patch.object(SerialSource, "start"),
                      mock.patch.object(desktop, "save_mat_names")):
            self.enterContext(patch)
        try:
            self.app = desktop.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(self.app._on_close)
        self.app.source_var.set("Serial")
        self.app._refresh_devices()

    def connect(self, label):
        self.app.device_var.set(label)
        self.app._connect()
        self.assertIsNotNone(self.app.source, self.app.status_var.get())

    def turn(self, rotation):
        self.app.rotation_var.set(str(rotation))
        self.app._orientation_changed()

    def test_switch_a_b_a_restores_a(self):
        app = self.app
        turned = DEFAULT_SHAPE[::-1]
        self.connect("COM3 - mat A")
        self.turn(90)
        app.calibration.capture_baseline(np.full(turned, 5.0))
        app.pressure_calibration.uniform.add_point(400, 30)
        app.pressure_calibration.use("uniform")

        self.connect("COM4 - mat B")  # same raw size: must not inherit A's tare/calibration
        self.assertIsNone(app.calibration.baseline)
        self.assertEqual(app.pressure_calibration.active_name, "individual")
        self.turn(0)
        self.assertEqual((config.TOTAL_ROWS, config.TOTAL_COLS), DEFAULT_SHAPE)

        self.connect("COM3 - mat A")
        self.assertIn("mat profile COM3 restored", app.status_var.get())
        self.assertEqual((app._rotation, app.rotation_var.get()), (90, "90"))
        self.assertEqual((config.TOTAL_ROWS, config.TOTAL_COLS), turned)
        self.assertEqual(app.pressure_calibration.active_name, "uniform")
        self.assertEqual(app.pressure_calibration.uniform.get_curve()["points"], [[400.0, 30.0]])
        app._orient(np.zeros(DEFAULT_SHAPE))  # first live frame: already the right size, no A4 reset
        np.testing.assert_array_equal(app.calibration.baseline, np.full(turned, 5.0))

        app._disconnect()
        self.assertEqual(json.loads(profile_path("COM4").read_text())["orientation"]["rotation"], 0)

    def test_mismatched_profile_is_ignored(self):
        calibration.PROFILES_DIR.mkdir(exist_ok=True)
        with mock.patch.object(config, "TOTAL_ROWS", 3), mock.patch.object(config, "TOTAL_COLS", 3):
            save_profile("COM3", np.ones((3, 3)), PressureCalibration(), ORIENTATION)
        self.connect("COM3 - mat A")
        self.assertIn("new mat profile", self.app.status_var.get())
        self.assertEqual((config.TOTAL_ROWS, config.TOTAL_COLS), DEFAULT_SHAPE)
        self.assertIsNone(self.app.calibration.baseline)
        self.assertFalse(self.app.mirror_h_var.get())

    def test_calibration_window_names_the_profile(self):
        self.connect("COM3 - mat A")
        self.app._open_calibration()
        self.assertIn("Mat profile: COM3", self.app.calibration_windows[-1].profile_text)


if __name__ == "__main__":
    unittest.main()
