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
