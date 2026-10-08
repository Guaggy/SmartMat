"""Bounded diagnostics from received sensor values."""

from collections import deque

import numpy as np

import config
from config import (
    VALUE_MIN_DEFAULT, VALUE_MAX_DEFAULT,
    HEALTH_WINDOW_FRAMES, HEALTH_UNLOADED_MAX, HEALTH_UNLOADED_DELTA,
    HEALTH_NOISE_STD, HEALTH_DRIFT_DELTA, HEALTH_DRIFT_MIN_S,
    HEALTH_SATURATION_MARGIN, HEALTH_SATURATION_FRAMES,
    HEALTH_STUCK_STD, HEALTH_STUCK_NEIGHBOR_STD, HEALTH_STUCK_FRAMES,
    HEALTH_INVALID_FRAMES,
)

HEALTH_STATES = ("Healthy", "Noisy", "Drifting", "Saturated", "Possible stuck",
                 "Missing", "Invalid", "Uncalibrated")


def _rolling_stats(values):
    valid = np.isfinite(values)
    count = valid.sum(axis=0)
    safe = np.where(valid, values, 0)
    mean = np.divide(safe.sum(axis=0), count, out=np.zeros_like(safe[0]), where=count > 0)
    variance = np.divide(((safe - mean) ** 2 * valid).sum(axis=0), count,
                         out=np.zeros_like(mean), where=count > 0)
    return count, mean, variance


class SensorHealth:
    def __init__(self):
        self.history = deque(maxlen=HEALTH_WINDOW_FRAMES)
        self.reset()

    def reset(self):
        self.history.clear()
        shape = (config.TOTAL_ROWS, config.TOTAL_COLS)
        self.current = np.full(shape, np.nan)
        self.mean = np.full(shape, np.nan)
        self.variance = np.full(shape, np.nan)
        self.noise = np.full(shape, np.nan)
        self.drift = np.full(shape, np.nan)
        self.baseline_offset = np.full(shape, np.nan)
        self.states = np.full(shape, 7, dtype=int)
        self.invalid_streak = np.zeros(shape, dtype=int)
        self.missing_streak = np.zeros(shape, dtype=int)
        self.saturation_streak = np.zeros(shape, dtype=int)
        self.reference_sum = np.zeros(shape)
        self.reference_count = np.zeros(shape, dtype=int)
        self.reference_time = np.full(shape, np.nan)
        self.calibrated = np.zeros(shape, dtype=bool)

    def update(self, raw, timestamp, baseline=None, pressure=None,
               contact_threshold_kpa=0, pressure_calibration=None):
        if raw.shape != (config.TOTAL_ROWS, config.TOTAL_COLS):
            raise ValueError("Sensor health grid size does not match configuration")
        self.current = raw.copy()
        finite = np.isfinite(raw)
        in_range = finite & (raw >= VALUE_MIN_DEFAULT) & (raw <= VALUE_MAX_DEFAULT)
        missing = ~finite
        invalid = finite & ~in_range
        self.missing_streak = np.where(missing, self.missing_streak + 1, 0)
        self.invalid_streak = np.where(invalid, self.invalid_streak + 1, 0)
        saturated = in_range & (raw >= VALUE_MAX_DEFAULT - HEALTH_SATURATION_MARGIN)
        self.saturation_streak = np.where(saturated, self.saturation_streak + 1, 0)

        if pressure is not None:
            unloaded = in_range & ~(np.isfinite(pressure) & (pressure > contact_threshold_kpa))
        elif baseline is not None:
            unloaded = in_range & (raw - baseline <= HEALTH_UNLOADED_DELTA)
        else:
            unloaded = in_range & (raw <= HEALTH_UNLOADED_MAX)
        values = np.where(in_range, raw, np.nan)
        self.history.append((values, unloaded))
        recent = np.stack([item[0] for item in self.history])
        unloaded_recent = np.stack([np.where(item[1], item[0], np.nan) for item in self.history])
        count, mean, variance = _rolling_stats(recent)
        unloaded_count, unloaded_mean, unloaded_variance = _rolling_stats(unloaded_recent)
        self.mean = np.where(count > 0, mean, np.nan)
        self.variance = np.where(count > 1, variance, np.nan)
        self.noise = np.where(unloaded_count >= 5, np.sqrt(unloaded_variance), np.nan)

        collecting_reference = unloaded & (self.reference_count < 10)
        self.reference_sum += np.where(collecting_reference, raw, 0)
        self.reference_count += collecting_reference.astype(int)
        new_reference = collecting_reference & (self.reference_count == 10)
        self.reference_time[new_reference] = timestamp
        reference = np.divide(self.reference_sum, self.reference_count,
                              out=np.zeros_like(raw), where=self.reference_count > 0)
        self.baseline_offset = baseline.copy() if baseline is not None else np.where(
            self.reference_count >= 10, reference, np.nan)
        self.drift = np.where(unloaded & (unloaded_count >= 5) & (self.reference_count >= 10),
                              unloaded_mean - reference, np.nan)

        if pressure_calibration is not None:
            self.calibrated = np.asarray([
                [pressure_calibration.is_calibrated(row, col) for col in range(config.TOTAL_COLS)]
                for row in range(config.TOTAL_ROWS)
            ])
        self.states = np.where(self.calibrated, 0, 7)
        self.states = np.where((unloaded_count >= 20) & (self.noise > HEALTH_NOISE_STD), 1, self.states)
        drift_ready = (timestamp - self.reference_time >= HEALTH_DRIFT_MIN_S) & unloaded
        self.states = np.where(drift_ready & (np.abs(self.drift) > HEALTH_DRIFT_DELTA), 2, self.states)

        recent_std = np.sqrt(np.nan_to_num(self.variance))
        neighbor_std = np.zeros_like(recent_std)
        neighbor_std[1:] = np.maximum(neighbor_std[1:], recent_std[:-1])
        neighbor_std[:-1] = np.maximum(neighbor_std[:-1], recent_std[1:])
        neighbor_std[:, 1:] = np.maximum(neighbor_std[:, 1:], recent_std[:, :-1])
        neighbor_std[:, :-1] = np.maximum(neighbor_std[:, :-1], recent_std[:, 1:])
        extreme = (raw <= VALUE_MIN_DEFAULT + 1) | (raw >= VALUE_MAX_DEFAULT - HEALTH_SATURATION_MARGIN)
        stuck = (count >= HEALTH_STUCK_FRAMES) & (recent_std < HEALTH_STUCK_STD)
        stuck &= extreme & (neighbor_std > HEALTH_STUCK_NEIGHBOR_STD)
        self.states = np.where(stuck, 4, self.states)
        self.states = np.where(self.saturation_streak >= HEALTH_SATURATION_FRAMES, 3, self.states)
        self.states = np.where(self.invalid_streak >= HEALTH_INVALID_FRAMES, 6, self.states)
        self.states = np.where(self.missing_streak >= HEALTH_INVALID_FRAMES, 5, self.states)

    def cell(self, row, col):
        return {
            "current": float(self.current[row, col]),
            "mean": float(self.mean[row, col]),
            "variance": float(self.variance[row, col]),
            "noise": float(self.noise[row, col]),
            "baseline_offset": float(self.baseline_offset[row, col]),
            "drift": float(self.drift[row, col]),
            "calibrated": bool(self.calibrated[row, col]),
            "state": HEALTH_STATES[self.states[row, col]],
        }
