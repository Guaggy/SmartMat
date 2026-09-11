"""Small shared pieces used by more than one part of the program"""

import threading
import numpy as np

from config import TOTAL_ROWS, TOTAL_COLS, VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT

def parse_frame_text(text):
    """Convert comma-separated frame into grid (None if invalid)"""

    text = text.strip()
    if text.endswith(","):
        text = text[:-1]

    pieces = text.split(",")
    if len(pieces) != TOTAL_ROWS * TOTAL_COLS:
        return None
    # Check if  empty cells
    if any(piece.strip() == "" for piece in pieces):
        return None

    # Convert to array of float numbers
    try:
        values = np.asarray([float(piece) for piece in pieces], dtype=float)
    except ValueError:
        return None

    # Check if data is valid
    if not np.all(np.isfinite(values)):
        return None
    if np.any(values < VALUE_MIN_DEFAULT) or np.any(values > VALUE_MAX_DEFAULT):
        return None

    grid = values.reshape(TOTAL_ROWS, TOTAL_COLS)
    return grid

# Needed for multithreading
class LatestFrame:
    """Holds the newest grid from a background thread"""

    def __init__(self):
        self._lock = threading.Lock()
        self._grid = None

    def set(self, grid):
        with self._lock:
            self._grid = grid

    def take(self):
        """Return the newest grid and clear it, or None if nothing is new"""
        with self._lock:
            grid, self._grid = self._grid, None
            return grid
