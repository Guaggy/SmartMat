"""Small shared pieces used by more than one part of the program"""

import json
import threading
from collections import deque
from pathlib import Path
import numpy as np

import config
from config import VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT

def parse_frame_text(text):
    """Convert comma-separated frame into grid (None if invalid)"""
    return parse_frame_text_with_reason(text)[0]


def parse_frame_text_with_reason(text):
    """Return a grid and a packet-level rejection reason."""

    text = text.strip()
    if text.endswith(","):
        text = text[:-1]

    pieces = text.split(",")
    if len(pieces) != config.TOTAL_ROWS * config.TOTAL_COLS:
        return None, "grid_size"
    # Check if  empty cells
    if any(piece.strip() == "" for piece in pieces):
        return None, "malformed"

    # Convert to array of float numbers
    try:
        values = np.asarray([float(piece) for piece in pieces], dtype=float)
    except ValueError:
        return None, "malformed"

    # Check if data is valid
    if not np.all(np.isfinite(values)):
        return None, "malformed"
    if np.any(values < VALUE_MIN_DEFAULT) or np.any(values > VALUE_MAX_DEFAULT):
        return None, "out_of_range"

    grid = values.reshape(config.TOTAL_ROWS, config.TOTAL_COLS)
    return grid, None


MATS_FILE = Path(__file__).resolve().parent / "mats.json"  # local nicknames, not in git


def load_mat_names(path=MATS_FILE):
    """Nicknames for MQTT mats as {chip_id: nickname}; empty if there is no usable file"""
    try:
        with open(path, encoding="utf-8") as file:
            names = json.load(file)
    except (OSError, ValueError):
        return {}
    if not isinstance(names, dict):
        return {}
    return {str(chip_id): str(name) for chip_id, name in names.items()}


def save_mat_names(names, path=MATS_FILE):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(names, file, indent=2)


def mat_labels(chip_ids, names):
    """Device-list label -> chip id: the nickname if the mat has one, else the raw chip id"""
    labels = {}
    for chip_id in sorted(chip_ids):
        label = names.get(chip_id) or chip_id
        if label in labels:  # two mats given the same nickname
            label = f"{label} ({chip_id})"
        labels[label] = chip_id
    return labels

# Needed for multithreading
class LatestFrame:
    """Holds the newest grid from a background thread"""

    def __init__(self):
        self._lock = threading.Lock()
        self._grid = None

    def set(self, grid):
        with self._lock:
            replaced = self._grid is not None
            self._grid = grid
            return replaced

    def take(self):
        """Return the newest grid and clear it, or None if nothing is new"""
        with self._lock:
            grid, self._grid = self._grid, None
            return grid


class QueuedFrames:
    """Keep every playback sample until the GUI can process it."""

    def __init__(self):
        self._lock = threading.Lock()
        self._samples = deque()

    def set(self, sample):
        with self._lock:
            self._samples.append(sample)

    def take_all(self):
        with self._lock:
            samples = list(self._samples)
            self._samples.clear()
            return samples
