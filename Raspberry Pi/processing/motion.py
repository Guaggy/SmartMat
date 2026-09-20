"""Transparent movement and sustained pressure redistribution analysis."""

from collections import deque
import math

import numpy as np

from config import (
    MOVEMENT_SMALL_SCORE, MOVEMENT_SIGNIFICANT_SCORE, MOVEMENT_MAJOR_SCORE,
    MOVEMENT_COP_SCALE_CELLS, MOVEMENT_COOLDOWN_S,
    REPOSITION_MIN_SCORE, REPOSITION_SETTLE_S, REPOSITION_BEFORE_S,
    REPOSITION_AFTER_S, REPOSITION_MIN_CHANGE, REPOSITION_COOLDOWN_S,
    REPOSITION_MIN_CONTACT_CELLS,
    HOTSPOT_ACTIVATE_KPA,
)
from processing.analysis import load_distribution
from processing.statistics import contact_mask, pressure_statistics


class MotionAnalyzer:
    def __init__(self):
        self.small_score = MOVEMENT_SMALL_SCORE
        self.significant_score = MOVEMENT_SIGNIFICANT_SCORE
        self.major_score = MOVEMENT_MAJOR_SCORE
        self.cop_scale_cells = MOVEMENT_COP_SCALE_CELLS
        self.movement_cooldown_s = MOVEMENT_COOLDOWN_S
        self.reposition_min_score = REPOSITION_MIN_SCORE
        self.settle_s = REPOSITION_SETTLE_S
        self.before_s = REPOSITION_BEFORE_S
        self.after_s = REPOSITION_AFTER_S
        self.reposition_min_change = REPOSITION_MIN_CHANGE
        self.reposition_min_contact_cells = REPOSITION_MIN_CONTACT_CELLS
        self.reposition_cooldown_s = REPOSITION_COOLDOWN_S
        self.high_pressure_kpa = HOTSPOT_ACTIVATE_KPA
        self.reset()

    def settings(self):
        return {key: getattr(self, key) for key in (
            "small_score", "significant_score", "major_score", "cop_scale_cells",
            "movement_cooldown_s", "reposition_min_score", "settle_s", "before_s",
            "after_s", "reposition_min_change", "reposition_min_contact_cells",
            "reposition_cooldown_s",
            "high_pressure_kpa")}

    def reset(self):
        self.previous = None
        self.previous_time = None
        self.previous_stats = None
        self.last_movement_event = -math.inf
        self.last_reposition = -math.inf
        self.pending = None
        self.last_score = {"score": 0.0, "map_change": 0.0, "cop_cells": 0.0,
                           "cop_score": 0.0, "area_change": 0.0, "category": "Stable"}
        self.debug = {"stage": "idle", "reason": "No reposition candidate"}
        self.movements = deque(maxlen=200)
        self.repositions = deque(maxlen=100)
        self.movement_total = 0
        self.major_total = 0
        self.reposition_total = 0
        self._buckets = deque(maxlen=max(5, math.ceil(self.before_s + self.settle_s + self.after_s) + 5))

    def invalidate(self):
        self.previous = None
        self.previous_time = None
        self.previous_stats = None
        self.pending = None
        self._buckets.clear()
        self.debug = {"stage": "invalid data", "reason": "Comparison reset after a data gap"}

    def _append_bucket(self, timestamp, pressure, stats, hotspots, temporal):
        bucket_id = math.floor(timestamp)
        if not self._buckets or self._buckets[-1]["second"] != bucket_id:
            self._buckets.append({"second": bucket_id, "sum": np.zeros_like(pressure), "count": 0,
                                  "hotspot_count": 0.0, "persistent_count": 0.0,
                                  "max_burden": 0.0, "exposure": 0.0,
                                  "hotspot_rate": 0.0})
        bucket = self._buckets[-1]
        bucket["sum"] += pressure
        bucket["count"] += 1
        bucket["hotspot_count"] += len(hotspots)
        bucket["persistent_count"] += sum(track["persistent"] for track in hotspots)
        bucket["max_burden"] += float(np.nanmax(temporal.burden))
        bucket["exposure"] += float(np.nansum(temporal.exposure))
        bucket["hotspot_rate"] += max((track["mean_kpa"] for track in hotspots), default=0)

    def _window(self, start, end, contact_threshold, cell_area_m2):
        selected = [bucket for bucket in self._buckets if start <= bucket["second"] < end]
        count = sum(bucket["count"] for bucket in selected)
        if not count:
            return None
        grid = sum((bucket["sum"] for bucket in selected), np.zeros_like(selected[0]["sum"])) / count
        stats = pressure_statistics(grid, contact_threshold, cell_area_m2)
        distribution = load_distribution(grid, calibrated=True, cell_area_m2=cell_area_m2)
        return {
            "grid": grid, "seconds_covered": len(selected),
            "peak_kpa": stats["peak_kpa"], "mean_kpa": stats["mean_kpa"],
            "contact_cells": stats["contact_cells"], "contact_area_m2": stats["contact_area_m2"],
            "high_pressure_cells": int(np.count_nonzero(grid >= self.high_pressure_kpa)),
            "cop_x": stats["cop_x"], "cop_y": stats["cop_y"],
            "hotspot_count": sum(bucket["hotspot_count"] for bucket in selected) / count,
            "persistent_count": sum(bucket["persistent_count"] for bucket in selected) / count,
            "max_burden": sum(bucket["max_burden"] for bucket in selected) / count,
            "exposure": sum(bucket["exposure"] for bucket in selected) / count,
            "hotspot_exposure_rate": sum(bucket["hotspot_rate"] for bucket in selected) / count,
            "left_percent": None if distribution is None else distribution["left"],
            "upper_percent": None if distribution is None else distribution["upper"],
        }

    def _difference(self, first, second):
        return float(np.abs(first - second).sum() / max(float(first.sum() + second.sum()), 1))

    def update(self, pressure, timestamp, contact_threshold, cell_area_m2, hotspots, temporal):
        if pressure is None or timestamp is None:
            self.invalidate()
            return []
        values = np.asarray(pressure, dtype=float)
        if values.shape != temporal.exposure.shape or not np.all(np.isfinite(values)):
            self.invalidate()
            return []
        if self.previous_time is not None and (timestamp <= self.previous_time or
                                               timestamp - self.previous_time > temporal.max_gap_s):
            self.invalidate()
        stats = pressure_statistics(values, contact_threshold, cell_area_m2)
        events = []
        if self.previous is not None:
            map_change = self._difference(values, self.previous)
            old_x, old_y = self.previous_stats["cop_x"], self.previous_stats["cop_y"]
            new_x, new_y = stats["cop_x"], stats["cop_y"]
            cop_cells = math.dist((old_x, old_y), (new_x, new_y)) if None not in (old_x, old_y, new_x, new_y) else 0
            old_area, new_area = self.previous_stats["contact_cells"], stats["contact_cells"]
            area_change = abs(new_area - old_area) / max(old_area, new_area, 1)
            cop_score = min(1, cop_cells / self.cop_scale_cells)
            score = max(map_change, cop_score, area_change)
            category = ("Major movement" if score >= self.major_score else
                        "Significant movement" if score >= self.significant_score else
                        "Small movement" if score >= self.small_score else "Stable")
            self.last_score = {"score": score, "map_change": map_change,
                               "cop_cells": cop_cells, "cop_score": cop_score,
                               "area_change": area_change,
                               "category": category}
            if score >= self.significant_score and timestamp - self.last_movement_event >= self.movement_cooldown_s:
                movement = {"timestamp": timestamp, **self.last_score}
                self.movements.append(movement)
                self.movement_total += 1
                self.major_total += category == "Major movement"
                events.append(("movement", {"movement": movement}))
                self.last_movement_event = timestamp
            if (self.pending is None and score >= self.reposition_min_score and
                    timestamp - self.last_reposition >= self.reposition_cooldown_s):
                before = self._window(timestamp - self.before_s, math.floor(timestamp),
                                      contact_threshold, cell_area_m2)
                if (before is not None and before["seconds_covered"] >= min(2, self.before_s)
                        and before["contact_cells"] >= self.reposition_min_contact_cells):
                    self.pending = {"timestamp": timestamp, "before": before,
                                    "movement": self.last_score.copy()}
                    self.debug = {"stage": "settling", "candidate_start": timestamp,
                                  "before": self._without_grid(before),
                                  "reason": "Movement trigger met"}
        self.previous = values.copy()
        self.previous_time = timestamp
        self.previous_stats = stats
        self._append_bucket(timestamp, values, stats, hotspots, temporal)
        if self.pending is not None:
            after_start = self.pending["timestamp"] + self.settle_s
            if timestamp >= after_start:
                self.debug["stage"] = "collecting after window"
            if timestamp >= after_start + self.after_s:
                after = self._window(after_start, after_start + self.after_s,
                                     contact_threshold, cell_area_m2)
                before = self.pending["before"]
                if (after is not None and after["seconds_covered"] >= max(1, self.after_s * 0.75)
                        and after["contact_cells"] >= self.reposition_min_contact_cells):
                    change = self._difference(before["grid"], after["grid"])
                    current_change = self._difference(before["grid"], values)
                    self.debug = {"stage": "rejected", "candidate_start": self.pending["timestamp"],
                                  "before": self._without_grid(before), "after": self._without_grid(after),
                                  "redistribution": change, "current_change": current_change,
                                  "threshold": self.reposition_min_change,
                                  "reason": "Redistribution did not persist"}
                    if min(change, current_change) >= self.reposition_min_change:
                        record = self._reposition_record(self.pending, after, change)
                        self.repositions.append(record)
                        self.reposition_total += 1
                        self.last_reposition = timestamp
                        events.append(("reposition_detected", {"reposition": self._serializable(record)}))
                        self.debug["stage"] = "confirmed"
                        self.debug["reason"] = "Sustained redistribution met threshold"
                else:
                    self.debug = {"stage": "rejected", "candidate_start": self.pending["timestamp"],
                                  "reason": "Insufficient valid or contacted after-window data"}
                self.pending = None
        return events

    @staticmethod
    def _without_grid(summary):
        return {key: value for key, value in summary.items() if key != "grid"}

    def _reposition_record(self, pending, after, change):
        before = pending["before"]
        first = (before["cop_x"], before["cop_y"])
        second = (after["cop_x"], after["cop_y"])
        cop_distance = math.dist(first, second) if None not in first + second else None
        return {
            "timestamp": pending["timestamp"], "movement": pending["movement"],
            "redistribution": change, "cop_displacement_cells": cop_distance,
            "before": before, "after": after,
        }

    @staticmethod
    def _serializable(record):
        return {"timestamp": record["timestamp"], "movement": record["movement"],
                "redistribution": record["redistribution"],
                "cop_displacement_cells": record["cop_displacement_cells"],
                "before": {key: value for key, value in record["before"].items() if key != "grid"},
                "after": {key: value for key, value in record["after"].items() if key != "grid"}}
