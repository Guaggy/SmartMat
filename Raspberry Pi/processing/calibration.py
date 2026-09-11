"""Controls the heatmap's display range and an optional baseline correction"""

import numpy as np

from config import VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT

class Calibration:
    """Display range, plus an optional baseline grid subtracted from future frames"""

    def __init__(self):
        self.auto = False
        self.vmin = VALUE_MIN_DEFAULT
        self.vmax = VALUE_MAX_DEFAULT
        self.baseline = None

    def apply_baseline(self, grid):
        """Subtract the captured baseline (if any), clamped back into range."""
        if self.baseline is None:
            return grid
        return np.clip(grid - self.baseline, VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT)

    def capture_baseline(self, grid):
        """Calibrate button: remember this (pre-baseline) reading as the new zero point."""
        self.baseline = grid.copy()

    def update(self, grid):
        """Call once per new (already baseline-corrected) frame"""
        if not self.auto:
            return
        lowest = float(grid.min())
        highest = float(grid.max())
        if lowest < highest:
            self.vmin, self.vmax = lowest, highest

    def toggle_auto(self):
        self.auto = not self.auto

    def reset(self):
        """Reset button. Back to the default fixed range, no baseline"""
        self.auto = False
        self.vmin = VALUE_MIN_DEFAULT
        self.vmax = VALUE_MAX_DEFAULT
        self.baseline = None
