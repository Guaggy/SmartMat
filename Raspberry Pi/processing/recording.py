"""Recording and loading of named sessions, saved as CSV (one row per frame)"""

import csv
import time
from pathlib import Path

import numpy as np

from config import TOTAL_ROWS, TOTAL_COLS

RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "recordings"

class Recorder:
    """Collects grids for one named session until stopped"""

    def __init__(self, name):
        self.name = name
        self.started_at = time.time()
        self._frames = []

    @property
    def frame_count(self):
        return len(self._frames)

    def add_frame(self, grid):
        self._frames.append(grid.flatten().tolist())

    def save(self):
        """Write the session to recordings/<name>_<timestamp>.csv"""
        RECORDINGS_DIR.mkdir(exist_ok=True)
        path = RECORDINGS_DIR / f"{self.name}_{int(time.time())}.csv"
        with open(path, "w", newline="") as file:
            csv.writer(file).writerows(self._frames)
        return path


def load_session(path):
    """Load a recorded sessions frames"""
    with open(path, newline="") as file:
        rows = list(csv.reader(file))
    return [np.asarray(row, dtype=float).reshape(TOTAL_ROWS, TOTAL_COLS) for row in rows]
