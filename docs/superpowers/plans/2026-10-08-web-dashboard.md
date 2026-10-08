# Web Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the single-grid test page in `gui/web.py` into a read-only per-mat dashboard: pick a known mat; for the live one see heatmap, hotspots, patient state and index values.

**Architecture:** `gui/web.py` keeps a small lock-guarded store keyed by mat ID and serves it through three GET addresses plus one static page that polls them. The desktop app stays the only producer: about once a second it publishes the known-mat list and a snapshot of the mat it is connected to. Mats it is not connected to are listed without data.

**Tech Stack:** Python 3.13, Flask (already a dependency), plain HTML/JS, `unittest` with Flask's test client.

**Spec:** `docs/superpowers/specs/2026-10-08-web-dashboard-design.md`

## Global Constraints

- Read-only: GET addresses only; nothing on the page changes the desktop.
- No new dependencies, no JavaScript libraries, no external URLs in the page.
- Addresses: `/`, `/api/mats`, `/api/mats/<mat_id>`. `/data` and `update_grid()` are removed.
- The non-MQTT source's mat ID is `local`.
- Heatmap is kPa when the frame has pressure, else the baseline-subtracted signal with unit `relative`; it does not follow the desktop's Data dropdown.
- A snapshot older than `STALE_AFTER_S` is reported as stale.
- Server text reaches the page only through `textContent` (nicknames are user-entered).
- Wording: "index", "threshold", "Patient detected / No patient"; never "risk". The page says it is not a medical device.
- Read the grid size only as `config.TOTAL_ROWS` / `config.TOTAL_COLS`.
- No commits (unrelated uncommitted work is in the tree). No AI attribution.
- After every task, from `Raspberry Pi/`: `python -m unittest discover -s tests -v`. Baseline: 134 tests, OK. One file: `python -m unittest discover -s tests -p "test_web.py" -v`.

## Where the request did not match the code

1. **"Share live data" is already removed.** No checkbox, `set_sharing()`, sharing gate or CORS header exists in the code. Only the `notes.md` line is deleted (Task 3).
2. **`tests/test_multi_mat.py` asserts on the old page** (`"var ROWS = 20;"` in `web.index()`). The new page takes its size from the API, so that assertion is removed (Task 1).
3. **The public website widget still points at `/data`.** It already cannot read it (no CORS header); this plan removes the address and does not touch `Website/`.

## Review Focus

1. A mat ID in the address that is not known must give a clean 404, not a server error. Test in Task 1.
2. A snapshot from a mat that is no longer live must not keep being served as that mat's data. Test in Task 1.
3. NaN / uncalibrated cells and an unknown index value must serialise as `null`, not break `jsonify` or show as 0. Test in Task 1.
4. A desktop that stops sending must show as stale, not as a frozen live picture. Test in Task 1.
5. Opening the page with nothing connected, or with no mats known at all, must still render. Tests in Tasks 1 and 2.

## File Structure

| File | Change |
|---|---|
| `gui/web.py` | rewritten: store, `build_snapshot`, three addresses, page |
| `gui/desktop.py` | `_publish_web`, hostname address, hooks |
| `tests/test_web.py` | new |
| `tests/test_multi_mat.py` | one stale assertion removed |
| `STATUS.md`, `notes.md`, `README.md` | docs |

---

### Task 1: Store, snapshot, addresses, page

**Files:**
- Rewrite: `gui/web.py`
- Modify: `tests/test_multi_mat.py`
- Test: `tests/test_web.py` (create)

**Interfaces:**
- Consumes: `IndexMonitor` (`definitions`, `states`, `compared`), hotspot track dicts (`id`, `peak_kpa`, `cells`, `active_s`, `persistent`), frame dict (`pressure`, `baseline_subtracted`).
- Produces: `web.update(mats, live_id=None, snapshot=None)`; `web.build_snapshot(frame, hotspot_tracks, occupied, monitor) -> dict`; `web.app`; `web.WebServer` (unchanged); `web.WEB_PORT`.

- [ ] **Step 1: Write the failing tests** - create `tests/test_web.py`:

<!-- file: tests/test_web.py -->
```python
"""Web dashboard: per-mat store, snapshot, addresses, and the desktop feeding it."""

import socket
import tkinter as tk
import unittest
from unittest import mock

import numpy as np

from gui import web
from processing.indices import IndexMonitor

SHAPE = (16, 15)
MATS = [{"id": "aaa111", "name": "Bed", "rows": 16, "cols": 15},
        {"id": "bbb222", "name": "bbb222", "rows": 20, "cols": 12}]


def snapshot(value=5.0):
    return {"unit": "kPa", "scale_max": 50.0, "grid": [[value]], "occupied": True,
            "hotspots": [], "indices": []}


class StoreAndAddressTests(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()
        web.update([])
        self.addCleanup(web.update, [])

    def test_page_is_served_without_any_mat_known(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"not a medical device", response.data)
        self.assertEqual(self.client.get("/api/mats").get_json(), {"mats": []})

    def test_mat_list_marks_the_live_one(self):
        web.update(MATS, "aaa111", snapshot())
        mats = self.client.get("/api/mats").get_json()["mats"]
        self.assertEqual([(mat["id"], mat["name"], mat["live"]) for mat in mats],
                         [("aaa111", "Bed", True), ("bbb222", "bbb222", False)])
        self.assertNotIn(b"Bed", self.client.get("/").data)   # names only arrive through the API

    def test_live_mat_has_a_snapshot_and_others_do_not(self):
        web.update(MATS, "aaa111", snapshot())
        live = self.client.get("/api/mats/aaa111").get_json()
        self.assertEqual((live["live"], live["stale"], live["snapshot"]["grid"]), (True, False, [[5.0]]))
        self.assertLess(live["age_s"], 5)
        other = self.client.get("/api/mats/bbb222").get_json()
        self.assertEqual((other["live"], other["snapshot"], other["rows"]), (False, None, 20))

    def test_unknown_mat_is_a_clean_404(self):
        web.update(MATS, "aaa111", snapshot())
        for mat_id in ("nope", "..%2F..%2Fetc", "aaa111x"):
            response = self.client.get(f"/api/mats/{mat_id}")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.get_json(), {"error": "unknown mat"})
        self.assertEqual(self.client.get("/data").status_code, 404)   # old address is gone

    def test_old_snapshot_is_reported_stale(self):
        with mock.patch.object(web.time, "monotonic", return_value=100.0):
            web.update(MATS, "aaa111", snapshot())
        with mock.patch.object(web.time, "monotonic", return_value=100.0 + web.STALE_AFTER_S + 1):
            data = self.client.get("/api/mats/aaa111").get_json()
        self.assertTrue(data["stale"])
        self.assertAlmostEqual(data["age_s"], web.STALE_AFTER_S + 1)

    def test_snapshot_does_not_outlive_its_mat_being_live(self):
        web.update(MATS, "aaa111", snapshot(1.0))
        web.update(MATS, "bbb222", snapshot(2.0))
        self.assertIsNone(self.client.get("/api/mats/aaa111").get_json()["snapshot"])
        self.assertEqual(self.client.get("/api/mats/bbb222").get_json()["snapshot"]["grid"], [[2.0]])
        web.update(MATS)                                   # disconnected
        self.assertIsNone(self.client.get("/api/mats/bbb222").get_json()["snapshot"])
        web.update(MATS, "aaa111")                         # live but no frame yet
        data = self.client.get("/api/mats/aaa111").get_json()
        self.assertEqual((data["live"], data["snapshot"], data["stale"]), (True, None, False))


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.pressure = np.zeros(SHAPE)
        self.pressure[0, 0] = 31.239
        self.pressure[1, 1] = np.nan
        self.frame = {"pressure": self.pressure, "baseline_subtracted": np.full(SHAPE, 123.0)}
        self.monitor = IndexMonitor()

    def test_pressure_grid_with_unknown_cells(self):
        data = web.build_snapshot(self.frame, [], True, self.monitor)
        self.assertEqual((data["unit"], data["scale_max"]), ("kPa", web.PRESSURE_DISPLAY_MAX_KPA))
        self.assertEqual((len(data["grid"]), len(data["grid"][0])), SHAPE)
        self.assertEqual((data["grid"][0][0], data["grid"][1][1], data["grid"][2][2]), (31.24, None, 0.0))
        web.app.json.dumps(data)   # must be valid JSON as it stands

    def test_falls_back_to_the_relative_signal_without_calibration(self):
        self.frame["pressure"] = None
        data = web.build_snapshot(self.frame, [], None, self.monitor)
        self.assertEqual((data["unit"], data["scale_max"], data["grid"][0][0]),
                         ("relative", web.VALUE_MAX_DEFAULT, 123.0))
        self.assertIsNone(data["occupied"])

    def test_hotspots_and_patient_states(self):
        track = {"id": 3, "peak_kpa": 31.239, "cells": {(2, 5), (2, 4)}, "active_s": 42.04,
                 "persistent": True, "centroid": (2.0, 4.5)}
        data = web.build_snapshot(self.frame, [track], False, self.monitor)
        self.assertEqual(data["hotspots"], [{"id": 3, "peak_kpa": 31.2, "cells": [[2, 4], [2, 5]],
                                             "active_s": 42.0, "persistent": True}])
        self.assertIs(data["occupied"], False)

    def test_indices_report_value_threshold_and_state(self):
        data = web.build_snapshot(self.frame, [], True, self.monitor)   # nothing evaluated yet
        self.assertEqual([(item["name"], item["layer"], item["value"], item["state"]) for item in data["indices"]],
                         [("Sustained load", "map", None, "inactive"), ("Mat overview", "summary", None, "inactive")])
        self.monitor.values = {"Sustained load": np.full(SHAPE, 0.25), "Mat overview": 0.9}
        self.monitor.states = {"Sustained load": "ok", "Mat overview": "near"}
        data = web.build_snapshot(self.frame, [], True, self.monitor)
        self.assertEqual(data["indices"][0]["value"], 0.25)                # a map index reports its peak cell
        self.assertEqual(data["indices"][1], {"name": "Mat overview", "layer": "summary", "value": 0.9,
                                              "threshold": 1.0, "near": 0.8, "state": "near"})


class DesktopFeedTests(unittest.TestCase):
    def setUp(self):
        from gui import desktop
        self.desktop = desktop
        for patch in (mock.patch.object(desktop, "load_mat_names", return_value={"aaa111": "Bed"}),
                      mock.patch.object(desktop, "INDEX_UPDATE_INTERVAL_S", 0.0)):
            patch.start()
            self.addCleanup(patch.stop)
        try:
            self.app = desktop.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(web.update, [])
        self.addCleanup(self.app._on_close)
        self.client = web.app.test_client()

    def test_connected_source_is_published_as_the_live_local_mat(self):
        self.assertEqual(self.client.get("/api/mats").get_json(), {"mats": []})
        self.app._connect()                                # Simulated
        mats = self.client.get("/api/mats").get_json()["mats"]
        self.assertEqual([(mat["id"], mat["live"]) for mat in mats], [("local", True)])
        self.assertIn("Simulated", mats[0]["name"])
        grid = np.zeros(SHAPE)
        grid[:4, :4] = 600.0
        self.app._handle_new_frame(grid, sample_time=1)
        self.app._publish_web(force=True)
        data = self.client.get("/api/mats/local").get_json()
        self.assertEqual((data["rows"], data["cols"], data["snapshot"]["unit"]), (16, 15, "kPa"))
        self.assertEqual(data["snapshot"]["grid"][0][0], 30.0)
        self.assertEqual(len(data["snapshot"]["indices"]), 2)
        self.app._disconnect()
        self.assertEqual(self.client.get("/api/mats").get_json(), {"mats": []})

    def test_known_mqtt_mats_are_listed_by_nickname(self):
        self.app._mats = {"aaa111": (16, 15), "bbb222": (20, 12)}
        self.app._publish_web(force=True)
        mats = self.client.get("/api/mats").get_json()["mats"]
        self.assertEqual([(mat["id"], mat["name"], mat["rows"], mat["live"]) for mat in mats],
                         [("aaa111", "Bed", 16, False), ("bbb222", "bbb222", 20, False)])

    def test_address_uses_the_hostname(self):
        self.assertIn(f"http://{socket.gethostname()}.local:{web.WEB_PORT}", self.app.web_address_var.get())
        self.assertIn(f"{socket.gethostname()}.local", self.app.status_var.get())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, expect failure** - `python -m unittest discover -s tests -p "test_web.py" -v` -> `AttributeError: module 'gui.web' has no attribute 'update'`.

- [ ] **Step 3: Rewrite `gui/web.py`:**

<!-- file: gui/web.py -->
```python
"""Local read-only web dashboard, toggled from the desktop app.

The desktop app is the only producer: it calls update() with the mats it knows about and a
snapshot of the one it is connected to. A browser on the same network picks a mat and gets a
quick glance: heatmap, hotspots, patient state and index values. Nothing here changes the app.
"""

import threading
import time

import numpy as np
from flask import Flask, jsonify
from werkzeug.serving import make_server

from config import PRESSURE_DISPLAY_MAX_KPA, STALE_AFTER_S, VALUE_MAX_DEFAULT, WEB_PORT

app = Flask(__name__)

_lock = threading.Lock()
_mats = []        # [{"id", "name", "rows", "cols"}] - every mat the desktop app knows about
_live_id = None   # the mat the desktop app is connected to
_snapshot = None  # latest snapshot of the live mat
_snapshot_time = None


def update(mats, live_id=None, snapshot=None):
    """Called by the desktop app: the known mats, which one is live, and its newest snapshot"""
    global _mats, _live_id, _snapshot, _snapshot_time
    with _lock:
        if live_id != _live_id:
            _snapshot = _snapshot_time = None  # a snapshot never outlives its mat being live
        _mats = [dict(mat) for mat in mats]
        _live_id = live_id
        if live_id is not None and snapshot is not None:
            _snapshot, _snapshot_time = snapshot, time.monotonic()


def build_snapshot(frame, hotspot_tracks, occupied, monitor):
    """JSON-ready glance at one mat, from the desktop app's current frame and trackers"""
    pressure = frame["pressure"]
    if pressure is not None:
        grid, unit, scale_max = pressure, "kPa", PRESSURE_DISPLAY_MAX_KPA
    else:  # not calibrated: show the tared signal, and say so
        grid, unit, scale_max = frame["baseline_subtracted"], "relative", VALUE_MAX_DEFAULT
    indices = []
    for definition in monitor.definitions:
        value = monitor.compared(definition["name"])
        indices.append({"name": definition["name"], "layer": definition["layer"],
                        "value": None if value is None else round(value, 3),
                        "threshold": definition["threshold"],
                        "near": definition["near_fraction"] * definition["threshold"],
                        "state": monitor.states[definition["name"]]})
    return {
        "unit": unit, "scale_max": float(scale_max),
        "grid": [[round(float(value), 2) if np.isfinite(value) else None for value in row] for row in grid],
        "occupied": occupied,
        "hotspots": [{"id": track["id"], "peak_kpa": round(track["peak_kpa"], 1),
                      "cells": sorted([int(row), int(col)] for row, col in track["cells"]),
                      "active_s": round(track["active_s"], 1), "persistent": bool(track["persistent"])}
                     for track in hotspot_tracks],
        "indices": indices,
    }


@app.route("/")
def index():
    return _PAGE


@app.route("/api/mats")
def list_mats():
    with _lock:
        return jsonify({"mats": [dict(mat, live=mat["id"] == _live_id) for mat in _mats]})


@app.route("/api/mats/<mat_id>")
def one_mat(mat_id):
    with _lock:
        mat = next((mat for mat in _mats if mat["id"] == mat_id), None)
        if mat is None:
            return jsonify({"error": "unknown mat"}), 404
        live = mat_id == _live_id
        snapshot = _snapshot if live else None
        age = None if snapshot is None else time.monotonic() - _snapshot_time
    return jsonify(dict(mat, live=live, snapshot=snapshot, age_s=age,
                        stale=age is not None and age > STALE_AFTER_S))


class WebServer:
    """Runs the web server on a background thread; start()/stop() toggle it cleanly"""

    def __init__(self):
        self._server = None
        self._thread = None

    def start(self):
        self._server = make_server("0.0.0.0", WEB_PORT, app)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._thread.join(timeout=1)
            self._server = None


# One static page; everything shown comes from the two /api addresses and is written with
# textContent (mat nicknames are typed in by users).
_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SmartMat</title>
  <style>
    body { margin: 0; padding: 16px; background: #15171a; color: #d4d7db; font-family: system-ui, sans-serif; }
    main { max-width: 760px; margin: 0 auto; }
    h1 { font-size: 1.2rem; margin: 0 0 12px; }
    h2 { font-size: 0.95rem; margin: 18px 0 6px; color: #9da7b1; font-weight: 600; }
    select { font-size: 1rem; padding: 6px 8px; background: #23272c; color: inherit; border: 1px solid #3a4047; border-radius: 6px; }
    canvas { width: 100%; max-width: 480px; background: #000; border-radius: 6px; display: block; margin-top: 12px; }
    .chip { display: inline-block; padding: 3px 10px; border-radius: 12px; color: #fff; font-size: 0.9rem; margin: 2px 6px 2px 0; }
    .ok { background: #777777; } .near { background: #b8862f; } .over { background: #bd5555; }
    .inactive, .unknown { background: #5a626b; } .present { background: #5b9d61; }
    ul { list-style: none; padding: 0; margin: 0; } li { padding: 3px 0; }
    #freshness.stale { color: #e8b04e; font-weight: 600; }
    footer { margin-top: 24px; font-size: 0.8rem; color: #808891; }
  </style>
</head>
<body>
<main>
  <h1>SmartMat</h1>
  <label for="mat">Mat: </label><select id="mat"></select>
  <p id="info"></p>
  <div id="live" hidden>
    <span id="patient" class="chip unknown"></span><span id="freshness"></span>
    <canvas id="heatmap" width="480" height="512"></canvas>
    <p id="unit"></p>
    <h2>Active hotspots</h2><ul id="hotspots"></ul>
    <h2>Indices</h2><ul id="indices"></ul>
  </div>
  <footer>Read-only view of the SmartMat desktop app. An engineering aid, not a medical device:
    indices are user-defined and not validated.</footer>
</main>
<script>
  var select = document.getElementById("mat");
  var canvas = document.getElementById("heatmap");
  var ctx = canvas.getContext("2d");

  function byId(id) { return document.getElementById(id); }

  function colorFor(v) {            // white -> green -> red, like the desktop heatmap
    v = Math.max(0, Math.min(1, v));
    if (v < 0.5) { var f = v / 0.5; return "rgb(" + Math.round(255 * (1 - f)) + "," + Math.round(255 - 127 * f) + "," + Math.round(255 * (1 - f)) + ")"; }
    var g = (v - 0.5) / 0.5; return "rgb(" + Math.round(255 * g) + "," + Math.round(128 * (1 - g)) + ",0)";
  }

  function fillList(id, lines, empty) {
    var list = byId(id);
    list.textContent = "";
    (lines.length ? lines : [{ text: empty }]).forEach(function (line) {
      var item = document.createElement("li");
      if (line.state) {
        var chip = document.createElement("span");
        chip.className = "chip " + line.state;
        chip.textContent = line.state;
        item.appendChild(chip);
      }
      item.appendChild(document.createTextNode(line.text));
      list.appendChild(item);
    });
  }

  function drawGrid(mat, snap) {
    var cellW = canvas.width / mat.cols, cellH = canvas.height / mat.rows;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    snap.grid.forEach(function (row, r) {
      row.forEach(function (value, c) {
        ctx.fillStyle = value === null ? "#333" : colorFor(value / snap.scale_max);
        ctx.fillRect(c * cellW + 1, r * cellH + 1, cellW - 2, cellH - 2);
      });
    });
    ctx.lineWidth = 3;
    snap.hotspots.forEach(function (spot) {
      ctx.strokeStyle = spot.persistent ? "#ff3b3b" : "#ffa726";
      spot.cells.forEach(function (cell) { ctx.strokeRect(cell[1] * cellW + 1, cell[0] * cellH + 1, cellW - 2, cellH - 2); });
    });
  }

  function show(mat) {
    var snap = mat.snapshot;
    byId("live").hidden = !snap;
    if (!mat.live) { byId("info").textContent = mat.name + " (" + mat.id + ", " + mat.rows + " x " + mat.cols + "): not open in the desktop app."; return; }
    if (!snap) { byId("info").textContent = mat.name + ": connected, waiting for data."; return; }
    byId("info").textContent = mat.name + " (" + mat.rows + " x " + mat.cols + ")";
    var patient = byId("patient");
    patient.textContent = snap.occupied === true ? "Patient detected" : snap.occupied === false ? "No patient" : "Patient: unknown";
    patient.className = "chip " + (snap.occupied === true ? "present" : "unknown");
    var fresh = byId("freshness");
    fresh.textContent = mat.stale ? "No new data for " + Math.round(mat.age_s) + " s - this picture is old" : "updated " + Math.round(mat.age_s) + " s ago";
    fresh.className = mat.stale ? "stale" : "";
    byId("unit").textContent = snap.unit === "kPa" ? "Pressure in kPa, full colour at " + snap.scale_max + " kPa." : "Not calibrated: relative sensor signal, not pressure.";
    drawGrid(mat, snap);
    fillList("hotspots", snap.hotspots.map(function (spot) {
      return { text: "#" + spot.id + ": peak " + spot.peak_kpa + " kPa, active " + Math.round(spot.active_s) + " s" + (spot.persistent ? " (persistent)" : "") };
    }), "None");
    fillList("indices", snap.indices.map(function (item) {
      return { state: item.state, text: item.name + ": " + (item.value === null ? "-" : item.value.toFixed(2)) + " (threshold " + item.threshold + ")" };
    }), "None defined");
  }

  function refreshMats() {
    return fetch("/api/mats", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (data) {
      var chosen = select.value;
      select.textContent = "";
      data.mats.forEach(function (mat) {
        var option = document.createElement("option");
        option.value = mat.id;
        option.textContent = mat.name + (mat.live ? " (live)" : "");
        select.appendChild(option);
      });
      var live = data.mats.filter(function (mat) { return mat.live; })[0];
      var ids = data.mats.map(function (mat) { return mat.id; });
      select.value = ids.indexOf(chosen) >= 0 ? chosen : (live ? live.id : (ids[0] || ""));
      if (!ids.length) { byId("live").hidden = true; byId("info").textContent = "No mats known yet. Connect a source in the desktop app."; }
    });
  }

  function refresh() {
    refreshMats().then(function () {
      if (!select.value) { return; }
      return fetch("/api/mats/" + encodeURIComponent(select.value), { cache: "no-store" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (mat) { if (mat) { show(mat); } });
    }).catch(function () { byId("live").hidden = true; byId("info").textContent = "Cannot reach the SmartMat desktop app."; });
  }

  select.addEventListener("change", refresh);
  setInterval(refresh, 1000);
  refresh();
</script>
</body>
</html>
"""
```

- [ ] **Step 4: `tests/test_multi_mat.py`** - delete the line `self.assertIn("var ROWS = 20;", web.index())` and the now-unused `from gui import web` import.

- [ ] **Step 5: Run** - `python -m unittest discover -s tests -p "test_web.py" -v` -> the 6 store/address tests and 4 snapshot tests pass; the 3 desktop tests fail (`_publish_web`), fixed in Task 2.

---

### Task 2: Desktop feeds the dashboard

**Files:**
- Modify: `gui/desktop.py`

**Interfaces:**
- Consumes: `web.update`, `web.build_snapshot` (Task 1); `self._mats`, `self.mat_names`, `self.source`, `self.frame`, `self.hotspots.active`, `self.occupancy.occupied`, `self.indices`.
- Produces (on `DesktopApp`): `_publish_web(force=False)`, `web_address_var`; module function `_web_address()`.

- [ ] **Step 1: Address helper** - below `_get_local_ip()`:

```python
def _web_address():
    """Where the web dashboard is reached: the mDNS name, with the plain IP as a fallback"""
    return (f"http://{socket.gethostname()}.local:{WEB_PORT}", f"http://{_get_local_ip()}:{WEB_PORT}")
```

- [ ] **Step 2: About panel** - replace the two lines `self._info_line(panel, f"Host IP: {_get_local_ip()}")` and `self._info_line(panel, f"Web UI port: {WEB_PORT}")` with:

```python
        self.web_address_var = tk.StringVar(value="Web UI:\n{}\nor {}".format(*_web_address()))
        ttk.Label(panel, textvariable=self.web_address_var, wraplength=190).pack(anchor="w")
```

- [ ] **Step 3: Status text** - in `_toggle_web_ui` replace the `self.status_var.set(...)` line with `self.status_var.set(f"Web UI running at {_web_address()[0]}")`.

- [ ] **Step 4: Publisher** - in `__init__` add `self._last_web_publish = 0.0` next to `self._last_index_update = 0.0`, and add below `_toggle_web_ui`:

```python
    def _publish_web(self, force=False):
        """Send the known mats and a snapshot of the connected one to the web dashboard"""
        now = time.time()
        if not force and now - self._last_web_publish < 1.0:
            return
        self._last_web_publish = now
        mats = [{"id": chip_id, "name": self.mat_names.get(chip_id) or chip_id, "rows": rows, "cols": cols}
                for chip_id, (rows, cols) in sorted(self._mats.items())]
        live_id = None
        if self.source is not None:
            live_id = getattr(self.source, "chip_id", None)
            if live_id is None:  # Serial, Simulated or a recording: one entry of its own
                live_id = "local"
                mats.append({"id": live_id, "name": f"{self.source_var.get()} ({self.device_var.get()})",
                             "rows": app_config.TOTAL_ROWS, "cols": app_config.TOTAL_COLS})
        snapshot = None
        if live_id is not None and self.frame is not None:
            snapshot = web.build_snapshot(self.frame, self.hotspots.active, self.occupancy.occupied, self.indices)
        web.update(mats, live_id, snapshot)
```

- [ ] **Step 5: Hooks**
  - In `_handle_new_frame` replace `web.update_grid(self.current_grid)` with `self._publish_web()`.
  - In `_apply_grid_shape` replace `web.update_grid(None)` with `self._publish_web(force=True)`.
  - In `_connect`, right after `self.status_var.set(f"Connected via {source_name} ({device}){replay_label}")`, and at the end of the `except Exception as error:` block: `self._publish_web(force=True)`.
  - At the end of `_disconnect`: `self._publish_web(force=True)`.
  - In `_sync_mats`, after `self._mats = dict(self._discovery.mats)`: `self._publish_web(force=True)`.
  - At the end of `_rename_mat`: `self._publish_web(force=True)`.
  - In `_on_close`, before `if self.web_server is not None:`: `web.update([])`.

- [ ] **Step 6: Run everything** - `python -m unittest discover -s tests -v` -> 147 tests, OK.

---

### Task 3: Docs

**Files:**
- Modify: `Raspberry Pi/STATUS.md`, `Raspberry Pi/notes.md`, `Raspberry Pi/README.md`

- [ ] **Step 1:** `notes.md`: delete the "Web UI's `/` page is a temporary..." line, the "/data's CORS header is wide open" line, the "Remove Share live data entirely" line, and the two "Web UI:" bullets under larger design passes. Add: the dashboard is built; the planned next step (a background listener per known mat for a live raw heatmap of mats the desktop does not have open); the public website widget still points at the removed `/data`; `.local` not yet confirmed on the deployed Pi. Update the patient-indicator and custom-indices lines, which say "not in the web UI".
- [ ] **Step 2:** `STATUS.md`: rewrite the `web.py` entry and add the spec/plan under design docs as built.
- [ ] **Step 3:** `README.md`: one sentence on opening `http://<hostname>.local:8000` from another device on the same network.
- [ ] **Step 4: Final run** - `python -m unittest discover -s tests -v` -> 147 tests, OK. Then start the app on the Simulated source and fetch `/`, `/api/mats` and `/api/mats/local` from the running server.
