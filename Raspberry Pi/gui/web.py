"""Local web server, off by default and toggled from the desktop app.
Serves a live heatmap page, and (once "sharing" is on) a /data endpoint
with the current grid - what the public website's live mode pulls from.
"""

import threading

from flask import Flask, jsonify
from werkzeug.serving import make_server

from config import WEB_PORT, VALUE_MAX_DEFAULT, TOTAL_ROWS, TOTAL_COLS

app = Flask(__name__)

_lock = threading.Lock()
_grid = None
_sharing = False


def update_grid(grid):
    """Called by the GUI on every new frame, so /data has something to serve"""
    global _grid
    with _lock:
        _grid = grid


def set_sharing(sharing):
    """Turn the /data endpoint's live output on or off"""
    global _sharing
    with _lock:
        _sharing = sharing


# TEMPORARY page - just renders /data so there's something to look at while
# testing. Replace with the real public-facing page later.
_INDEX_PAGE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>SmartMat (temporary)</title>
  <style>
    body {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      height: 100vh; margin: 0; background: #111; font-family: sans-serif; color: #ccc;
    }
    canvas { background: #000; border-radius: 6px; }
    p { margin-top: 12px; }
  </style>
</head>
<body>
  <canvas id="heatmap" width="450" height="480"></canvas>
  <p id="status">Waiting for data...</p>
  <script>
    var ROWS = __ROWS__;
    var COLS = __COLS__;
    var canvas = document.getElementById("heatmap");
    var ctx = canvas.getContext("2d");
    var statusEl = document.getElementById("status");
    var cellW = canvas.width / COLS;
    var cellH = canvas.height / ROWS;

    function colorFor(v) {
      v = Math.max(0, Math.min(1, v));
      if (v < 0.5) {
        var f = v / 0.5;
        return "rgb(0," + Math.round(163 * f) + ",0)";
      }
      var f2 = (v - 0.5) / 0.5;
      var r = Math.round(12 + (208 - 12) * f2);
      var g = Math.round(163 + (59 - 163) * f2);
      return "rgb(" + r + "," + g + "," + Math.round(59 * f2) + ")";
    }

    function refresh() {
      fetch("/data", { cache: "no-store" })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (data.status !== "live") {
            statusEl.textContent = "Offline - no live data being shared";
            return;
          }
          statusEl.textContent = "Live";
          ctx.fillStyle = "#000";
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          for (var row = 0; row < ROWS; row++) {
            for (var col = 0; col < COLS; col++) {
              ctx.fillStyle = colorFor(data.grid[row * COLS + col]);
              ctx.fillRect(col * cellW + 1, row * cellH + 1, cellW - 2, cellH - 2);
            }
          }
        })
        .catch(function () { statusEl.textContent = "Could not reach /data"; });
    }
    setInterval(refresh, 300);
    refresh();
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return _INDEX_PAGE.replace("__ROWS__", str(TOTAL_ROWS)).replace("__COLS__", str(TOTAL_COLS))


@app.route("/data")
def data():
    """The live grid (flattened, normalized 0-1), or an offline status - never fake data"""
    with _lock:
        sharing, grid = _sharing, _grid
    if not sharing or grid is None:
        return jsonify({"status": "offline"})
    normalized = (grid.flatten() / VALUE_MAX_DEFAULT).tolist()
    return jsonify({"status": "live", "grid": normalized})


@app.after_request
def add_cors_headers(response):
    """Allow the public website (a different origin) to read /data"""
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


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
