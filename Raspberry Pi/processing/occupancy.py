"""Whether the mat is loaded enough, for long enough, to call it occupied."""

from config import OCCUPANCY_MIN_CELLS, OCCUPANCY_ENTER_S, OCCUPANCY_EXIT_S
from processing.statistics import contact_mask


class OccupancyDetector:
    """Contact-cell count with hold times; says nothing about what is on the mat"""

    def __init__(self):
        self.min_cells = OCCUPANCY_MIN_CELLS
        self.enter_s = OCCUPANCY_ENTER_S
        self.exit_s = OCCUPANCY_EXIT_S
        self.reset()

    def reset(self):
        self.occupied = None  # None = unknown (no usable pressure data)
        self._changing_since = None

    def update(self, pressure, timestamp, threshold_kpa):
        """Feed one calibrated-pressure frame; returns True, False or None (unknown)"""
        if pressure is None or timestamp is None:
            self.reset()
            return None
        loaded = int(contact_mask(pressure, threshold_kpa).sum()) >= self.min_cells
        if self.occupied is None or loaded == self.occupied:
            self.occupied = loaded
            self._changing_since = None
        elif self._changing_since is None or timestamp < self._changing_since:
            self._changing_since = timestamp  # also restarts when playback loops back
        elif timestamp - self._changing_since >= (self.enter_s if loaded else self.exit_s):
            self.occupied = loaded
            self._changing_since = None
        return self.occupied
