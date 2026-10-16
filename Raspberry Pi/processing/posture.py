"""Seated posture class and risk level from the oriented pressure grid (pure, no GUI).

Heuristics for testing the pipeline, not a clinical assessment. Grid convention (after
orientation): row 0 is the back of the seat and the last row is "forward" (the front edge); left/right are the SITTER'S
left and right (clinical convention): with the front at the bottom of the map the sitter faces the viewer-bottom, so column 0 is
the sitter's right (the Mirror H setting swaps it).
"""

import config
from processing.indices import NEAR, OVER
from processing.statistics import weighted_center

SIDE_CELLS = getattr(config, "POSTURE_SIDE_CELLS", 2.0)
FORWARD_CELLS = getattr(config, "POSTURE_FORWARD_CELLS", 2.5)
HOLD_S = getattr(config, "POSTURE_HOLD_S", 3.0)

RISK_ORDER = ("offline", "high", "medium", "low", "none")  # overview sort order, worst first


def classify_posture(pressure, occupied, threshold_kpa, side_cells=SIDE_CELLS, forward_cells=FORWARD_CELLS):
    """'left' / 'right' / 'forward' / 'centred' from the centre of pressure vs the mat centre; 'none' when empty"""
    if occupied is not True or pressure is None:
        return "none"
    x, y = weighted_center(pressure, threshold_kpa)
    if x is None:
        return "none"
    rows, cols = pressure.shape
    dx, dy = x - (cols - 1) / 2, y - (rows - 1) / 2
    if abs(dx) > side_cells:
        return "right" if dx < 0 else "left"  # column 0 is the sitter's right
    return "forward" if dy > forward_cells else "centred"


class PostureTracker:
    """Debounced posture: a new class must hold for hold_s; time in position counts from the last change
    (or a detected reposition)"""

    def __init__(self, hold_s=HOLD_S):
        self.hold_s = hold_s
        self.posture = None      # debounced class, None before the first frame
        self.changed_at = None
        self._candidate = None
        self._candidate_since = None

    def update(self, posture, t, reposition=False):
        if self.posture is None:
            self.posture, self.changed_at = posture, t
        elif posture == self.posture:
            self._candidate = None
        elif posture != self._candidate:
            self._candidate, self._candidate_since = posture, t
        elif t - self._candidate_since >= self.hold_s:
            self.posture, self.changed_at, self._candidate = posture, t, None
        if reposition:
            self.changed_at = t
        return self.posture

    def time_in_position(self, t):
        """Seconds in the current posture (for "none": how long nobody has been on the mat), None before any frame"""
        if self.posture is None:
            return None
        return max(0.0, t - self.changed_at)


def risk_from(index_states, occupied, online):
    """Worst summary-index state as a risk level: over -> high, near -> medium, else low"""
    if not online:
        return "offline"
    if occupied is not True:
        return "none"
    states = set(index_states)
    return "high" if OVER in states else "medium" if NEAR in states else "low"


def risk_sort_key(row):
    """Overview order: offline, high, medium, low, none; ties by longest time in position"""
    return RISK_ORDER.index(row["risk"]), -(row.get("time_in_position_s") or 0)
