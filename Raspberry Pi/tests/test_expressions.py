"""Free-form formulas: whitelist, evaluation, errors."""

import unittest

import numpy as np

from processing.expressions import EXAMPLES, compile_expression, variables
from processing.hotspots import HotspotTracker
from processing.motion import MotionAnalyzer
from processing.signals import Context
from processing.temporal import TemporalAnalysis

SHAPE = (16, 15)


def context(pressure=None):
    if pressure is None:
        pressure = np.zeros(SHAPE)
        pressure[:4, :4] = 30.0
    return Context(pressure, 100.0, 2.0, TemporalAnalysis(), HotspotTracker(), MotionAnalyzer(), None)


def run(text, ctx=None):
    return compile_expression(text).evaluate(ctx or context())


class ExpressionTests(unittest.TestCase):
    def test_grid_and_number_results(self):
        grid = run("pressure * 2 + 1")
        self.assertEqual(grid.shape, SHAPE)
        self.assertEqual(grid[0, 0], 61.0)
        self.assertEqual(grid[10, 10], 1.0)
        self.assertEqual(run("2 + 3 * 4"), 14.0)
        self.assertEqual(run("active_hotspots + 1"), 1.0)

    def test_functions_and_comparisons(self):
        self.assertEqual(run("where(pressure > 20, 1, 0)").sum(), 16)
        self.assertEqual(run("clip(pressure, 0, 10)").max(), 10)
        self.assertEqual(run("max(pressure, 40)").min(), 40)
        self.assertEqual(run("(pressure > 20 and pressure < 40) * 5").max(), 5)
        self.assertEqual(run("1 if pressure > 20 else 0").sum(), 16)

    def test_windowed_names_and_unknowns(self):
        self.assertIn("exposure_15", variables())
        self.assertNotIn("pressure_15", variables())  # pressure is not windowed
        self.assertEqual(run("exposure_15").shape, SHAPE)
        for bad in ("exposure_7", "nonsense + 1", "pressure +", "", "min", "min(1)", "foo(1)", "abs(x=1)",
                    "__import__('os')", "pressure.max()", "pressure[0]", "'a'", "True", "lambda: 1",
                    "[1, 2]", "1 if" , "x" * 400):
            with self.assertRaises(ValueError, msg=bad):
                compile_expression(bad)

    def test_bad_arithmetic_gives_nan_not_an_error(self):
        result = run("1 / pressure")
        self.assertTrue(np.isnan(result[10, 10]) and result[0, 0] == 1 / 30)
        self.assertTrue(np.isnan(run("repositions / active_hotspots")))
        self.assertTrue(np.isnan(run("9 ** 9 ** 9")))  # inf is hidden too

    def test_no_pressure_frame(self):
        ctx = context()._replace(pressure=None)
        self.assertIsNone(compile_expression("pressure").evaluate(ctx))

    def test_examples_all_compile_and_run(self):
        for text in EXAMPLES:
            self.assertIsNotNone(run(text), text)


if __name__ == "__main__":
    unittest.main()
