"""Checks for real-cell analysis and conservative diagnostics."""

import unittest

import numpy as np

from processing.analysis import load_distribution, pressure_distribution, roi_statistics
from processing.display import interpolate_grid
from processing.sensor_health import SensorHealth
from processing.statistics import weighted_center


class Phase3ProcessingTests(unittest.TestCase):
    def test_interpolation_keeps_real_cells_unchanged(self):
        real = np.arange(240.0).reshape(16, 15)
        original = real.copy()
        dense = interpolate_grid(real, "Linear", 4)
        self.assertEqual(dense.shape, (61, 57))
        np.testing.assert_allclose(dense[::4, ::4], real)
        np.testing.assert_array_equal(real, original)

    def test_roi_distribution_and_symmetry_use_real_cells(self):
        pressure = np.zeros((16, 15))
        pressure[1, 1:4] = [10, 20, 30]
        roi = roi_statistics(pressure, (1, 2, 1, 3), "kPa", 5, 0.0001)
        self.assertEqual(roi["sensors"], 6)
        self.assertEqual(roi["contact_cells"], 3)
        self.assertAlmostEqual(roi["force_n"], 6)
        self.assertAlmostEqual(roi["center_x"], 7 / 3)

        distribution = pressure_distribution(pressure, 5, cell_area_m2=0.0001)
        self.assertEqual(distribution["histogram"].sum(), 3)
        self.assertAlmostEqual(distribution["percentiles"][90], 30)
        self.assertEqual(distribution["area_above"][0], 3)

        balanced = load_distribution(np.ones((16, 15)))
        self.assertAlmostEqual(balanced["left"], 50)
        self.assertAlmostEqual(balanced["upper"], 50)
        self.assertAlmostEqual(sum(balanced["quadrants"].values()), 100)
        self.assertAlmostEqual(balanced["left_right_imbalance"], 0)

    def test_occupied_cell_is_not_called_drifting(self):
        health = SensorHealth()
        for index in range(100):
            grid = np.full((16, 15), 10.0)
            grid[0, 0] = 10 + index * 0.3
            grid[5, 5] = 300
            health.update(grid, float(index))
        self.assertEqual(health.cell(0, 0)["state"], "Drifting")
        self.assertFalse(np.isfinite(health.cell(5, 5)["drift"]))

    def test_health_warnings_need_repeated_evidence(self):
        health = SensorHealth()
        for index in range(5):
            grid = np.full((16, 15), 10.0)
            grid[1, 1] = 1000
            health.update(grid, float(index))
        self.assertEqual(health.cell(1, 1)["state"], "Saturated")

        for index in range(3):
            grid = np.full((16, 15), 10.0)
            grid[2, 2] = np.nan
            grid[3, 3] = 1200
            health.update(grid, float(index + 10))
        self.assertEqual(health.cell(2, 2)["state"], "Missing")
        self.assertEqual(health.cell(3, 3)["state"], "Invalid")

    def test_weighted_center_supports_relative_grids_and_noise_cutoff(self):
        values = np.zeros((16, 15))
        values[1, 2] = 4
        values[5, 8] = 12
        self.assertEqual(weighted_center(values, 5), (8.0, 5.0))
        self.assertEqual(weighted_center(values, 20), (None, None))


if __name__ == "__main__":
    unittest.main()
