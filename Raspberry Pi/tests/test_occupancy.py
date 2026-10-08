"""Patient-detected indicator: contact-cell count with enter/exit hold times."""

import unittest

import numpy as np

from processing.occupancy import OccupancyDetector


def grid(loaded_cells, value=30.0):
    values = np.zeros((16, 15))
    values.flat[:loaded_cells] = value
    return values


class OccupancyTests(unittest.TestCase):
    def setUp(self):
        self.detector = OccupancyDetector()
        self.detector.min_cells = 4
        self.detector.enter_s = 2.0
        self.detector.exit_s = 5.0

    def feed(self, loaded_cells, timestamp):
        return self.detector.update(grid(loaded_cells), timestamp, threshold_kpa=2.0)

    def test_unknown_until_there_is_pressure_data(self):
        self.assertIsNone(self.detector.occupied)
        self.assertIsNone(self.detector.update(None, 0.0, 2.0))

    def test_first_valid_frame_is_taken_as_is(self):
        self.assertTrue(self.feed(10, 0.0))
        self.detector.reset()
        self.assertFalse(self.feed(0, 0.0))

    def test_too_few_cells_is_not_a_patient(self):
        self.assertFalse(self.feed(3, 0.0))
        self.assertFalse(self.feed(3, 10.0))

    def test_load_must_hold_before_patient_is_detected(self):
        self.feed(0, 0.0)
        self.assertFalse(self.feed(10, 1.0))
        self.assertFalse(self.feed(10, 2.5))
        self.assertTrue(self.feed(10, 3.0))

    def test_brief_lift_does_not_clear_the_patient(self):
        self.feed(10, 0.0)
        self.assertTrue(self.feed(0, 1.0))
        self.assertTrue(self.feed(0, 4.0))
        self.assertTrue(self.feed(10, 5.0))   # back before exit_s: the timer starts over
        self.assertTrue(self.feed(0, 9.0))
        self.assertFalse(self.feed(0, 14.0))

    def test_missing_pressure_goes_back_to_unknown(self):
        self.feed(10, 0.0)
        self.assertIsNone(self.detector.update(None, 1.0, 2.0))
        self.assertIsNone(self.detector.update(np.full((16, 15), np.nan), None, 2.0))

    def test_nan_cells_do_not_count_as_contact(self):
        values = np.full((16, 15), np.nan)
        self.assertFalse(self.detector.update(values, 0.0, 2.0))

    def test_playback_loop_restarts_the_hold_timer(self):
        self.feed(0, 100.0)
        self.feed(10, 101.0)
        self.assertFalse(self.feed(10, 0.0))   # time jumped back
        self.assertTrue(self.feed(10, 2.0))


if __name__ == "__main__":
    unittest.main()
