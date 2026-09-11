# SmartMat desktop app

A Tkinter app for viewing, calibrating, and recording the pressure-mat heatmap - from the
real ESP32 (Serial or MQTT), or from fake data (Simulated) when testing without hardware.

## Running it

    pip install -r requirements.txt
    python main.py

(Copy `config.example.py` to `config.py` first and fill in your MQTT broker details if you
plan to use the MQTT source.)

## How a frame flows through the app

1. A **source** (`sources/serial_source.py`, `mqtt_source.py`, `simulated_source.py`) runs on
   its own background thread and produces a validated grid of pressure values roughly 10
   times a second, storing the newest one in a `LatestFrame` (`general.py`) - a small
   thread-safe box.
2. The GUI (`gui/desktop.py`) polls that box every 50ms (`_poll`). Each new grid is run
   through the active processing **mode** (`processing/modes.py`), then baseline-corrected
   by `Calibration`, then: fed to the active `Recorder` if one is running, handed to the
   local web server, and (unless paused) drawn on the plot.

## Modules

- **`config.py`** (gitignored - copy `config.example.py`) - MQTT broker secrets, and every
  other setting worth tuning without digging through code: grid size (`TOTAL_ROWS`/
  `TOTAL_COLS`), value range, serial baud rate, the web server port, and the staleness/
  auto-reconnect timings. The grid size and baud rate must match `SmartMat_Resistive/src/main.cpp`
  on the ESP32.
- **`general.py`** - shared, dependency-light pieces every source uses: frame
  parsing/validation (`parse_frame_text`) and `LatestFrame`.
- **`sources/`** - one module per data source. Each exposes a class with `.start()`, `.stop()`,
  and `.latest` (a `LatestFrame`), so the GUI treats all three the same way.
  `simulated_source.py` also has a few named scenarios (`SCENARIOS`) - a drifting blob, a bad
  distribution, a good distribution, and a hand-press shape - plus `pause()`/`resume()` so a
  played-back recording can freeze on an exact frame instead of skipping ahead.
- **`processing/`** - logic with no GUI dependency, so a future web UI can reuse it as-is:
  `calibration.py` (the display range, its auto-scale toggle, and an optional baseline grid
  subtracted from every future frame), `modes.py` (Live / rolling average / exponential
  average, each with at most one adjustable parameter), and `recording.py` (saving/loading
  named sessions as CSV under `recordings/`, gitignored - one row per frame).
- **`gui/desktop.py`** - the Tkinter window itself.
- **`gui/web.py`** - a small local Flask server, off by default, toggled from the desktop app.
  Serves a live heatmap page (temporary - just for testing) plus a `/data` endpoint, which is
  what the public website's live heatmap mode actually pulls from.

## Desktop app controls

- **Source / Device** - pick Serial (USB), MQTT, or Simulated (a named scenario, or a
  recorded `.csv` session), then **Connect**. The status label next to Connect shows whether
  the connection is healthy or has gone stale.
- **Plot** - switch between a 2D heatmap and a 3D surface.
- **Mode** - Live (no processing), Average (rolling mean over the last N frames), or
  Exponential average (same idea as the ESP32 firmware's own smoothing) - each shows its one
  adjustable parameter next to the dropdown.
- **Reset** - put the display range back to the default, clear any calibration baseline, and
  turn Auto-scale off.
- **Calibrate / View calibration** - capture the current reading as a zero-point baseline
  (subtracted from every future frame), and open a window showing that baseline grid.
- **Record** - start/stop a named recording session, saved as CSV to `recordings/`; the
  status bar shows elapsed time and frame count while recording, and confirms (or reports a
  failure) once saved.
- **Auto-scale** - continuously rescale the display range to the live data's min/max.
- **Pause** - freeze the display without stopping an active recording; for a live source,
  unpausing jumps to whatever's currently coming in, while a played-back recording actually
  pauses and resumes at the exact next frame.
- **Show numbers** - overlay each cell's value (divided by 10, so roughly 0-100) on the 2D
  heatmap.
- **Auto-reconnect** - if the connection goes stale (`STALE_AFTER_S` in `config.py`, default
  10s), automatically retry every `RECONNECT_INTERVAL_S` seconds (default 3) until data
  resumes.
- **Web UI** - start/stop the local web server (see `gui/web.py`).
- **Share live data** - while the Web UI is running, whether `/data` actually returns the
  live grid or reports itself offline.

The **About** panel on the right shows the live FPS plus a few static facts about the grid,
firmware assumptions, and app settings (including the host's LAN IP, for reaching the Web UI
from another device).

## Connecting to the public website

The `Website/` widget's "Live" mode fetches `/data` from wherever this app's Web UI is
running. Since that's normally just on your LAN, it needs a tunnel to be reachable from the
internet - a Cloudflare Tunnel is the easiest way to test this:

    winget install --id Cloudflare.cloudflared
    cloudflared tunnel --url http://localhost:8000

That prints a public HTTPS URL - paste `<that url>/data` into `LIVE_DATA_URL` in the widget.
The free "quick tunnel" URL changes every time `cloudflared` restarts, so for anything
longer-term than a one-off test, a named Cloudflare tunnel (stable URL, needs a free
Cloudflare account) is worth setting up instead.
