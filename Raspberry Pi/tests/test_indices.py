"""Custom indices: signal registry, evaluation, warning state, settings, GUI."""

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from processing.hotspots import HotspotTracker
from processing.indices import (INACTIVE, NEAR, OK, OVER, IndexMonitor, default_indices,
                                evaluate_indices, validate_indices)
from processing.motion import MotionAnalyzer
from processing.roi import rectangle_mask
from processing.settings import builtin_preset, load_preset, save_preset, validate_settings
from processing.signals import SIGNALS, WINDOWS_MIN, Context, read_signal
from processing.temporal import TemporalAnalysis

SHAPE = (16, 15)


class FakeTemporal:
    """Exact per-cell values, so evaluation tests do not depend on integration timing"""

    def __init__(self):
        self.exposure = np.zeros(SHAPE)
        self.burden = np.zeros(SHAPE)
        self.loaded_s = np.zeros(SHAPE)
        self.since = np.full(SHAPE, np.nan)
        self.relief = np.zeros(SHAPE)

    def rolling(self, minutes=None):
        return (self.exposure if minutes is None else self.exposure / 2), None, None

    def time_since_relief(self):
        return self.since

    def relief_percent(self, minutes=None):
        return self.relief


def fake_context(pressure=None, roi=None, timestamp=1000.0):
    if pressure is None:
        pressure = np.zeros(SHAPE)
        pressure[:4, :4] = 30.0
    return Context(pressure, timestamp, 2.0, FakeTemporal(), HotspotTracker(), MotionAnalyzer(), roi)


class SignalTests(unittest.TestCase):
    def test_every_signal_reads_from_the_real_trackers(self):
        pressure = np.zeros(SHAPE)
        pressure[:4, :4] = 30.0
        temporal = TemporalAnalysis()
        temporal.max_gap_s = 30
        for timestamp in range(0, 601, 10):
            temporal.update(pressure, timestamp)
        context = Context(pressure, 600.0, 2.0, temporal, HotspotTracker(), MotionAnalyzer(), None)
        for name, signal in SIGNALS.items():
            for minutes in (WINDOWS_MIN if signal.windowed else (None,)):
                with self.subTest(signal=name, minutes=minutes):
                    value = read_signal(name, context, minutes)
                    if signal.level == "cell":
                        self.assertEqual(value.shape, SHAPE)
                    else:
                        self.assertIsInstance(value, float)
        self.assertAlmostEqual(read_signal("exposure", context)[0, 0], 300.0, delta=1.0)
        self.assertEqual(read_signal("contact_cells", context), 16.0)

    def test_cell_signals_are_blank_where_pressure_is_unknown(self):
        pressure = np.zeros(SHAPE)
        pressure[0, 0] = np.nan
        context = fake_context(pressure)
        context.temporal.burden[:] = 5.0
        burden = read_signal("burden", context)
        self.assertTrue(np.isnan(burden[0, 0]))
        self.assertEqual(burden[1, 1], 5.0)

    def test_never_relieved_cell_counts_its_loaded_time(self):
        context = fake_context()
        context.temporal.loaded_s[0, 0] = 900.0
        context.temporal.since[2, 2] = 40.0
        since = read_signal("since_relief", context)
        self.assertEqual(since[0, 0], 900.0)   # never relieved: at least its loaded time
        self.assertEqual(since[2, 2], 40.0)
        self.assertEqual(since[10, 10], 0.0)   # never loaded

    def test_counts_respect_the_window(self):
        context = fake_context(timestamp=1000.0)
        context.motion.repositions.extend({"timestamp": t} for t in (100.0, 800.0, 990.0))
        context.motion.reposition_total = 7
        self.assertEqual(read_signal("repositions", context, None), 7.0)   # session total
        self.assertEqual(read_signal("repositions", context, 5), 2.0)      # last 300 s
        self.assertEqual(read_signal("repositions", context, 60), 3.0)


def map_index(name="Load", **overrides):
    definition = {"name": name, "layer": "map", "threshold": 1.0, "near_fraction": 0.8,
                  "terms": [{"signal": "burden", "window_min": None, "reference": 100.0,
                             "weight": 1.0, "inverted": False}]}
    definition.update(overrides)
    return definition


def summary_index(terms, name="Overview"):
    return {"name": name, "layer": "summary", "threshold": 1.0, "near_fraction": 0.8, "terms": terms}


def term(**keys):
    return {"reference": 1.0, "weight": 1.0, "inverted": False, **keys}


class EvaluationTests(unittest.TestCase):
    def evaluate(self, definitions, context):
        return evaluate_indices(validate_indices(definitions), context)

    def test_map_index_is_a_weighted_average_and_is_not_capped(self):
        context = fake_context()
        context.temporal.burden[0, 0] = 400.0      # 4.0 at reference 100
        context.temporal.loaded_s[0, 0] = 3600.0   # 0.5 at reference 7200
        definition = map_index(terms=[
            term(signal="burden", window_min=None, reference=100.0, weight=3.0),
            term(signal="loaded_time", window_min=None, reference=7200.0, weight=1.0)])
        grid = self.evaluate([definition], context)["Load"]
        self.assertAlmostEqual(grid[0, 0], (3 * 4.0 + 1 * 0.5) / 4)
        self.assertEqual(grid[5, 5], 0.0)

    def test_windowed_term_uses_its_window(self):
        context = fake_context()
        context.temporal.exposure[0, 0] = 300.0   # FakeTemporal halves it for any window
        definition = map_index(terms=[term(signal="exposure", window_min=15, reference=300.0)])
        self.assertAlmostEqual(self.evaluate([definition], context)["Load"][0, 0], 0.5)

    def test_inverted_term_floors_at_zero(self):
        context = fake_context(timestamp=1000.0)
        context.motion.repositions.extend({"timestamp": 990.0} for _ in range(3))
        definition = summary_index([term(signal="repositions", window_min=5, reference=2.0, inverted=True)])
        self.assertEqual(self.evaluate([definition], context)["Overview"], 0.0)
        context.motion.repositions.clear()
        self.assertEqual(self.evaluate([definition], context)["Overview"], 1.0)

    def test_unknown_cells_stay_blank_and_reducers_skip_them(self):
        pressure = np.zeros(SHAPE)
        pressure[0, 0] = np.nan
        context = fake_context(pressure)
        context.temporal.burden[:] = 50.0
        definitions = [map_index(), summary_index([term(source="Load", reducer="mean", region="mat")])]
        values = self.evaluate(definitions, context)
        self.assertTrue(np.isnan(values["Load"][0, 0]))
        self.assertAlmostEqual(values["Overview"], 0.5)

    def test_reducers_over_mat_and_roi(self):
        context = fake_context(roi=rectangle_mask(SHAPE, (0, 0), (1, 1)))
        context.temporal.burden[0, 0] = 200.0
        context.temporal.burden[5, 5] = 300.0
        for reducer, region, extra, expected in (
                ("peak", "mat", {}, 3.0), ("peak", "roi", {}, 2.0), ("mean", "roi", {}, 0.5),
                ("fraction_above", "roi", {"reducer_value": 1.0}, 0.25)):
            with self.subTest(reducer=reducer, region=region):
                definitions = [map_index(), summary_index(
                    [term(source="Load", reducer=reducer, region=region, **extra)])]
                self.assertAlmostEqual(self.evaluate(definitions, context)["Overview"], expected)

    def test_summary_can_reduce_a_cell_signal_directly(self):
        context = fake_context()
        definition = summary_index([term(signal="pressure", window_min=None, reference=60.0,
                                         reducer="peak", region="mat")])
        self.assertAlmostEqual(self.evaluate([definition], context)["Overview"], 0.5)

    def test_unknown_cases(self):
        definitions = [map_index(), summary_index([term(source="Load", reducer="peak", region="roi")])]
        self.assertIsNone(self.evaluate(definitions, fake_context())["Overview"])   # no ROI selected
        none_context = fake_context()._replace(pressure=None)
        self.assertEqual(self.evaluate(definitions, none_context), {"Load": None, "Overview": None})
        blank = self.evaluate(definitions, fake_context(np.full(SHAPE, np.nan), roi=rectangle_mask(SHAPE, (0, 0), (1, 1))))
        self.assertIsNone(blank["Overview"])   # nothing valid to reduce

    def test_summary_defined_before_its_map_still_works(self):
        context = fake_context()
        context.temporal.burden[0, 0] = 100.0
        definitions = [summary_index([term(source="Load", reducer="peak", region="mat")]), map_index()]
        self.assertAlmostEqual(self.evaluate(definitions, context)["Overview"], 1.0)

    def test_built_in_examples_are_valid_and_evaluate(self):
        values = self.evaluate(default_indices(), fake_context())
        self.assertEqual(values["Sustained load"].shape, SHAPE)
        self.assertIsInstance(values["Mat overview"], float)


class ValidationTests(unittest.TestCase):
    def test_each_rule_names_the_index(self):
        bad = {
            "empty name": map_index(name=" "),
            "bad layer": map_index(layer="grid"),
            "no terms": map_index(terms=[]),
            "missing key": map_index(terms=[{"signal": "burden"}]),
            "unknown signal": map_index(terms=[term(signal="mood", window_min=None)]),
            "mat signal in map": map_index(terms=[term(signal="repositions", window_min=None)]),
            "zero reference": map_index(terms=[term(signal="burden", window_min=None, reference=0)]),
            "text weight": map_index(terms=[term(signal="burden", window_min=None, weight="heavy")]),
            "negative weight": map_index(terms=[term(signal="burden", window_min=None, weight=-1)]),
            "all weights zero": map_index(terms=[term(signal="burden", window_min=None, weight=0)]),
            "window on unwindowed": map_index(terms=[term(signal="burden", window_min=5)]),
            "bad window": map_index(terms=[term(signal="exposure", window_min=7)]),
            "zero threshold": map_index(threshold=0),
            "near above one": map_index(near_fraction=1.5),
            "unknown source": summary_index([term(source="Nope", reducer="peak", region="mat")]),
            "bad reducer": summary_index([term(signal="pressure", window_min=None, reducer="median", region="mat")]),
            "no reducer value": summary_index([term(signal="pressure", window_min=None,
                                                    reducer="fraction_above", region="mat")]),
            "not a dict": "Load",
        }
        for label, definition in bad.items():
            with self.subTest(label):
                with self.assertRaisesRegex(ValueError, "^Index '"):
                    validate_indices([definition])

    def test_duplicate_names_and_non_lists_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Index 'Load'"):
            validate_indices([map_index(), map_index()])
        with self.assertRaises(ValueError):
            validate_indices({"name": "Load"})

    def test_summary_cannot_use_a_summary(self):
        first = summary_index([term(signal="repositions", window_min=None)], name="A")
        second = summary_index([term(source="A", reducer="peak", region="mat")], name="B")
        with self.assertRaisesRegex(ValueError, "Index 'B'"):
            validate_indices([first, second])

    def test_validation_returns_a_cleaned_copy(self):
        definition = map_index(threshold="2", terms=[
            {"signal": "exposure", "window_min": 15.0, "reference": "300", "weight": 1}])
        clean = validate_indices([definition])[0]
        self.assertEqual(clean["threshold"], 2.0)
        self.assertEqual(clean["terms"][0], {"signal": "exposure", "window_min": 15, "reference": 300.0,
                                             "weight": 1.0, "inverted": False})
        self.assertEqual(definition["threshold"], "2")   # input untouched


class WarningTests(unittest.TestCase):
    def setUp(self):
        self.context = fake_context()
        self.monitor = IndexMonitor([map_index(), summary_index(
            [term(source="Load", reducer="mean", region="mat")])])
        self.monitor.hold_s = 5.0

    def step(self, peak_burden, timestamp, occupied=True):
        self.context.temporal.burden[:] = 0.0
        self.context.temporal.burden[0, 0] = peak_burden   # reference 100, threshold 1.0, near 0.8
        return self.monitor.update(self.context, timestamp, occupied)

    def test_starts_inactive_and_takes_the_first_state_without_logging(self):
        self.assertEqual(self.monitor.states, {"Load": INACTIVE, "Overview": INACTIVE})
        self.assertEqual(self.step(90, 0), [])
        self.assertEqual(self.monitor.states["Load"], NEAR)
        self.assertEqual(self.monitor.states["Overview"], OK)

    def test_boundaries(self):
        for burden, expected in ((79, OK), (80, NEAR), (99, NEAR), (100, OVER)):
            with self.subTest(burden=burden):
                self.monitor.reset()
                self.step(burden, 0)
                self.assertEqual(self.monitor.states["Load"], expected)

    def test_change_must_hold_in_both_directions(self):
        self.step(50, 0)
        self.assertEqual(self.step(120, 1), [])
        self.assertEqual(self.step(120, 5), [])
        self.assertEqual(self.step(120, 6), [("Load", OK, OVER)])
        self.assertEqual(self.step(50, 7), [])
        self.assertEqual(self.step(50, 12), [("Load", OVER, OK)])

    def test_value_hovering_at_the_line_does_not_flicker(self):
        self.step(50, 0)
        for second in range(1, 30):
            self.assertEqual(self.step(120 if second % 2 else 50, second), [])
        self.assertEqual(self.monitor.states["Load"], OK)

    def test_empty_mat_or_missing_data_is_inactive_and_not_logged(self):
        self.step(120, 0)
        self.assertEqual(self.monitor.states["Load"], OVER)
        self.assertEqual(self.step(120, 1, occupied=False), [])
        self.assertEqual(self.monitor.states["Load"], INACTIVE)
        self.assertEqual(self.step(120, 2, occupied=None), [])
        self.assertEqual(self.monitor.update(self.context._replace(pressure=None), 3, True), [])
        self.assertEqual(self.monitor.states["Load"], INACTIVE)

    def test_map_index_compares_its_peak_cell_and_exposes_the_over_mask(self):
        self.step(250, 0)
        self.assertAlmostEqual(self.monitor.compared("Load"), 2.5)
        mask = self.monitor.over_mask("Load")
        self.assertEqual((int(mask.sum()), bool(mask[0, 0])), (1, True))
        self.assertIsNone(self.monitor.over_mask("Overview"))

    def test_new_definitions_reset_state_and_bad_ones_are_refused(self):
        self.step(120, 0)
        with self.assertRaises(ValueError):
            self.monitor.set_definitions([map_index(), map_index()])
        self.assertEqual(self.monitor.states["Load"], OVER)   # unchanged after a refused set
        self.monitor.set_definitions([map_index(name="Other")])
        self.assertEqual(self.monitor.states, {"Other": INACTIVE})

    def test_default_monitor_uses_the_examples(self):
        self.assertEqual([d["name"] for d in IndexMonitor().definitions], ["Sustained load", "Mat overview"])


class SettingsTests(unittest.TestCase):
    def test_indices_round_trip_through_a_preset_file(self):
        settings = builtin_preset("Default")
        settings["indices"] = validate_indices([map_index()])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preset.json"
            save_preset(path, settings, "With indices")
            self.assertEqual(load_preset(path), ("With indices", settings))

    def test_settings_without_indices_stay_without(self):
        self.assertNotIn("indices", validate_settings(builtin_preset("Sensitive")))

    def test_bad_indices_reject_the_whole_preset(self):
        settings = builtin_preset("Default")
        settings["indices"] = [map_index(terms=[])]
        with self.assertRaisesRegex(ValueError, "Index 'Load'"):
            validate_settings(settings)


class DesktopIndexTests(unittest.TestCase):
    def setUp(self):
        from gui import desktop
        throttle = mock.patch.object(desktop, "INDEX_UPDATE_INTERVAL_S", float("inf"))
        throttle.start()   # only the forced evaluations in frame() run
        self.addCleanup(throttle.stop)
        try:
            self.app = desktop.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(self.app._on_close)
        self.app.indices.hold_s = 0.0
        self.app.occupancy.enter_s = 0.0

    def frame(self, timestamp, value=30.0):
        grid = np.zeros(SHAPE)
        grid[:4, :4] = value * 20   # default linear calibration: 1000 raw = 50 kPa
        self.app._handle_new_frame(grid, sample_time=timestamp)
        self.app._update_indices(force=True)

    def test_a_chip_per_index_and_an_event_when_one_goes_over(self):
        self.assertEqual(list(self.app.index_chips), ["Sustained load", "Mat overview"])
        self.app._set_indices([map_index(terms=[term(signal="pressure", window_min=None, reference=10.0)])])
        self.assertEqual(list(self.app.index_chips), ["Load"])
        self.frame(1, value=1.0)    # 4 cells at 1 kPa: no contact, so no patient
        self.assertEqual(self.app.indices.states["Load"], "inactive")
        self.frame(2, value=5.0)    # load appears...
        self.frame(3, value=5.0)    # ...and has held: patient detected, index 0.5 = ok (not logged)
        self.frame(4, value=30.0)   # index 3.0: over, pending
        self.frame(5, value=30.0)   # held: over, logged once
        self.assertEqual(self.app.indices.states["Load"], "over")
        kinds = [event["kind"] for event in self.app.timeline.events]
        self.assertEqual(kinds.count("index_over_threshold"), 1)
        self.assertEqual(self.app.index_chips["Load"].cget("bg"), "#bd5555")
        self.app._update_plot()     # draws the over-threshold outline without error

    def test_settings_carry_indices_and_old_presets_leave_them_alone(self):
        custom = [map_index()]
        settings = self.app.current_settings()
        self.assertEqual([d["name"] for d in settings["indices"]], ["Sustained load", "Mat overview"])
        settings["indices"] = custom
        self.app.apply_engineering_settings(settings)
        self.assertEqual([d["name"] for d in self.app.indices.definitions], ["Load"])
        del settings["indices"]     # an older preset
        self.app.apply_engineering_settings(settings)
        self.assertEqual([d["name"] for d in self.app.indices.definitions], ["Load"])

    def test_summary_history_is_kept_for_the_trend(self):
        self.frame(1)
        self.frame(2)
        self.assertEqual(len(self.app.index_history["Mat overview"]), 2)
        self.assertNotIn("Sustained load", self.app.index_history)

    def test_disconnect_clears_index_state(self):
        self.frame(1)
        self.app._disconnect()
        self.assertEqual(set(self.app.indices.states.values()), {"inactive"})

    def test_indices_window_lists_and_draws_both_layers(self):
        self.frame(1)
        self.frame(2)
        self.app._open_indices()
        window = self.app.indices_window
        self.assertEqual(list(window.list.get_children()), ["Sustained load", "Mat overview"])
        for name in ("Sustained load", "Mat overview"):
            window.list.selection_set(name)
            window.refresh()
        self.assertEqual(window.list.set("Mat overview", "state"), self.app.indices.states["Mat overview"])
        self.app._set_indices([map_index()])
        window.refresh()
        self.assertEqual(list(window.list.get_children()), ["Load"])

    def test_editor_builds_an_index_and_apply_uses_it(self):
        self.app._open_engineering()
        window = self.app.engineering_window
        editor = window.index_editor
        self.assertEqual([d["name"] for d in editor.get_definitions()], ["Sustained load", "Mat overview"])
        editor._add_index("map")
        editor.name_var.set("Peak load")
        editor.threshold_var.set("2")
        editor.input_var.set("pressure")
        editor._input_chosen()
        self.assertEqual(float(editor.reference_var.get()), 20.0)   # pre-filled default reference
        editor.weight_var.set("1")
        editor._add_term()
        editor._add_index("summary")
        editor.name_var.set("Peak share")
        editor.input_var.set("index: Peak load")
        editor._input_chosen()
        editor.reducer_var.set("fraction_above")
        editor.reducer_value_var.set("1.0")
        editor._add_term()
        window._apply()
        names = [d["name"] for d in self.app.indices.definitions]
        self.assertEqual(names, ["Sustained load", "Mat overview", "Peak load", "Peak share"])
        self.assertEqual(self.app.indices.definitions[2]["threshold"], 2.0)
        self.assertEqual(self.app.indices.definitions[3]["terms"][0]["reducer_value"], 1.0)
        self.assertIn("Peak share", self.app.index_chips)

        editor._add_index("map")           # no terms: must be refused, nothing applied
        window._apply()
        self.assertIn("Index '", window.settings_status.get())
        self.assertEqual(len(self.app.indices.definitions), 4)


if __name__ == "__main__":
    unittest.main()
