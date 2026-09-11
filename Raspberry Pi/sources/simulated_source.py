"""Fake/recorded data source for testing the app without real hardware"""

import threading
import time

import numpy as np

from general import LatestFrame
from config import TOTAL_ROWS, TOTAL_COLS, VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT

FRAME_INTERVAL_S = 0.1  # matches the ESP32 10fps

# [[0],[1],[2],...] and [[0,1,2,...]] - broadcast together into a full grid of coordinates
_ROWS = np.arange(TOTAL_ROWS).reshape(-1, 1)
_COLS = np.arange(TOTAL_COLS).reshape(1, -1)


def _blob(center_row, center_col, spread, amplitude):
    """One soft pressure blob centered at (center_row, center_col)."""
    distance_sq = (_ROWS - center_row) ** 2 + (_COLS - center_col) ** 2
    return amplitude * np.exp(-distance_sq / spread)


def _with_noise(grid, amount=30):
    noise = np.random.uniform(0, amount, size=grid.shape)
    return np.clip(grid + noise, VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT)


def _drifting_blob(elapsed_seconds):
    """A single soft blob drifting in a circle."""
    center_row = TOTAL_ROWS / 2 + (TOTAL_ROWS / 3) * np.sin(elapsed_seconds * 0.5)
    center_col = TOTAL_COLS / 2 + (TOTAL_COLS / 3) * np.cos(elapsed_seconds * 0.5)
    return _with_noise(_blob(center_row, center_col, 8, VALUE_MAX_DEFAULT))


def _bad_distribution(elapsed_seconds):
    """A small, sharp, static hotspot - concentrated pressure in one place."""
    return _with_noise(_blob(TOTAL_ROWS * 0.3, TOTAL_COLS * 0.5, 2, VALUE_MAX_DEFAULT))


def _good_distribution(elapsed_seconds):
    """A wide, gentle plateau spread across most of the mat."""
    return _with_noise(_blob(TOTAL_ROWS / 2, TOTAL_COLS / 2, 60, VALUE_MAX_DEFAULT * 0.5), amount=15)


def _hand(elapsed_seconds):
    """A palm plus four fingertips - a rough hand-press shape."""
    palm = _blob(TOTAL_ROWS * 0.65, TOTAL_COLS * 0.5, 6, VALUE_MAX_DEFAULT * 0.8)
    fingers = sum(
        _blob(TOTAL_ROWS * 0.25, TOTAL_COLS * (0.3 + 0.15 * i), 1.5, VALUE_MAX_DEFAULT * 0.6)
        for i in range(4)
    )
    return _with_noise(palm + fingers)


SCENARIOS = {
    "Drifting blob": _drifting_blob,
    "Bad distribution": _bad_distribution,
    "Good distribution": _good_distribution,
    "Hand": _hand,
}


class SimulatedSource:
    """Fake grids on a background thread: a named scenario, or a recording played back in a loop"""

    def __init__(self, playback_frames=None, scenario="Drifting blob"):
        self.latest = LatestFrame()
        self._playback_frames = playback_frames
        self._generate = SCENARIOS.get(scenario, _drifting_blob)
        self._running = False
        self._paused = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self):
        """Freeze exactly where the source is - a recording resumes at the next frame"""
        self._paused = True

    def resume(self):
        self._paused = False

    def _run(self):
        start_time = time.time()
        frame_index = 0
        while self._running:
            if not self._paused:
                if self._playback_frames:
                    grid = self._playback_frames[frame_index % len(self._playback_frames)]
                    frame_index += 1
                else:
                    grid = self._generate(time.time() - start_time)
                self.latest.set(grid)
            time.sleep(FRAME_INTERVAL_S)

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1)
