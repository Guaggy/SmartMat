"""Snapshot history: every HISTORY_INTERVAL_S per online mat, and at every alert raised/cleared, a small row in the
database (an 8-bit zlib grid and the key numbers, ~0.5 KB). Periodic snapshots also keep the per-cell peak over the
interval. Read by the playback, the CSV exports and the clinical review; no patient data, only mats."""

import math

import numpy as np

import config

ENABLED = getattr(config, "HISTORY_ENABLED", True)
INTERVAL_S = getattr(config, "HISTORY_INTERVAL_S", 300)
MAX_HOTSPOTS = 5
G = 9.81


def _array(grid):
    """Rows x cols list (None = dead cell) or array -> float array, dead cells 0"""
    return np.nan_to_num(np.array([[np.nan if v is None else v for v in row] for row in grid], dtype=float), nan=0.0)


def quantize(grid, scale_max):
    """uint8 0-255 relative to scale_max"""
    return np.clip(np.rint(_array(grid) / (scale_max or 1.0) * 255), 0, 255).astype(np.uint8)


def _round(value, digits=1):
    return None if value is None or not math.isfinite(value) else round(float(value), digits)


def numbers(snap, engine=None):
    """The key figures of a snapshot() dict (plus the engine's contact threshold, cell size and motion counters)"""
    summary = [i for i in snap.get("indices", []) if i.get("layer") == "summary" and i.get("value") is not None
               and i.get("threshold")]
    hotspots = []
    for h in sorted(snap.get("hotspots", []), key=lambda h: -h["peak_kpa"])[:MAX_HOTSPOTS]:
        cells = h["cells"]
        centre = [int(round(sum(c[0] for c in cells) / len(cells))), int(round(sum(c[1] for c in cells) / len(cells)))] if cells else None
        hotspots.append({"id": h["id"], "peak_kpa": h["peak_kpa"], "cells": len(cells), "centre": centre,
                         "active_s": h["active_s"], "persistent": h["persistent"]})
    out = {"peak_kpa": snap.get("peak_kpa"), "risk": snap.get("risk"),
           "score": _round(max((i["value"] / i["threshold"] for i in summary), default=None), 2),
           "posture": snap.get("posture"), "occupied": snap.get("occupied"), "hotspots": hotspots,
           "contact_cells": None, "contact_area_cm2": None, "load_kg": None,
           "time_in_position_s": _round(snap.get("time_in_position_s")),
           "since_movement_s": None, "since_reposition_s": None, "movements": None, "repositions": None}
    grid = snap.get("grid")
    if grid is not None and snap.get("unit") == "kPa" and engine is not None:
        a = _array(grid)
        mask = a >= engine.contact_threshold_kpa
        out["contact_cells"] = int(mask.sum())
        area = engine.cell_area_m2
        if area:
            out["contact_area_cm2"] = _round(mask.sum() * area * 1e4)
            out["load_kg"] = _round(a[mask].sum() * 1000 * area / G)
    if engine is not None:
        motion = engine.motion
        out.update(engine.motion_ages())
        out["movements"], out["repositions"] = int(motion.movement_total), int(motion.reposition_total)
    return out


class HistoryRecorder:
    """observe(): called every tick for every mat (keeps the running peak, writes a periodic snapshot when due).
    alert(): one snapshot for a raised/cleared alert. Nothing here raises into the server loop."""

    def __init__(self, store, enabled=ENABLED, interval_s=INTERVAL_S):
        self.store, self.enabled, self.interval_s = store, enabled, interval_s
        self._peak = {}   # chip_id -> running per-cell maximum (in the mat's unit)
        self._last = {}   # chip_id -> time of the last periodic snapshot (or when the mat was first seen)

    def observe(self, chip_id, snap, engine, now):
        if not self.enabled:
            return
        if not snap.get("online") or snap.get("grid") is None:
            self._peak.pop(chip_id, None)
            self._last.pop(chip_id, None)   # the interval counts from when the mat is back
            return
        grid = _array(snap["grid"])
        peak = self._peak.get(chip_id)
        self._peak[chip_id] = grid if peak is None or peak.shape != grid.shape else np.maximum(peak, grid)
        last = self._last.setdefault(chip_id, now)
        if not 0 <= now - last < self.interval_s:   # due (or the clock went back)
            self._last[chip_id] = now
            self._write(chip_id, snap, engine, now, "periodic", self._peak.pop(chip_id), None)

    def alert(self, kind, alert, snap, engine, now):
        """kind: 'raised' | 'cleared'; snap may be None (a mat without an engine)"""
        if self.enabled:
            self._write(alert["chip_id"], snap, engine, now, f"alert_{kind}", None, alert)

    def _write(self, chip_id, snap, engine, now, reason, peak, alert):
        try:
            snap = snap or {"risk": "offline", "posture": "none", "occupied": None}
            scale, grid = snap.get("scale_max"), snap.get("grid")
            self.store.add_snapshot(now, chip_id, reason, numbers(snap, engine),
                                    None if grid is None else quantize(grid, scale),
                                    None if peak is None else quantize(peak, scale), alert, snap.get("unit"), scale)
        except Exception as error:   # history is a convenience: never stop the tick for it
            print(f"history {chip_id}: {type(error).__name__}: {error}")
