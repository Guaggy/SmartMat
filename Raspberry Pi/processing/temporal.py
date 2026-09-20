"""Incremental pressure-time exposure, experimental burden, and relief."""

from collections import deque
import math

import numpy as np

from config import (
    TOTAL_ROWS, TOTAL_COLS, TEMPORAL_MAX_GAP_S, TEMPORAL_BUCKET_S,
    EXPOSURE_THRESHOLD_KPA, EXPOSURE_MODE, BURDEN_LOAD_THRESHOLD_KPA,
    BURDEN_ACCUMULATION_RATE, BURDEN_RECOVERY_TIME_S,
    RELIEF_PARTIAL_RATIO, RELIEF_FULL_RATIO, RELIEF_MIN_DURATION_S,
    ROI_RELIEF_FRACTION, TEMPORAL_WINDOWS_MIN,
)

UNKNOWN, LOADED, PARTIAL, FULL = 0, 1, 2, 3
RELIEF_NAMES = ("Unknown", "Loaded", "Partial relief", "Full relief")
WINDOWS_MIN = TEMPORAL_WINDOWS_MIN


class TemporalAnalysis:
    def __init__(self):
        self.exposure_mode = EXPOSURE_MODE
        self.exposure_threshold_kpa = EXPOSURE_THRESHOLD_KPA
        self.burden_load_threshold_kpa = BURDEN_LOAD_THRESHOLD_KPA
        self.burden_accumulation_rate = BURDEN_ACCUMULATION_RATE
        self.burden_recovery_time_s = BURDEN_RECOVERY_TIME_S
        self.relief_partial_ratio = RELIEF_PARTIAL_RATIO
        self.relief_full_ratio = RELIEF_FULL_RATIO
        self.relief_min_duration_s = RELIEF_MIN_DURATION_S
        self.roi_relief_fraction = ROI_RELIEF_FRACTION
        self.max_gap_s = TEMPORAL_MAX_GAP_S
        self.bucket_s = TEMPORAL_BUCKET_S
        self.reset_all()

    def settings(self):
        return {name: getattr(self, name) for name in (
            "exposure_mode", "exposure_threshold_kpa", "burden_load_threshold_kpa",
            "burden_accumulation_rate", "burden_recovery_time_s",
            "relief_partial_ratio", "relief_full_ratio", "relief_min_duration_s",
            "roi_relief_fraction",
            "max_gap_s", "bucket_s",
        )}

    def reset_all(self):
        shape = (TOTAL_ROWS, TOTAL_COLS)
        self.exposure = np.zeros(shape)
        self.burden = np.zeros(shape)
        self.state = np.zeros(shape, dtype=np.uint8)
        self._candidate = np.zeros(shape, dtype=np.uint8)
        self._candidate_since = np.full(shape, np.nan)
        self._peak = np.zeros(shape)
        self.last_full_relief = np.full(shape, np.nan)
        self.full_relief_started = np.full(shape, np.nan)
        self.loaded_s = np.zeros(shape)
        self.relieved_s = np.zeros(shape)
        self.valid_s = np.zeros(shape)
        self.last_time = None
        self.last_pressure = None
        self.valid_intervals = 0
        self.skipped_intervals = 0
        self._buckets = deque(maxlen=max(1, math.ceil(3600 / self.bucket_s)))
        self.mat_full_relief = False
        self.last_event = None
        self._roi_bounds = None
        self._roi_last_relief = None

    def reset_exposure(self):
        self.exposure.fill(0)
        for _bucket_id, exposure, _relieved, _valid in self._buckets:
            exposure.fill(0)

    def reset_burden(self):
        self.burden.fill(0)

    def clear_roi(self):
        self._roi_bounds = None
        self._roi_last_relief = None

    def invalidate(self):
        # A missing or malformed sample breaks the integration interval.
        self.last_time = None
        self.last_pressure = None
        self.state.fill(UNKNOWN)
        self._candidate.fill(UNKNOWN)
        self._candidate_since.fill(np.nan)
        self.full_relief_started.fill(np.nan)
        self.mat_full_relief = False

    def _bucket(self, timestamp):
        bucket_id = math.floor(timestamp / self.bucket_s)
        if not self._buckets or self._buckets[-1][0] != bucket_id:
            zero = np.zeros_like(self.exposure)
            self._buckets.append((bucket_id, zero.copy(), zero.copy(), zero.copy()))
        return self._buckets[-1]

    def update(self, pressure, timestamp):
        self.last_event = None
        if pressure is None or timestamp is None or not math.isfinite(timestamp):
            self.invalidate()
            return
        values = np.asarray(pressure, dtype=float)
        if values.shape != self.exposure.shape:
            self.invalidate()
            return
        if self.last_time is None:
            self.last_time = float(timestamp)
            self.last_pressure = values.copy()
            self._update_relief(values, timestamp, np.zeros_like(values, dtype=bool))
            return
        dt = float(timestamp) - self.last_time
        previous = self.last_pressure
        self.last_time = float(timestamp)
        self.last_pressure = values.copy()
        if dt <= 0 or dt > self.max_gap_s:
            self.skipped_intervals += 1
            self.state.fill(UNKNOWN)
            self._candidate.fill(UNKNOWN)
            self._candidate_since.fill(np.nan)
            self.full_relief_started.fill(np.nan)
            self.mat_full_relief = False
            return
        valid = np.isfinite(previous) & np.isfinite(values)
        if not np.any(valid):
            return
        self.valid_intervals += 1
        average = (np.where(valid, previous, 0) + np.where(valid, values, 0)) / 2
        if self.exposure_mode == "Above threshold":
            exposure_pressure = np.maximum(0, average - self.exposure_threshold_kpa)
        else:
            exposure_pressure = np.maximum(0, average)
        increment = np.where(valid, exposure_pressure * dt / 60, 0)
        self.exposure += increment
        load = np.maximum(0, average - self.burden_load_threshold_kpa)
        decay = math.exp(-dt / max(self.burden_recovery_time_s, 0.001))
        next_burden = self.burden * decay + load * self.burden_accumulation_rate * dt / 60
        self.burden[valid] = np.maximum(0, next_burden[valid])
        self.valid_s[valid] += dt
        previous_state = self.state.copy()
        self._update_relief(values, timestamp, valid)
        previously_loaded = self._peak > max(self.burden_load_threshold_kpa, 0)
        full = bool(np.any(previously_loaded) and np.all(self.state[previously_loaded] == FULL))
        if full != self.mat_full_relief:
            self.last_event = "full_relief_started" if full else "full_relief_ended"
            self.mat_full_relief = full
        if self._roi_bounds is not None:
            row0, row1, col0, col1 = self._roi_bounds
            area = self.state[row0:row1 + 1, col0:col1 + 1]
            if np.count_nonzero(area == FULL) >= area.size * self.roi_relief_fraction:
                self._roi_last_relief = timestamp
        self.loaded_s[valid & (previous_state == LOADED)] += dt
        self.relieved_s[valid & (previous_state == FULL)] += dt
        _, bucket_exposure, bucket_relief, bucket_valid = self._bucket(timestamp)
        bucket_exposure += increment
        bucket_relief[valid & (previous_state == FULL)] += dt
        bucket_valid[valid] += dt

    def _update_relief(self, values, timestamp, valid):
        finite = np.isfinite(values)
        self._peak[finite] = np.maximum(self._peak[finite], values[finite])
        eligible = finite & (self._peak > max(self.burden_load_threshold_kpa, 0))
        desired = np.full(self.state.shape, UNKNOWN, dtype=np.uint8)
        desired[eligible] = LOADED
        desired[eligible & (values <= self.relief_partial_ratio * self._peak)] = PARTIAL
        desired[eligible & (values <= self.relief_full_ratio * self._peak)] = FULL
        changed = finite & (desired != self._candidate)
        self._candidate[changed] = desired[changed]
        self._candidate_since[changed] = timestamp
        ready = valid & (desired != self.state) & (desired == LOADED)
        relief_ready = valid & (desired != self.state) & (desired != LOADED)
        relief_ready &= (timestamp - self._candidate_since >= self.relief_min_duration_s)
        ready |= relief_ready
        ending = ready & (self.state == FULL)
        starting = ready & (desired == FULL)
        self.last_full_relief[ending] = timestamp
        self.full_relief_started[ending] = np.nan
        self.full_relief_started[starting] = timestamp
        self.state[ready] = desired[ready]

    def rolling(self, minutes=None):
        if minutes is None:
            return self.exposure.copy(), self.relieved_s.copy(), self.valid_s.copy()
        cutoff = math.floor((self.last_time or 0) / self.bucket_s) - math.ceil(minutes * 60 / self.bucket_s) + 1
        exposure = np.zeros_like(self.exposure)
        relieved = np.zeros_like(self.exposure)
        valid = np.zeros_like(self.exposure)
        for bucket_id, bucket_exposure, bucket_relief, bucket_valid in self._buckets:
            if bucket_id >= cutoff:
                exposure += bucket_exposure
                relieved += bucket_relief
                valid += bucket_valid
        return exposure, relieved, valid

    def relief_percent(self, minutes=None):
        _, relieved, valid = self.rolling(minutes)
        return np.divide(100 * relieved, valid, out=np.full_like(valid, np.nan), where=valid > 0)

    def time_since_relief(self):
        result = np.full_like(self.exposure, np.nan)
        if self.last_time is not None:
            known = np.isfinite(self.last_full_relief)
            result[known] = self.last_time - self.last_full_relief[known]
            result[self.state == FULL] = 0
        return result

    def cell(self, row, col):
        state = int(self.state[row, col])
        since = self.time_since_relief()[row, col]
        current = (self.last_time - self.full_relief_started[row, col]
                   if state == FULL and self.last_time is not None else 0)
        return {
            "exposure": float(self.exposure[row, col]),
            "burden": float(self.burden[row, col]),
            "state": RELIEF_NAMES[state], "state_code": state,
            "since_relief_s": float(since), "current_relief_s": float(current),
            "loaded_s": float(self.loaded_s[row, col]),
            "relieved_s": float(self.relieved_s[row, col]),
            "relief_percent": float(self.relief_percent()[row, col]),
        }

    def roi(self, bounds):
        if bounds != self._roi_bounds:
            self._roi_bounds = bounds
            self._roi_last_relief = None
        row0, row1, col0, col1 = bounds
        area = np.s_[row0:row1 + 1, col0:col1 + 1]
        states = self.state[area]
        count = states.size
        return {
            "mean_exposure": float(np.mean(self.exposure[area])),
            "max_exposure": float(np.max(self.exposure[area])),
            "mean_burden": float(np.mean(self.burden[area])),
            "max_burden": float(np.max(self.burden[area])),
            "loaded_fraction": float(np.count_nonzero(states == LOADED) / count),
            "relieved_fraction": float(np.count_nonzero(states == FULL) / count),
            "valid_fraction": float(np.count_nonzero(states != UNKNOWN) / count),
            "since_relief_s": (self.last_time - self._roi_last_relief
                               if self.last_time is not None and self._roi_last_relief is not None else math.nan),
        }
