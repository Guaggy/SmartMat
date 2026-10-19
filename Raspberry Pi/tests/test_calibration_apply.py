"""IndividualCalibration.apply converts a frame with arrays; it must give exactly what the one-cell-at-a-time conversion gives,
and notice every change to a cell."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

import config
from processing.calibration import IndividualCalibration, _convert_curve


def reference(calibration, grid):
    """The original, slow way: one curve conversion per cell"""
    pressure = np.full(grid.shape, np.nan, dtype=float)
    for (row, col), cell in calibration.cells.items():
        pressure[row, col] = _convert_curve(np.asarray([grid[row, col]]), cell)[0]
    return pressure


def mixed_calibration(seed=3):
    rng = np.random.default_rng(seed)
    calibration = IndividualCalibration()
    for row in range(config.TOTAL_ROWS):
        for col in range(config.TOTAL_COLS):
            kind = (row * 7 + col * 3) % 5
            calibration.set_offset(row, col, float(rng.uniform(0, 6)))
            if kind == 0:
                continue                                           # no points: stays NaN
            offset = calibration.get_cell(row, col)["offset"]
            calibration.add_point(row, col, offset + float(rng.uniform(20, 200)), float(rng.uniform(5, 60)))
            if kind >= 3:
                calibration.add_point(row, col, offset + float(rng.uniform(210, 250)), float(rng.uniform(61, 120)))
            calibration.set_model(row, col, "linear" if kind != 4 else "piecewise")
    return calibration


class ApplyTests(unittest.TestCase):
    def check(self, calibration, grids=4):
        rng = np.random.default_rng(1)
        for _ in range(grids):
            grid = rng.uniform(0, 255, (config.TOTAL_ROWS, config.TOTAL_COLS))
            np.testing.assert_array_equal(calibration.apply(grid), reference(calibration, grid))

    def test_same_numbers_as_the_cell_by_cell_conversion_for_mixed_models_and_empty_cells(self):
        calibration = mixed_calibration()
        self.check(calibration)
        self.assertTrue(np.isnan(calibration.apply(np.ones((config.TOTAL_ROWS, config.TOTAL_COLS)))).any())

    def test_calibrated_count_matches_the_per_cell_check_and_follows_changes(self):
        calibration = mixed_calibration()
        slow = lambda: sum(calibration.is_calibrated(row, col) for row, col in calibration.cells)
        self.assertEqual(calibration.calibrated_count, slow())
        calibration.add_point(0, 0, 200.0, 10.0)           # cell (0, 0) had no points
        self.assertEqual(calibration.calibrated_count, slow())
        calibration.remove_point(0, 0, 0)
        self.assertEqual(calibration.calibrated_count, slow())

    def test_the_default_calibration(self):
        self.check(IndividualCalibration.default())

    def test_a_change_to_a_cell_is_picked_up_at_once(self):
        calibration = IndividualCalibration.default()
        grid = np.full((config.TOTAL_ROWS, config.TOTAL_COLS), 100.0)
        before = calibration.apply(grid)
        calibration.add_point(2, 3, 150.0, 5.0)
        after = calibration.apply(grid)
        self.assertNotEqual(after[2, 3], before[2, 3])
        np.testing.assert_array_equal(after, reference(calibration, grid))
        calibration.set_model(2, 3, "piecewise")
        np.testing.assert_array_equal(calibration.apply(grid), reference(calibration, grid))
        calibration.remove_point(2, 3, 0)
        np.testing.assert_array_equal(calibration.apply(grid), reference(calibration, grid))

    def test_nan_and_inf_inputs_behave_as_before(self):
        calibration = IndividualCalibration.default()
        grid = np.full((config.TOTAL_ROWS, config.TOTAL_COLS), 80.0)
        grid[0, 0], grid[1, 1] = np.nan, np.inf
        np.testing.assert_array_equal(calibration.apply(grid), reference(calibration, grid))

    def test_loading_a_saved_calibration_rebuilds_it(self):
        source = mixed_calibration(7)
        copy = IndividualCalibration.default()
        grid = np.full((config.TOTAL_ROWS, config.TOTAL_COLS), 90.0)
        copy.apply(grid)                                  # compiled for the default
        with tempfile.TemporaryDirectory() as folder:
            source.save(Path(folder) / "cal.json")
            copy.load(Path(folder) / "cal.json")
        np.testing.assert_array_equal(copy.apply(grid), reference(copy, grid))
        np.testing.assert_array_equal(copy.apply(grid), source.apply(grid))


if __name__ == "__main__":
    unittest.main()
