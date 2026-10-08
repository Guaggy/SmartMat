# Custom Indices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user combine standard named signals into weighted indices (per-cell maps and whole-mat summaries) from a table, plot them, and get a quiet OK / near / over-threshold warning on each.

**Architecture:** `processing/signals.py` is a registry that reads existing tracker state (no new signal math). `processing/indices.py` validates index definitions (plain dicts), evaluates them in two fixed layers, and holds an `IndexMonitor` with the warning state machine. Definitions travel in the existing engineering-settings dict under a new `"indices"` key, so presets, recordings and replay carry them. The GUI adds status-bar chips, a heatmap outline, timeline events, an Indices window and an editor tab in the Engineering window.

**Tech Stack:** Python 3.13, numpy, Tkinter, matplotlib, `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-08-custom-indices-design.md`

## Global Constraints

- UI wording is "index" and "threshold". Never "risk". The Indices window states that indices are user-defined engineering indices, not validated scores.
- Exactly two layers: `map` (cell signals) and `summary`. A summary index is never a term of another index.
- Normalised term = `value / reference`; inverted = `max(0, 1 - value / reference)`; not capped. Index = `sum(weight * n) / sum(weight)`. Default threshold 1.0, default near margin 0.8.
- Warning states `inactive`, `ok`, `near`, `over`; one hold time `INDEX_WARNING_HOLD_S = 5.0` in both directions; `inactive` whenever the value is unknown or `OccupancyDetector.occupied is not True`. Transitions to or from `inactive` are not logged.
- Timeline event kinds: `index_near_threshold`, `index_over_threshold`, `index_cleared`.
- Indices are evaluated at most once per `INDEX_UPDATE_INTERVAL_S = 1.0`, not per frame.
- A preset or recording without `"indices"` leaves the current indices unchanged.
- Read the grid size only as `config.TOTAL_ROWS` / `config.TOTAL_COLS` (never `from config import TOTAL_ROWS`).
- No new dependencies. No commits (unrelated uncommitted work is in the tree; staging is left to Even). No AI attribution.
- New config constants go in both `config.example.py` and the local `config.py`.
- After every task, from `Raspberry Pi/`: `python -m unittest discover -s tests -v`. Baseline: 75 tests, OK. To run one file: `python -m unittest discover -s tests -p "test_indices.py" -v`.

## Where the spec did not match the code

1. **`since_relief` is unknown for a cell that has never been relieved**, which is exactly the cell that matters most. `TemporalAnalysis.time_since_relief()` returns NaN there. The signal falls back to that cell's `loaded_s` (time observed loaded), which is a lower bound and is 0 for a cell that was never loaded. Task 1.
2. **Temporal grids are 0, not NaN, for uncalibrated cells.** `read_signal` blanks every cell signal where the pressure frame is not finite, so the spec's "uncalibrated cells are blank" holds. Task 1.
3. **Built-in presets do not carry indices.** The spec says they include the two examples, but then "Use preset: Sensitive" would wipe the user's own indices. The examples are the app's starting definitions instead, and built-in presets leave indices unchanged. Task 4.
4. **`apply_settings` keeps its signature.** It is called from `reanalysis.py` and `session_events.py` with only the three trackers. `validate_settings` passes a validated `"indices"` through; `gui/desktop.py` applies it to the monitor. Tasks 4 and 5.
5. **The editor gets its own file** (`gui/index_editor.py`), not inline in `engineering_window.py`, so that file does not double in size. Task 7.

## Review Focus

1. A definition from a hand-edited preset with a missing key, an unknown signal, a zero reference or a text weight must be rejected with a message naming the index, not crash a frame update. Test in Task 2.
2. A map index over an uncalibrated mat or all-NaN cells must be unknown, not 0 or a NumPy warning. Test in Task 2.
3. An index value hovering at the threshold must not flip state every evaluation. Test in Task 3.
4. A patient leaving the mat must not leave a chip red or log "cleared". Test in Task 3.
5. Loading an old preset or an old recording must not delete the user's indices. Tests in Tasks 4 and 5.

## File Structure

| File | Change |
|---|---|
| `processing/signals.py` | new: `Signal`, `Context`, `SIGNALS`, `WINDOWS_MIN`, `read_signal` |
| `processing/indices.py` | new: `default_indices`, `validate_indices`, `evaluate_indices`, `IndexMonitor` |
| `processing/settings.py` | `validate_settings` passes `"indices"` through |
| `gui/desktop.py` | monitor, chips, outline, events, settings/recording/replay wiring, button |
| `gui/indices_window.py` | new: list, map heatmap, summary trend |
| `gui/index_editor.py` | new: table editor |
| `gui/engineering_window.py` | "Indices" tab hosting the editor |
| `config.example.py`, `config.py` | two constants |
| `tests/test_indices.py` | new: all tests for this plan |
| `STATUS.md`, `notes.md`, `README.md` | docs |

---

### Task 1: Signal registry

**Files:**
- Create: `processing/signals.py`
- Test: `tests/test_indices.py` (create)

**Interfaces:**
- Produces:
  - `Signal(label, unit, level, reference, windowed, read)`; `level` is `"cell"` or `"mat"`.
  - `Context(pressure, timestamp, contact_threshold_kpa, temporal, hotspots, motion, roi)`; `roi` is `(row0, row1, col0, col1)` or `None`.
  - `SIGNALS: dict[str, Signal]`; `WINDOWS_MIN = (None, 1, 5, 15, 30, 60)`.
  - `read_signal(name, context, minutes=None)` -> float grid (cell) or float (mat).

- [ ] **Step 1: Write the failing tests** - create `tests/test_indices.py`:

```python
"""Custom indices: signal registry, evaluation, warning state, settings, GUI."""

import types
import unittest

import numpy as np

from processing.hotspots import HotspotTracker
from processing.motion import MotionAnalyzer
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, expect failure** - `python -m unittest discover -s tests -p "test_indices.py" -v` -> `ModuleNotFoundError: No module named 'processing.signals'`.

- [ ] **Step 3: Implement** - create `processing/signals.py`:

```python
"""Named signals read from the existing trackers, the building blocks of custom indices."""

from collections import namedtuple

import numpy as np

from config import HOTSPOT_ACTIVATE_KPA, HOTSPOT_PERSISTENCE_S, TEMPORAL_WINDOWS_MIN
from processing.statistics import contact_mask

# level: "cell" reads a grid, "mat" reads one number. reference: the value that counts as 1.0
# in an index - a starting point for the user to change, not a recommendation.
Signal = namedtuple("Signal", "label unit level reference windowed read")
Context = namedtuple("Context", "pressure timestamp contact_threshold_kpa temporal hotspots motion roi")
WINDOWS_MIN = (None,) + tuple(TEMPORAL_WINDOWS_MIN)  # None = whole session


def _since_relief(context, _minutes):
    since = context.temporal.time_since_relief()
    # never relieved while we watched: at least as long as the cell has been seen loaded
    return np.where(np.isfinite(since), since, context.temporal.loaded_s)


def _count_recent(records, session_total, context, minutes):
    if minutes is None:
        return float(session_total)
    cutoff = context.timestamp - minutes * 60
    # ponytail: the trackers keep the last 100 repositions / 200 movements, so a windowed
    # count tops out there; raise their deque sizes if longer windows are ever added
    return float(sum(record["timestamp"] >= cutoff for record in records))


SIGNALS = {
    "pressure": Signal("Pressure", "kPa", "cell", float(HOTSPOT_ACTIVATE_KPA), False,
                       lambda c, m: c.pressure),
    "exposure": Signal("Exposure", "kPa*min", "cell", 300.0, True,
                       lambda c, m: c.temporal.rolling(m)[0]),
    "burden": Signal("Burden", "", "cell", 300.0, False, lambda c, m: c.temporal.burden),
    "since_relief": Signal("Time since relief", "s", "cell", 7200.0, False, _since_relief),
    "loaded_time": Signal("Loaded time", "s", "cell", 7200.0, False, lambda c, m: c.temporal.loaded_s),
    "relief_percent": Signal("Relieved share of time", "%", "cell", 100.0, True,
                             lambda c, m: c.temporal.relief_percent(m)),
    "repositions": Signal("Repositions", "count", "mat", 2.0, True,
                          lambda c, m: _count_recent(c.motion.repositions, c.motion.reposition_total, c, m)),
    "movements": Signal("Movements", "count", "mat", 10.0, True,
                        lambda c, m: _count_recent(c.motion.movements, c.motion.movement_total, c, m)),
    "active_hotspots": Signal("Active hotspots", "count", "mat", 1.0, False,
                              lambda c, m: float(len(c.hotspots.active))),
    "longest_hotspot": Signal("Longest active hotspot", "s", "mat", float(HOTSPOT_PERSISTENCE_S), False,
                              lambda c, m: float(max((t["active_s"] for t in c.hotspots.active), default=0.0))),
    "contact_cells": Signal("Contact cells", "cells", "mat", 60.0, False,
                            lambda c, m: float(contact_mask(c.pressure, c.contact_threshold_kpa).sum())),
}


def read_signal(name, context, minutes=None):
    """Current value of a signal: a grid (NaN where pressure is unknown) or one number"""
    signal = SIGNALS[name]
    value = signal.read(context, minutes if signal.windowed else None)
    if signal.level == "mat":
        return value
    return np.where(np.isfinite(context.pressure), np.asarray(value, dtype=float), np.nan)
```

- [ ] **Step 4: Run everything** - `python -m unittest discover -s tests -v` -> 79 tests, OK.

---

### Task 2: Index definitions and evaluation

**Files:**
- Create: `processing/indices.py`
- Test: `tests/test_indices.py`

**Interfaces:**
- Consumes: `SIGNALS`, `WINDOWS_MIN`, `Context`, `read_signal` (Task 1).
- Produces:
  - `REDUCERS = ("peak", "mean", "fraction_above")`, `REGIONS = ("mat", "roi")`
  - `default_indices() -> list[dict]` (new list each call)
  - `validate_indices(definitions) -> list[dict]` (cleaned copy; raises `ValueError` whose text starts `Index '<name>': `)
  - `evaluate_indices(definitions, context) -> dict[name, ndarray | float | None]`
  - Definition keys: `name`, `layer` (`"map"`/`"summary"`), `threshold`, `near_fraction`, `terms`. Term keys: `reference`, `weight`, `inverted`, and either `source` (map index name) or `signal` + `window_min`; reduced terms add `reducer`, `region`, and `reducer_value` for `fraction_above`.

- [ ] **Step 1: Write the failing tests** - add to `tests/test_indices.py` (import: `from processing.indices import default_indices, evaluate_indices, validate_indices`):

```python
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
        context = fake_context(roi=(0, 1, 0, 1))
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
        blank = self.evaluate(definitions, fake_context(np.full(SHAPE, np.nan), roi=(0, 1, 0, 1)))
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
```

- [ ] **Step 2: Run, expect failure** - `ModuleNotFoundError: No module named 'processing.indices'`.

- [ ] **Step 3: Implement** - create `processing/indices.py`:

```python
"""User-defined indices: weighted combinations of named signals, with a warning state.

Two fixed layers. A map index combines cell signals into a grid; a summary index combines
single numbers (whole-mat signals, or a reduction of a map index or cell signal) into one
number. These are engineering indices the user defines, not validated scores.
"""

import math

import numpy as np

from processing.signals import SIGNALS, WINDOWS_MIN, read_signal

REDUCERS = ("peak", "mean", "fraction_above")
REGIONS = ("mat", "roi")


def default_indices():
    """Two examples to start from"""
    return [
        {"name": "Sustained load", "layer": "map", "threshold": 1.0, "near_fraction": 0.8, "terms": [
            {"signal": "exposure", "window_min": 15, "reference": 300.0, "weight": 1.0, "inverted": False},
            {"signal": "since_relief", "window_min": None, "reference": 7200.0, "weight": 1.0,
             "inverted": False}]},
        {"name": "Mat overview", "layer": "summary", "threshold": 1.0, "near_fraction": 0.8, "terms": [
            {"source": "Sustained load", "reducer": "peak", "region": "mat", "reference": 1.0,
             "weight": 2.0, "inverted": False},
            {"signal": "repositions", "window_min": 60, "reference": 2.0, "weight": 1.0,
             "inverted": True}]},
    ]


def _number(value, label, positive=False):
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0):
        raise ValueError(f"{label} must be a {'positive ' if positive else ''}number")
    return number


def _validate_term(term, layer, map_names):
    clean = {}
    source = term.get("source")
    if source is not None:
        if layer != "summary" or source not in map_names:
            raise ValueError(f"'{source}' is not a map index")
        clean["source"] = source
        reduced = True
    else:
        name = term["signal"]
        signal = SIGNALS.get(name)
        if signal is None:
            raise ValueError(f"unknown signal '{name}'")
        if layer == "map" and signal.level != "cell":
            raise ValueError(f"'{name}' is a whole-mat signal; use it in a summary index")
        window = term.get("window_min")
        if window is not None:
            if not signal.windowed or window not in WINDOWS_MIN:
                raise ValueError(f"window {window} min is not available for '{name}'")
            window = int(window)
        clean.update(signal=name, window_min=window)
        reduced = layer == "summary" and signal.level == "cell"
    if reduced:
        reducer, region = term.get("reducer", "peak"), term.get("region", "mat")
        if reducer not in REDUCERS or region not in REGIONS:
            raise ValueError("unknown reducer or region")
        clean.update(reducer=reducer, region=region)
        if reducer == "fraction_above":
            clean["reducer_value"] = _number(term["reducer_value"], "fraction-above value")
    clean["reference"] = _number(term["reference"], "reference", positive=True)
    clean["weight"] = _number(term["weight"], "weight")
    if clean["weight"] < 0:
        raise ValueError("weight must be 0 or more")
    clean["inverted"] = bool(term.get("inverted", False))
    return clean


def _validate_index(definition, taken_names, map_names):
    name = str(definition["name"]).strip()
    if not name or name in taken_names:
        raise ValueError("name must be unique and not empty")
    layer = definition["layer"]
    if layer not in ("map", "summary"):
        raise ValueError("layer must be map or summary")
    near = _number(definition.get("near_fraction", 0.8), "near margin")
    if not 0 < near <= 1:
        raise ValueError("near margin must be above 0 and at most 1")
    terms = [_validate_term(term, layer, map_names) for term in definition["terms"]]
    if sum(term["weight"] for term in terms) <= 0:
        raise ValueError("needs at least one term with a weight above 0")
    return {"name": name, "layer": layer,
            "threshold": _number(definition.get("threshold", 1.0), "threshold", positive=True),
            "near_fraction": near, "terms": terms}


def validate_indices(definitions):
    """Return a cleaned copy of a list of index definitions, or raise ValueError naming the index"""
    if not isinstance(definitions, list):
        raise ValueError("Indices must be a list")
    map_names = {str(item.get("name", "")).strip() for item in definitions
                 if isinstance(item, dict) and item.get("layer") == "map"}
    result = []
    for definition in definitions:
        label = str(definition.get("name", "?")).strip() if isinstance(definition, dict) else "?"
        try:
            result.append(_validate_index(definition, {item["name"] for item in result}, map_names))
        except (AttributeError, KeyError, TypeError, OverflowError) as error:
            raise ValueError(f"Index '{label}': missing or invalid values") from error
        except ValueError as error:
            raise ValueError(f"Index '{label}': {error}") from error
    return result


def _normalise(value, term):
    ratio = value / term["reference"]
    return np.maximum(0.0, 1.0 - ratio) if term["inverted"] else ratio


def _reduce(grid, term, roi):
    if term["region"] == "roi":
        if roi is None:
            return None  # never silently fall back to the whole mat
        row0, row1, col0, col1 = roi
        grid = grid[row0:row1 + 1, col0:col1 + 1]
    valid = grid[np.isfinite(grid)]
    if not valid.size:
        return None
    if term["reducer"] == "peak":
        return float(valid.max())
    if term["reducer"] == "mean":
        return float(valid.mean())
    return float(np.mean(valid > term["reducer_value"]))


def _term_value(term, layer, context, values):
    if "source" in term:
        grid = values[term["source"]]
        return None if grid is None else _reduce(grid, term, context.roi)
    value = read_signal(term["signal"], context, term["window_min"])
    if layer == "summary" and SIGNALS[term["signal"]].level == "cell":
        return _reduce(value, term, context.roi)
    return value


def evaluate_indices(definitions, context):
    """Value of every (validated) index: a grid, a number, or None when unknown"""
    values = {definition["name"]: None for definition in definitions}
    if context.pressure is None:
        return values
    for layer in ("map", "summary"):  # maps first, so summary terms can read them
        for definition in definitions:
            if definition["layer"] != layer:
                continue
            total, weights = 0.0, 0.0
            for term in definition["terms"]:
                value = _term_value(term, layer, context, values)
                if value is None:
                    total = None
                    break
                total = total + term["weight"] * _normalise(value, term)
                weights += term["weight"]
            if total is not None:
                values[definition["name"]] = total / weights if layer == "map" else float(total / weights)
    return values
```

- [ ] **Step 4: Run everything** - `python -m unittest discover -s tests -v` -> 92 tests, OK.

---

### Task 3: Warning state machine

**Files:**
- Modify: `processing/indices.py`, `config.example.py`, `config.py`
- Test: `tests/test_indices.py`

**Interfaces:**
- Consumes: `validate_indices`, `evaluate_indices`, `default_indices` (Task 2).
- Produces: `INACTIVE, OK, NEAR, OVER = "inactive", "ok", "near", "over"`; `IndexMonitor(definitions=None)` with `definitions`, `values`, `states`, `hold_s`, `set_definitions(definitions)`, `reset()`, `compared(name) -> float | None`, `over_mask(name) -> bool ndarray | None`, `update(context, timestamp, occupied) -> list[(name, old_state, new_state)]`.

- [ ] **Step 1: Config constants** - in both `config.example.py` and `config.py`, after the `OCCUPANCY_EXIT_S` line:

```python

# Custom indices (Engineering window > Indices): warning hold time and evaluation rate.
INDEX_WARNING_HOLD_S = 5.0     # a new OK/near/over state must last this long before it shows
INDEX_UPDATE_INTERVAL_S = 1.0  # indices move slowly; no need to evaluate them every frame
```

- [ ] **Step 2: Write the failing tests** - add to `tests/test_indices.py` (import: `from processing.indices import INACTIVE, NEAR, OK, OVER, IndexMonitor`):

```python
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
```

- [ ] **Step 3: Run, expect failure** - `ImportError: cannot import name 'INACTIVE'`.

- [ ] **Step 4: Implement** - in `processing/indices.py` add `from config import INDEX_WARNING_HOLD_S` to the imports, `INACTIVE, OK, NEAR, OVER = "inactive", "ok", "near", "over"` under `REGIONS`, and at the end of the file:

```python
class IndexMonitor:
    """Holds the index definitions, their latest values, and each one's warning state"""

    def __init__(self, definitions=None):
        self.hold_s = INDEX_WARNING_HOLD_S
        self.definitions = validate_indices(default_indices() if definitions is None else definitions)
        self.reset()

    def set_definitions(self, definitions):
        self.definitions = validate_indices(definitions)  # raises before anything changes
        self.reset()

    def reset(self):
        self.values = {definition["name"]: None for definition in self.definitions}
        self.states = {definition["name"]: INACTIVE for definition in self.definitions}
        self._pending = {}  # name -> (state it is moving to, since when)

    def compared(self, name):
        """The number checked against the threshold: the value itself, or a map's peak cell"""
        value = self.values.get(name)
        if isinstance(value, np.ndarray):
            finite = value[np.isfinite(value)]
            return float(finite.max()) if finite.size else None
        return value

    def over_mask(self, name):
        """Cells of a map index at or above its threshold (None for anything else)"""
        value = self.values.get(name)
        if not isinstance(value, np.ndarray):
            return None
        threshold = next(d["threshold"] for d in self.definitions if d["name"] == name)
        return np.isfinite(value) & (value >= threshold)

    def update(self, context, timestamp, occupied):
        """Re-evaluate every index; returns [(name, old_state, new_state)] worth logging"""
        self.values = evaluate_indices(self.definitions, context)
        changes = []
        for definition in self.definitions:
            name = definition["name"]
            value = self.compared(name)
            current = self.states[name]
            if value is None or occupied is not True or timestamp is None:
                self.states[name] = INACTIVE  # an empty mat or missing data never warns
                self._pending.pop(name, None)
                continue
            raw = (OVER if value >= definition["threshold"] else
                   NEAR if value >= definition["near_fraction"] * definition["threshold"] else OK)
            if current == INACTIVE:
                self.states[name] = raw
            elif raw == current:
                self._pending.pop(name, None)
            else:
                target, since = self._pending.get(name, (None, None))
                if target != raw or timestamp < since:
                    self._pending[name] = (raw, timestamp)  # also restarts when playback loops
                elif timestamp - since >= self.hold_s:
                    self.states[name] = raw
                    self._pending.pop(name)
                    changes.append((name, current, raw))
        return changes
```

- [ ] **Step 5: Run everything** - `python -m unittest discover -s tests -v` -> 100 tests, OK.

---

### Task 4: Settings and presets

**Files:**
- Modify: `processing/settings.py`
- Test: `tests/test_indices.py`

**Interfaces:**
- Produces: `validate_settings(settings)` returns `"indices"` (validated) when the input has that key and omits it otherwise. `save_preset` / `load_preset` therefore round-trip indices. `apply_settings`, `capture_settings`, `default_settings`, `builtin_preset` are unchanged.

- [ ] **Step 1: Write the failing tests** - add to `tests/test_indices.py` (imports: `import tempfile`, `from pathlib import Path`, `from processing.settings import builtin_preset, load_preset, save_preset, validate_settings`):

```python
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
```

- [ ] **Step 2: Run, expect failure** - the round-trip test fails (`"indices"` is dropped) and the bad-indices test fails (nothing raised).

- [ ] **Step 3: Implement** - in `processing/settings.py` add `from processing.indices import validate_indices` to the imports, and in `validate_settings` replace the final `return result` with:

```python
    if "indices" in settings:  # absent = leave the current indices alone (older presets)
        result["indices"] = validate_indices(settings["indices"])
    return result
```

- [ ] **Step 4: Run everything** - `python -m unittest discover -s tests -v` -> 103 tests, OK.

---

### Task 5: Main-window wiring

**Files:**
- Modify: `gui/desktop.py`
- Test: `tests/test_indices.py`

**Interfaces:**
- Consumes: `IndexMonitor`, state constants, `default_indices` (Task 3); `Context` (Task 1); `validate_settings` pass-through (Task 4); `OccupancyDetector.occupied`.
- Produces (on `DesktopApp`): `indices: IndexMonitor`, `index_history: dict[name, deque[(time, value)]]`, `index_chips: dict[name, tk.Label]`, `_set_indices(definitions)`, `_update_indices(force=False)`, `_open_indices()`; `current_settings()` includes `"indices"`.

- [ ] **Step 1: Write the failing tests** - add to `tests/test_indices.py` (imports: `import tkinter as tk`, `from processing.indices import default_indices`):

```python
class DesktopIndexTests(unittest.TestCase):
    def setUp(self):
        from gui.desktop import DesktopApp
        try:
            self.app = DesktopApp()
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
```

- [ ] **Step 2: Run, expect failure** - `AttributeError: 'DesktopApp' object has no attribute 'indices'`.

- [ ] **Step 3: Imports and constants** in `gui/desktop.py`: add `import copy` at the top; extend the `from config import (` list with `INDEX_UPDATE_INTERVAL_S`; add

```python
from processing.indices import NEAR, OK, OVER, IndexMonitor, default_indices
from processing.signals import Context
from gui.indices_window import IndicesWindow
```

and under `OCCUPANCY_LABELS`:

```python
INDEX_CHIP_COLORS = {"inactive": "#9da7b1", OK: "#777777", NEAR: "#e8b04e", OVER: "#bd5555"}
INDEX_EVENTS = {OK: "index_cleared", NEAR: "index_near_threshold", OVER: "index_over_threshold"}
INDEX_OUTLINE_COLOR = "#8a4f9e"  # distinct from hotspot red/orange and the blue contact boundary
```

(`gui/indices_window.py` is created in Task 6; to keep this task's tests runnable, create it now as a stub containing only `class IndicesWindow: pass` and replace it in Task 6.)

- [ ] **Step 4: State** - in `__init__` after `self.occupancy = OccupancyDetector()`:

```python
        self.indices = IndexMonitor()
        self.index_history = {}      # summary index name -> recent (time, value) for its trend
        self.index_chips = {}        # index name -> status-bar label
        self.indices_window = None
        self._live_indices = None    # live definitions kept aside while a recording plays
        self._last_index_update = 0.0
```

- [ ] **Step 5: Chips** - in the status-bar block, after `self.occupancy_label.pack(...)`:

```python
        self.index_chip_bar = ttk.Frame(status_bar)
        self.index_chip_bar.pack(side=tk.RIGHT)
        self._build_index_chips()
```

and add next to `_update_occupancy`:

```python
    def _build_index_chips(self):
        for chip in self.index_chip_bar.winfo_children():
            chip.destroy()
        self.index_chips = {}
        for definition in self.indices.definitions:
            chip = tk.Label(self.index_chip_bar, text=definition["name"], fg="white", padx=8)
            chip.pack(side=tk.LEFT, padx=2, pady=2)
            self.index_chips[definition["name"]] = chip
        self._update_index_chips()

    def _update_index_chips(self):
        for name, chip in self.index_chips.items():
            chip.configure(bg=INDEX_CHIP_COLORS[self.indices.states[name]])

    def _set_indices(self, definitions):
        """Replace the index definitions (raises ValueError and changes nothing if invalid)"""
        self.indices.set_definitions(definitions)
        self.index_history = {}
        self._build_index_chips()

    def _update_indices(self, force=False):
        now = time.time()
        if self.frame is None or (not force and now - self._last_index_update < INDEX_UPDATE_INTERVAL_S):
            return
        self._last_index_update = now
        context = Context(self.frame["pressure"], self.frame_timestamp, self.contact_threshold_kpa,
                          self.temporal, self.hotspots, self.motion, self.roi)
        for name, old, new in self.indices.update(context, self.frame_timestamp, self.occupancy.occupied):
            self.add_event(INDEX_EVENTS[new], name, {
                "index": name, "value": self.indices.compared(name), "previous_state": old})
        for definition in self.indices.definitions:
            value = self.indices.values[definition["name"]]
            if definition["layer"] == "summary" and value is not None:
                self.index_history.setdefault(
                    definition["name"], deque(maxlen=HISTORY_MAX_FRAMES)).append((self.frame_timestamp, value))
        self._update_index_chips()

    def _reset_indices(self):
        self.indices.reset()
        self.index_history = {}
        self._update_index_chips()
```

- [ ] **Step 6: Per-frame and reset hooks**
  - In `_handle_new_frame`, directly after the `self.occupancy.update(...)` line: `self._update_indices()`.
  - At each of the four existing `self.occupancy.reset()` calls (in `_apply_grid_shape`, `_connect`, `_disconnect`, and the stale branch of `_check_connection_health`) add `self._reset_indices()` on the next line.
  - In `_handle_new_frame`'s playback-loop branch, after `self.sensor_health.reset()`: `self._reset_indices()`.

- [ ] **Step 7: Settings, recording, replay**
  - `current_settings()` becomes:

```python
    def current_settings(self):
        settings = capture_settings(self.contact_threshold_kpa, self.temporal,
                                    self.hotspots, self.motion)
        settings["indices"] = copy.deepcopy(self.indices.definitions)
        return settings
```

  - In `apply_engineering_settings`, before the `apply_settings(...)` call add `if "indices" in settings: self._set_indices(settings["indices"])` (first, so an invalid set raises before anything else is applied).
  - In `_connect`'s recording branch, replace `self._current_analysis_settings = capture_settings(self.contact_threshold_kpa, self.temporal, self.hotspots, self.motion)` with `self._current_analysis_settings = self.current_settings()` and add `self._live_indices = copy.deepcopy(self.indices.definitions)` on the next line.
  - In `_restore_live_state`, after `self._live_state = None`:

```python
        if self._live_indices is not None:
            self._set_indices(self._live_indices)
            self._live_indices = None
```

  - In `_reset_playback_state`, in the `else:` (reproduce) branch after the `for group, key in ...` loop: `settings["indices"] = metadata.get("indices", default_indices())`; and after the `self.contact_threshold_kpa = apply_settings(...)` line: `self._set_indices(settings.get("indices", default_indices()))`.
  - In `_apply_playback_state_events`, after the `threshold = apply_state_event(...)` call:

```python
                recorded = (event.get("payload") or {}).get("settings", {})
                if event["kind"] == "algorithm_settings_changed" and "indices" in recorded:
                    self._set_indices(recorded["indices"])
```

  - In `_toggle_recording`'s `metadata` dict add `"indices": copy.deepcopy(self.indices.definitions),`.

- [ ] **Step 8: Heatmap outline** - in `_update_plot`, directly before the `if self.roi_patch is not None:` line (same indentation, inside the 2D branch):

```python
            if not difference:
                for name, state in self.indices.states.items():
                    mask = self.indices.over_mask(name) if state == OVER else None
                    if mask is not None and mask.any() and not mask.all():
                        self.axes.contour(np.arange(app_config.TOTAL_COLS), np.arange(app_config.TOTAL_ROWS),
                                          mask.astype(float), levels=[0.5], colors=INDEX_OUTLINE_COLOR,
                                          linewidths=1.3, linestyles="dotted")
```

- [ ] **Step 9: Button, window refresh** - in `_build_options_bar` after the "Movement..." button: `ttk.Button(bar, text="Indices...", command=self._open_indices).pack(side=tk.LEFT, padx=4)`. Add next to `_open_motion`:

```python
    def _open_indices(self):
        if self.indices_window is not None and self.indices_window.window.winfo_exists():
            self.indices_window.window.lift()
        else:
            self.indices_window = IndicesWindow(self.root, self)
```

  In `_poll`, inside the existing `if time.time() - self._last_feature_draw >= 0.5:` block:

```python
                if self.indices_window is not None and self.indices_window.window.winfo_exists():
                    self.indices_window.refresh()
```

- [ ] **Step 10: Run everything** - `python -m unittest discover -s tests -v` -> 107 tests, OK.

---

### Task 6: Indices window

**Files:**
- Create (replace the Task 5 stub): `gui/indices_window.py`
- Test: `tests/test_indices.py`

**Interfaces:**
- Consumes: `app.indices` (`definitions`, `values`, `states`, `compared`), `app.index_history`.
- Produces: `IndicesWindow(parent, app)` with `window`, `list` (Treeview, item ids = index names), `refresh()`.

- [ ] **Step 1: Write the failing test** - add to `DesktopIndexTests`:

```python
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
```

- [ ] **Step 2: Run, expect failure** - `TypeError: IndicesWindow() takes no arguments`.

- [ ] **Step 3: Implement** - `gui/indices_window.py`:

```python
"""Live values of the user-defined indices: a map heatmap or a summary trend."""

import tkinter as tk
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


class IndicesWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Indices")
        self.window.geometry("760x680")
        ttk.Label(self.window, wraplength=740, padding=(8, 6), text=(
            "Indices are weighted combinations of signals that you define under Engineering > Indices. "
            "They are engineering indices, not validated scores: 1.0 means every signal is at the "
            "reference value you chose.")).pack(side=tk.TOP, fill=tk.X)
        columns = ("layer", "value", "threshold", "state")
        self.list = ttk.Treeview(self.window, columns=columns, show="tree headings", height=5)
        self.list.heading("#0", text="Index")
        self.list.column("#0", width=260)
        for column in columns:
            self.list.heading(column, text=column.capitalize())
            self.list.column(column, width=100, anchor="center")
        self.list.pack(fill=tk.X, padx=8, pady=4)
        self.list.bind("<<TreeviewSelect>>", lambda _event: self.refresh())
        self.figure = Figure(figsize=(6, 4.5))
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.window)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.refresh()

    def refresh(self):
        if not self.window.winfo_exists():
            return
        monitor = self.app.indices
        names = [definition["name"] for definition in monitor.definitions]
        selected = self.list.selection()
        selected = selected[0] if selected and selected[0] in names else (names[0] if names else None)
        if list(self.list.get_children()) != names:
            self.list.delete(*self.list.get_children())
            for name in names:
                self.list.insert("", tk.END, iid=name, text=name)
        for definition in monitor.definitions:
            value = monitor.compared(definition["name"])
            self.list.item(definition["name"], values=(
                definition["layer"], "-" if value is None else f"{value:.2f}",
                f"{definition['threshold']:g}", monitor.states[definition["name"]]))
        if selected is not None and self.list.selection() != (selected,):
            self.list.selection_set(selected)  # fires <<TreeviewSelect>>, which redraws
            return
        self._draw(next((d for d in monitor.definitions if d["name"] == selected), None))

    def _draw(self, definition):
        self.figure.clear()
        axes = self.figure.add_subplot()
        if definition is None:
            axes.set_title("No indices defined")
        elif definition["layer"] == "map":
            self._draw_map(axes, definition)
        else:
            self._draw_trend(axes, definition)
        self.canvas.draw_idle()

    def _draw_map(self, axes, definition):
        grid = self.app.indices.values[definition["name"]]
        if grid is None:
            axes.set_title(f"{definition['name']}: no pressure data")
            return
        finite = grid[np.isfinite(grid)]
        top = max(definition["threshold"], float(finite.max()) if finite.size else 0.0)
        image = axes.imshow(grid, cmap="viridis", vmin=0, vmax=top, aspect="auto")
        self.figure.colorbar(image, ax=axes, label="Index value")
        if finite.size and finite.min() < definition["threshold"] <= finite.max():
            axes.contour(np.where(np.isfinite(grid), grid, 0.0), levels=[definition["threshold"]],
                         colors="white", linewidths=1.0, linestyles="dashed")
        axes.set_title(f"{definition['name']} (dashed line: threshold {definition['threshold']:g})")

    def _draw_trend(self, axes, definition):
        history = self.app.index_history.get(definition["name"], ())
        if history:
            start = history[0][0]
            axes.plot([time - start for time, _value in history], [value for _time, value in history],
                      color="green")
        threshold = definition["threshold"]
        axes.axhline(threshold, color="#bd5555", linestyle="dashed", label="Threshold")
        axes.axhline(threshold * definition["near_fraction"], color="#e8b04e", linestyle="dotted",
                     label="Near")
        axes.set_ylim(bottom=0)
        axes.set_xlabel("Time (s)")
        axes.set_ylabel("Index value")
        axes.set_title(definition["name"] if history else f"{definition['name']}: no values yet")
        axes.legend(loc="upper left", fontsize=8)
```

- [ ] **Step 4: Run everything** - `python -m unittest discover -s tests -v` -> 108 tests, OK.

---

### Task 7: Editor tab in the Engineering window

**Files:**
- Create: `gui/index_editor.py`
- Modify: `gui/engineering_window.py`
- Test: `tests/test_indices.py`

**Interfaces:**
- Consumes: `SIGNALS`, `WINDOWS_MIN`, `REDUCERS`, `REGIONS`, `validate_indices`; `app.current_settings()["indices"]`, `app.apply_engineering_settings(settings, preset_name)`.
- Produces: `IndexEditor(parent, definitions)` with `set_definitions(definitions)`, `get_definitions()` (validated; raises `ValueError`), `status_var`; methods `_add_index(layer)`, `_delete_index()`, `_select(position)`, `_add_term()`, `_remove_term()` and the form variables `name_var`, `threshold_var`, `near_var`, `input_var`, `window_var`, `reducer_var`, `reducer_value_var`, `region_var`, `reference_var`, `weight_var`, `inverted_var`. `EngineeringWindow.index_editor`.

- [ ] **Step 1: Write the failing test** - add to `DesktopIndexTests`:

```python
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
```

(`HOTSPOT_ACTIVATE_KPA` is 20.0 in `config.py`, hence the 20.0.)

- [ ] **Step 2: Run, expect failure** - `AttributeError: 'EngineeringWindow' object has no attribute 'index_editor'`.

- [ ] **Step 3: Implement the editor** - `gui/index_editor.py`:

```python
"""Table editor for user-defined index definitions (Engineering window > Indices)."""

import copy
import tkinter as tk
from tkinter import ttk

from processing.indices import REDUCERS, REGIONS, validate_indices
from processing.signals import SIGNALS, WINDOWS_MIN

SOURCE_PREFIX = "index: "
TERM_COLUMNS = ("input", "window", "reducer", "region", "reference", "weight", "inverted")


def _window_text(minutes):
    return "Session" if minutes is None else f"{minutes} min"


class IndexEditor:
    def __init__(self, parent, definitions):
        self.definitions = []
        self.current = None  # position of the index being edited
        self.status_var = tk.StringVar()

        left = ttk.Frame(parent)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.index_list = tk.Listbox(left, height=12, width=26, exportselection=False)
        self.index_list.pack(fill=tk.Y, expand=True)
        self.index_list.bind("<<ListboxSelect>>", lambda _event: self._list_clicked())
        for text, command in (("New map index", lambda: self._add_index("map")),
                              ("New summary index", lambda: self._add_index("summary")),
                              ("Delete index", self._delete_index)):
            ttk.Button(left, text=text, command=command).pack(fill=tk.X, pady=2)

        right = ttk.Frame(parent)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        header = ttk.Frame(right)
        header.pack(fill=tk.X)
        self.name_var, self.threshold_var, self.near_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.layer_var = tk.StringVar()
        for label, variable, width in (("Name", self.name_var, 22), ("Threshold", self.threshold_var, 7),
                                       ("Near margin (0-1)", self.near_var, 7)):
            ttk.Label(header, text=label).pack(side=tk.LEFT)
            ttk.Entry(header, textvariable=variable, width=width).pack(side=tk.LEFT, padx=(3, 10))
        ttk.Label(header, textvariable=self.layer_var).pack(side=tk.LEFT)

        self.terms = ttk.Treeview(right, columns=TERM_COLUMNS, show="headings", height=6)
        for column, width in zip(TERM_COLUMNS, (190, 70, 105, 55, 80, 60, 65)):
            self.terms.heading(column, text=column.capitalize())
            self.terms.column(column, width=width, anchor="center")
        self.terms.pack(fill=tk.X, pady=6)

        form = ttk.Frame(right)
        form.pack(fill=tk.X)
        self.input_var, self.window_var = tk.StringVar(), tk.StringVar(value="Session")
        self.reducer_var, self.region_var = tk.StringVar(value="peak"), tk.StringVar(value="mat")
        self.reducer_value_var = tk.StringVar(value="1.0")
        self.reference_var, self.weight_var = tk.StringVar(), tk.StringVar(value="1.0")
        self.inverted_var = tk.BooleanVar(value=False)
        self.input_menu = ttk.Combobox(form, textvariable=self.input_var, state="readonly", width=24)
        self.input_menu.bind("<<ComboboxSelected>>", lambda _event: self._input_chosen())
        widgets = (
            ("Signal / map index", self.input_menu),
            ("Window", ttk.Combobox(form, textvariable=self.window_var, state="readonly", width=9,
                                    values=[_window_text(minutes) for minutes in WINDOWS_MIN])),
            ("Reduce by (summary)", ttk.Combobox(form, textvariable=self.reducer_var, state="readonly",
                                                 width=14, values=REDUCERS)),
            ("Fraction above", ttk.Entry(form, textvariable=self.reducer_value_var, width=7)),
            ("Over", ttk.Combobox(form, textvariable=self.region_var, state="readonly", width=6,
                                  values=REGIONS)),
            ("Reference (= 1.0)", ttk.Entry(form, textvariable=self.reference_var, width=9)),
            ("Weight", ttk.Entry(form, textvariable=self.weight_var, width=6)),
        )
        for row, (label, widget) in enumerate(widgets):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
            widget.grid(row=row, column=1, sticky="w", padx=6)
        ttk.Checkbutton(form, text="Inverted (more of this lowers the index)",
                        variable=self.inverted_var).grid(row=len(widgets), column=0, columnspan=2, sticky="w")
        buttons = ttk.Frame(right)
        buttons.pack(fill=tk.X, pady=6)
        ttk.Button(buttons, text="Add term", command=self._add_term).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Remove selected term", command=self._remove_term).pack(side=tk.LEFT, padx=6)
        ttk.Label(right, textvariable=self.status_var, wraplength=560).pack(fill=tk.X)
        self.set_definitions(definitions)

    # ---- whole set

    def set_definitions(self, definitions):
        self.definitions = copy.deepcopy(definitions)
        self.current = None
        self._refresh_list()
        self._select(0 if self.definitions else None)

    def get_definitions(self):
        """The edited definitions, validated (raises ValueError naming the index)"""
        self._store_header()
        return validate_indices(self.definitions)

    # ---- index list

    def _refresh_list(self):
        self.index_list.delete(0, tk.END)
        for definition in self.definitions:
            self.index_list.insert(tk.END, f"{definition['name']}  [{definition['layer']}]")

    def _list_clicked(self):
        chosen = self.index_list.curselection()
        if chosen and chosen[0] != self.current:
            self._store_header()
            self._refresh_list()
            self._select(chosen[0])

    def _store_header(self):
        if self.current is not None:
            self.definitions[self.current].update(
                name=self.name_var.get().strip(), threshold=self.threshold_var.get(),
                near_fraction=self.near_var.get())

    def _select(self, position):
        self.current = position
        self.terms.delete(*self.terms.get_children())
        if position is None:
            for variable in (self.name_var, self.threshold_var, self.near_var, self.layer_var):
                variable.set("")
            self.input_menu.configure(values=[])
            return
        definition = self.definitions[position]
        self.index_list.selection_clear(0, tk.END)
        self.index_list.selection_set(position)
        self.name_var.set(definition["name"])
        self.threshold_var.set(str(definition["threshold"]))
        self.near_var.set(str(definition["near_fraction"]))
        self.layer_var.set(f"Layer: {definition['layer']}")
        for term in definition["terms"]:
            self.terms.insert("", tk.END, values=self._term_row(term))
        if definition["layer"] == "map":
            choices = [name for name, signal in SIGNALS.items() if signal.level == "cell"]
        else:
            choices = list(SIGNALS) + [SOURCE_PREFIX + item["name"] for item in self.definitions
                                       if item["layer"] == "map"]
        self.input_menu.configure(values=choices)
        self.input_var.set(choices[0])
        self._input_chosen()

    def _add_index(self, layer):
        self._store_header()
        taken = {definition["name"] for definition in self.definitions}
        name = next(f"New {layer} index {number}" for number in range(1, len(taken) + 2)
                    if f"New {layer} index {number}" not in taken)
        self.definitions.append({"name": name, "layer": layer, "threshold": 1.0,
                                 "near_fraction": 0.8, "terms": []})
        self._refresh_list()
        self._select(len(self.definitions) - 1)

    def _delete_index(self):
        if self.current is None:
            return
        del self.definitions[self.current]
        self.current = None
        self._refresh_list()
        self._select(0 if self.definitions else None)

    # ---- terms of the selected index

    @staticmethod
    def _term_row(term):
        return (SOURCE_PREFIX + term["source"] if "source" in term else term["signal"],
                "-" if "source" in term else _window_text(term.get("window_min")),
                term.get("reducer", "-") + (f" > {term['reducer_value']:g}" if "reducer_value" in term else ""),
                term.get("region", "-"), f"{float(term['reference']):g}", f"{float(term['weight']):g}",
                "yes" if term.get("inverted") else "no")

    def _input_chosen(self):
        """Pre-fill the reference with the signal's default"""
        choice = self.input_var.get()
        self.reference_var.set("1.0" if choice.startswith(SOURCE_PREFIX) else f"{SIGNALS[choice].reference:g}")
        if choice.startswith(SOURCE_PREFIX) or not SIGNALS[choice].windowed:
            self.window_var.set("Session")

    def _add_term(self):
        if self.current is None:
            self.status_var.set("Create or select an index first")
            return
        definition = self.definitions[self.current]
        choice = self.input_var.get()
        try:
            term = {"reference": float(self.reference_var.get()), "weight": float(self.weight_var.get()),
                    "inverted": self.inverted_var.get()}
            if choice.startswith(SOURCE_PREFIX):
                term["source"] = choice[len(SOURCE_PREFIX):]
                reduced = True
            else:
                text = self.window_var.get()
                term["signal"] = choice
                term["window_min"] = (None if text == "Session" or not SIGNALS[choice].windowed
                                      else int(text.split()[0]))
                reduced = definition["layer"] == "summary" and SIGNALS[choice].level == "cell"
            if reduced:
                term.update(reducer=self.reducer_var.get(), region=self.region_var.get())
                if term["reducer"] == "fraction_above":
                    term["reducer_value"] = float(self.reducer_value_var.get())
        except ValueError:
            self.status_var.set("Reference, weight and fraction-above value must be numbers")
            return
        definition["terms"].append(term)
        self.terms.insert("", tk.END, values=self._term_row(term))
        self.status_var.set("Term added; choose Apply values to use the new definitions")

    def _remove_term(self):
        chosen = self.terms.selection()
        if self.current is None or not chosen:
            return
        del self.definitions[self.current]["terms"][self.terms.index(chosen[0])]
        self.terms.delete(chosen[0])
```

- [ ] **Step 4: Host it** in `gui/engineering_window.py`:
  - Import: `from gui.index_editor import IndexEditor`.
  - In `__init__`, add `indices_tab = ttk.Frame(tabs, padding=8)` with the other tab frames, add `(indices_tab, "Indices")` to the tuple right after `(settings_tab, "Thresholds & presets")`, and after `self._build_settings(settings_tab)`:

```python
        ttk.Label(indices_tab, wraplength=800, text=(
            "Combine signals into your own indices. Each term is divided by its reference, so 1.0 means "
            "\"at the reference\"; the index is the weighted average of its terms. Use Apply values on the "
            "Thresholds & presets tab to put changes into effect.")).pack(fill=tk.X, pady=(0, 8))
        self.index_editor = IndexEditor(indices_tab, self.app.indices.definitions)
```

  - In `_form_settings`, before `return validate_settings(settings)`: `settings["indices"] = self.index_editor.get_definitions()`.
  - In `_show_settings`, at the end:

```python
        if "indices" in settings:
            self.index_editor.set_definitions(settings["indices"])
```

- [ ] **Step 5: Run everything** - `python -m unittest discover -s tests -v` -> 109 tests, OK.

---

### Task 8: Docs

**Files:**
- Modify: `Raspberry Pi/STATUS.md`, `Raspberry Pi/notes.md`, `Raspberry Pi/README.md`

- [ ] **Step 1:** `STATUS.md`: add `signals.py` and `indices.py` to the `processing/` file map and `indices_window.py`, `index_editor.py` to `gui/`; change the design-doc entry to "built" with a link to this plan.
- [ ] **Step 2:** `notes.md`: replace the two "larger design passes" bullets (near-threshold warning, composable weighted functions) with one line saying they are built as custom indices, what is not included (main Data dropdown, sound, web UI), and that all reference values are untuned placeholders.
- [ ] **Step 3:** `README.md`: one sentence under "First run" pointing at **Indices...** and Engineering > Indices, and one sentence in "Not a medical device" that custom indices are user-defined and unvalidated.
- [ ] **Step 4: Final run** - `python -m unittest discover -s tests -v` -> 109 tests, OK. Then start the app (`python main.py`), connect the Simulated source, open **Indices...** and Engineering > Indices, and confirm the chips, heatmap, trend and editor behave as described.
