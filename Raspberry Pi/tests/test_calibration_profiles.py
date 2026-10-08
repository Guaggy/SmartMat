import json
import os
import tempfile
import unittest

import numpy as np

import config
from processing.calibration import PressureCalibration, UniformCalibration

SHAPE = (config.TOTAL_ROWS, config.TOTAL_COLS)


class ProfileTests(unittest.TestCase):
    def test_uniform_matches_individual_with_same_curve(self):
        uniform = UniformCalibration()
        uniform.set_offset(10)
        uniform.add_point(110, 20)
        uniform.add_point(210, 50)
        uniform.set_model("piecewise")
        facade = PressureCalibration()
        facade.individual.set_all_offsets(10)
        facade.individual.set_model_all("piecewise")
        facade.individual.add_grid_point(np.full(SHAPE, 110.0), 20)
        facade.individual.add_grid_point(np.full(SHAPE, 210.0), 50)
        grid = np.random.default_rng(0).uniform(0, 300, SHAPE)
        np.testing.assert_allclose(uniform.apply(grid), facade.individual.apply(grid))
        self.assertTrue(uniform.is_complete)

    def test_empty_uniform_is_incomplete_and_all_nan(self):
        uniform = UniformCalibration()
        self.assertFalse(uniform.is_complete)
        self.assertTrue(np.all(np.isnan(uniform.apply(np.ones(SHAPE)))))

    def test_switching_does_not_touch_other_profile(self):
        facade = PressureCalibration.default()
        before = facade.individual.to_dict()
        facade.uniform.add_point(100, 10)
        facade.use("uniform")
        self.assertTrue(facade.is_complete)
        facade.use("individual")
        self.assertEqual(facade.individual.to_dict(), before)
        self.assertEqual(facade.uniform.get_curve()["points"], [[100.0, 10.0]])

    def test_save_load_roundtrip_with_date_and_auto_switch(self):
        facade = PressureCalibration()
        facade.uniform.add_point(100, 10)
        facade.use("uniform")
        stamp = facade.to_dict()["calibrated_at"]
        self.assertIsNotNone(stamp)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "u.json")
            facade.save(path)
            fresh = PressureCalibration()
            fresh.load(path)
            self.assertEqual(fresh.active_name, "uniform")
            self.assertEqual(fresh.uniform.to_dict(), facade.uniform.to_dict())
            self.assertLess(os.path.getsize(path), 600)

    def test_old_individual_file_without_date_loads(self):
        data = PressureCalibration.default().individual.to_dict()
        data.pop("calibrated_at")
        fresh = PressureCalibration()
        fresh.load_dict(json.loads(json.dumps(data)))
        self.assertIsNone(fresh.individual.modified_at)
        self.assertTrue(fresh.is_complete)

    def test_default_has_no_date_but_edits_do(self):
        facade = PressureCalibration.default()
        self.assertIsNone(facade.to_dict()["calibrated_at"])
        facade.set_offset(0, 0, 1)
        self.assertIsNotNone(facade.to_dict()["calibrated_at"])

    def test_tare_sets_offsets_in_both_profiles(self):
        facade = PressureCalibration.default()
        facade.uniform.add_point(500, 20)
        tare = np.full(SHAPE, 30.0)
        tare[0, 0] = 40.0
        facade.capture_tare(tare)
        self.assertEqual(facade.individual.get_cell(0, 0)["offset"], 40.0)
        self.assertEqual(facade.individual.get_cell(1, 1)["offset"], 30.0)
        self.assertAlmostEqual(facade.uniform.get_curve()["offset"], tare.mean())
        self.assertTrue(facade.individual.is_complete)

    def test_tare_that_would_uncalibrate_is_refused_and_changes_nothing(self):
        facade = PressureCalibration.default()  # single point at raw 1000
        facade.uniform.add_point(500, 20)
        before = (facade.individual.to_dict(), facade.uniform.to_dict())
        with self.assertRaises(ValueError):
            facade.capture_tare(np.full(SHAPE, 600.0))  # above the uniform point
        self.assertEqual((facade.individual.to_dict(), facade.uniform.to_dict()), before)

    def test_tare_rejects_missing_values(self):
        grid = np.full(SHAPE, 10.0)
        grid[0, 0] = np.nan
        with self.assertRaises(ValueError):
            PressureCalibration.default().capture_tare(grid)

    def test_uniform_grid_point_needs_mostly_valid_cells(self):
        uniform = UniformCalibration()
        grid = np.full(SHAPE, np.nan)
        with self.assertRaises(ValueError):
            uniform.add_grid_point(grid, 10)
        grid[:] = 50.0
        grid[0, 0] = np.nan
        uniform.add_grid_point(grid, 10)
        self.assertEqual(uniform.get_curve()["points"], [[50.0, 10.0]])


if __name__ == "__main__":
    unittest.main()
