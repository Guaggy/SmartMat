"""Processing modes applied to each new grid before tare and pressure conversion.
Each has at most one adjustable parameter, so the GUI can show one generic field.
"""

from collections import deque

import numpy as np


class LiveMode:
    """No processing - the raw frame as-is."""

    label = "Live"
    param_label = None
    param_default = None

    def reset(self):
        pass

    def set_param(self, value):
        pass

    def apply(self, grid):
        return grid


class AverageMode:
    """Rolling average over the last `period` frames."""

    label = "Average"
    param_label = "Period (frames)"
    param_default = 5

    def __init__(self):
        self.period = self.param_default
        self._history = deque(maxlen=self.period)

    def set_param(self, value):
        self.period = max(1, int(value))
        self._history = deque(self._history, maxlen=self.period)

    def reset(self):
        self._history.clear()

    def apply(self, grid):
        self._history.append(grid)
        values = np.asarray(self._history)
        valid = np.isfinite(values)
        totals = np.where(valid, values, 0).sum(axis=0)
        count = valid.sum(axis=0)
        return np.divide(totals, count, out=np.full_like(grid, np.nan), where=count > 0)


class ExponentialAverageMode:
    """Exponential moving average, like the ESP32 firmware's own smoothing"""

    label = "Exponential average"
    param_label = "Smoothing (0-1)"
    param_default = 0.7

    def __init__(self):
        self.smoothing = self.param_default
        self._previous = None

    def set_param(self, value):
        self.smoothing = float(value)

    def reset(self):
        self._previous = None

    def apply(self, grid):
        if self._previous is None:
            self._previous = grid.copy()
        else:
            blended = self.smoothing * self._previous + (1 - self.smoothing) * grid
            self._previous = np.where(np.isfinite(grid),
                                      np.where(np.isfinite(self._previous), blended, grid), np.nan)
        return self._previous


MODES = [LiveMode(), AverageMode(), ExponentialAverageMode()]
