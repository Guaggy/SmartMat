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
