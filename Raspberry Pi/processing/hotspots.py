"""Connected pressure regions with simple deterministic ID tracking."""

from collections import deque
import math

import numpy as np

from config import (
    HOTSPOT_ACTIVATE_KPA, HOTSPOT_DEACTIVATE_KPA, HOTSPOT_MIN_CELLS,
    HOTSPOT_PERSISTENCE_S, HOTSPOT_MAX_MOVE_CELLS, HOTSPOT_END_RELIEF_S,
)
from processing.temporal import FULL, PARTIAL


def connected_regions(mask):
    """Return four-neighbor connected cell sets."""
    rows, cols = mask.shape
    unseen = set(zip(*np.nonzero(mask)))
    regions = []
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        region = {start}
        pending = [start]
        while pending:
            row, col = pending.pop()
            for neighbor in ((row - 1, col), (row + 1, col),
                             (row, col - 1), (row, col + 1)):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    region.add(neighbor)
                    pending.append(neighbor)
        regions.append(region)
    return regions


class HotspotTracker:
    def __init__(self):
        self.activate_kpa = HOTSPOT_ACTIVATE_KPA
        self.deactivate_kpa = HOTSPOT_DEACTIVATE_KPA
        self.min_cells = HOTSPOT_MIN_CELLS
        self.persistence_s = HOTSPOT_PERSISTENCE_S
        self.max_move_cells = HOTSPOT_MAX_MOVE_CELLS
        self.end_relief_s = HOTSPOT_END_RELIEF_S
        self.tracks = {}
        self.ended = deque(maxlen=50)
        self.next_id = 1
        self.last_time = None
        self._gap = False
        self.data_valid = False
        self._previous_exposure = None
        self.reset()

    def settings(self):
        return {key: getattr(self, key) for key in (
            "activate_kpa", "deactivate_kpa", "min_cells", "persistence_s",
            "max_move_cells", "end_relief_s")}

    def reset(self):
        self.tracks.clear()
        self.ended.clear()
        self.next_id = 1
        self.last_time = None
        self._previous_exposure = None
        self._gap = False
        self.data_valid = False
        self.initial_frame = True
        self.created_total = 0
        self.persistent_total = 0
        self.ended_total = 0
        self.longest_observed_s = 0.0

    def invalidate(self):
        self._gap = True
        self.data_valid = False

    @property
    def active(self):
        return [track for track in self.tracks.values() if track["state"] == "active"]

    def update(self, pressure, timestamp, temporal, cell_area_m2=None):
        if pressure is None or timestamp is None:
            self.invalidate()
            return []
        values = np.asarray(pressure, dtype=float)
        if values.shape != temporal.exposure.shape or not np.all(np.isfinite(values)):
            self.invalidate()
            return []
        if (self._gap and not self.initial_frame) or (self.last_time is not None and
                         (timestamp <= self.last_time or timestamp - self.last_time > temporal.max_gap_s)):
            self.last_time = timestamp
            self._previous_exposure = temporal.exposure.copy()
            self._gap = False
            self.data_valid = False
            return []
        self._gap = False
        dt = 0 if self.last_time is None else timestamp - self.last_time
        self.last_time = timestamp
        self.data_valid = True
        exposure_delta = (np.zeros_like(values) if self._previous_exposure is None else
                          np.maximum(0, temporal.exposure - self._previous_exposure))
        self._previous_exposure = temporal.exposure.copy()

        low_mask = values >= self.deactivate_kpa
        regions = []
        for cells in connected_regions(low_mask):
            if len(cells) < self.min_cells:
                continue
            if any(values[cell] >= self.activate_kpa for cell in cells) or any(
                    cells & track["cells"] for track in self.tracks.values()):
                regions.append(cells)
        regions.sort(key=lambda cells: min(cells))
        matches = []
        for index, cells in enumerate(regions):
            center = np.mean(np.asarray(list(cells)), axis=0)
            for track in self.tracks.values():
                overlap = len(cells & track["cells"])
                distance = math.dist(center, track["centroid"])
                if overlap or distance <= self.max_move_cells:
                    matches.append((-overlap, distance, track["id"], index))
        assigned_tracks, assigned_regions = set(), set()
        assignments = {}
        for _negative_overlap, _distance, track_id, index in sorted(matches):
            if track_id not in assigned_tracks and index not in assigned_regions:
                assignments[index] = track_id
                assigned_tracks.add(track_id)
                assigned_regions.add(index)

        events = []
        for track in list(self.active):
            if sum(bool(track["cells"] & cells) for cells in regions) > 1:
                events.append(("hotspot_split", track["id"]))
        for index, cells in enumerate(regions):
            if index not in assignments:
                continue
            survivor = assignments[index]
            for track in list(self.active):
                if track["id"] != survivor and cells & track["cells"]:
                    if track.get("merged_into") != survivor:
                        events.append(("hotspot_merged", track["id"]))
                        track["merged_into"] = survivor
        for index, cells in enumerate(regions):
            new_track = index not in assignments
            was_relieved = False
            if index in assignments:
                track = self.tracks[assignments[index]]
                if track["state"] == "relieved":
                    was_relieved = True
                    track["state"] = "active"
                    track["relieved_since"] = None
                    track["relieved_s"] = 0.0
                    events.append(("hotspot_resumed", track["id"]))
            else:
                if not any(values[cell] >= self.activate_kpa for cell in cells):
                    continue
                track_id = self.next_id
                self.next_id += 1
                track = {
                    "id": track_id, "first_seen": timestamp, "last_seen": timestamp,
                    "active_s": 0.0, "total_active_s": 0.0, "persistent": False,
                    "peak_observed": 0.0, "max_cells": 0, "total_exposure": 0.0,
                    "max_burden": 0.0, "state": "active", "relieved_since": None,
                    "relieved_s": 0.0,
                    "started_before_session": self.initial_frame,
                    "prior_duration_s": None if self.initial_frame else 0.0,
                    "tracking_decision": "Observed at session start" if self.initial_frame else "New region",
                    "matched_previous_id": None, "previous_overlap_cells": 0,
                    "cells": set(), "centroid": (0.0, 0.0),
                }
                self.tracks[track_id] = track
                self.created_total += 1
                events.append(("hotspot_started", track_id))
            if not new_track:
                previous_cells = track["cells"]
                track["previous_overlap_cells"] = len(previous_cells & cells)
                track["matched_previous_id"] = track["id"]
                track["tracking_decision"] = ("Resumed after relief" if was_relieved
                                              else "Matched by overlap" if previous_cells & cells else
                                              "Matched by centroid distance")
            self._measure(track, cells, values, exposure_delta, temporal, cell_area_m2)
            track["merged_into"] = None
            track["last_seen"] = timestamp
            track["active_s"] += 0 if new_track else dt
            track["total_active_s"] += 0 if new_track else dt
            self.longest_observed_s = max(self.longest_observed_s, track["total_active_s"])
            if not track["persistent"] and track["active_s"] >= self.persistence_s:
                track["persistent"] = True
                self.persistent_total += 1
                events.append(("hotspot_persistent", track["id"]))

        for track_id, track in list(self.tracks.items()):
            if track_id in assigned_tracks or (track["state"] == "active" and
                                                track["last_seen"] == timestamp):
                continue
            if track["state"] == "active":
                track["state"] = "relieved"
                track["relieved_since"] = timestamp
                track["relieved_s"] = 0.0
                track["active_s"] = 0.0
                events.append(("hotspot_relief_started", track_id))
            else:
                track["relieved_s"] += dt
            if track["state"] == "relieved" and track["relieved_s"] >= self.end_relief_s:
                self.ended.append(track.copy())
                self.ended_total += 1
                del self.tracks[track_id]
                events.append(("hotspot_ended", track_id))
        self.initial_frame = False
        return events

    def _measure(self, track, cells, pressure, exposure_delta, temporal, cell_area_m2):
        ordered = sorted(cells)
        rows, cols = zip(*ordered)
        values = pressure[rows, cols]
        track["cells"] = cells
        track["centroid"] = (float(np.mean(rows)), float(np.mean(cols)))
        track["peak_kpa"] = float(values.max())
        track["mean_kpa"] = float(values.mean())
        track["cell_count"] = len(cells)
        track["area_cm2"] = None if cell_area_m2 is None else len(cells) * cell_area_m2 * 10_000
        track["force_n"] = None if cell_area_m2 is None else float(values.sum() * 1000 * cell_area_m2)
        track["exposure_kpa_min"] = float(temporal.exposure[rows, cols].sum())
        track["burden"] = float(temporal.burden[rows, cols].max())
        track["total_exposure"] += float(exposure_delta[rows, cols].sum())
        track["peak_observed"] = max(track["peak_observed"], track["peak_kpa"])
        track["max_cells"] = max(track["max_cells"], len(cells))
        track["max_burden"] = max(track["max_burden"], track["burden"])
        states = temporal.state[rows, cols]
        track["relief_state"] = ("Unknown" if np.all(states == 0) else
                                 "Full relief" if np.all(states == FULL) else
                                 "Partial relief" if np.any(states == PARTIAL) else "Loaded")
        since = temporal.time_since_relief()[rows, cols]
        finite = since[np.isfinite(since)]
        track["since_relief_s"] = float(finite.max()) if finite.size else math.nan
