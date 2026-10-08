"""User-defined indices: weighted combinations of named signals, with a warning state.

Two fixed layers. A map index combines cell signals into a grid; a summary index combines
single numbers (whole-mat signals, or a reduction of a map index or cell signal) into one
number. These are engineering indices the user defines, not validated scores.
"""

import math

import numpy as np

from config import INDEX_WARNING_HOLD_S
from processing.signals import SIGNALS, WINDOWS_MIN, read_signal

REDUCERS = ("peak", "mean", "fraction_above")
REGIONS = ("mat", "roi")
INACTIVE, OK, NEAR, OVER = "inactive", "ok", "near", "over"


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
        grid = grid[roi]
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
