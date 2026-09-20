"""Packet-level source diagnostics shared by live sources."""

import threading
import time
from collections import deque


class SourceQuality:
    def __init__(self):
        self._lock = threading.Lock()
        self.received = 0
        self.valid = 0
        self.malformed = 0
        self.dropped = 0
        self.missing_timestamps = 0
        self.unexpected_grid_size = 0
        self.out_of_range = 0
        self.last_valid = None
        self.first_valid = None
        self.longest_arrival_gap_s = 0.0
        self._recent = deque()

    def packet(self, reason=None, timestamp=True):
        now = time.monotonic()
        with self._lock:
            self.received += 1
            if not timestamp:
                self.missing_timestamps += 1
            if reason is None:
                self.valid += 1
                if self.first_valid is None:
                    self.first_valid = now
                if self.last_valid is not None:
                    self.longest_arrival_gap_s = max(self.longest_arrival_gap_s, now - self.last_valid)
                self.last_valid = now
                self._recent.append(now)
            else:
                self.malformed += 1
                if reason == "grid_size":
                    self.unexpected_grid_size += 1
                elif reason == "out_of_range":
                    self.out_of_range += 1
            self._trim(now)

    def drop(self, count=1):
        with self._lock:
            self.dropped += count

    def _trim(self, now):
        while self._recent and self._recent[0] < now - 10:
            self._recent.popleft()

    def snapshot(self):
        now = time.monotonic()
        with self._lock:
            self._trim(now)
            return {
                "received": self.received, "valid": self.valid,
                "malformed": self.malformed, "dropped": self.dropped,
                "missing_timestamps": self.missing_timestamps,
                "unexpected_grid_size": self.unexpected_grid_size,
                "out_of_range": self.out_of_range,
                "rate_hz": len(self._recent) / 10,
                "age_s": None if self.last_valid is None else now - self.last_valid,
                "session_duration_s": 0.0 if self.first_valid is None else now - self.first_valid,
                "longest_arrival_gap_s": self.longest_arrival_gap_s,
                "average_rate_hz": 0.0 if self.first_valid is None or now == self.first_valid else
                                   self.valid / (now - self.first_valid),
            }
