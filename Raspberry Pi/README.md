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
   its own background thread. Live data uses `LatestFrame`; playback uses `QueuedFrames`
   so faster playback does not discard frames before processing.
2. The GUI (`gui/desktop.py`) polls that box every 50ms (`_poll`). Live and playback grids
   both enter `processing/frames.py`, which keeps separate copies of the received grid,
   the selected processing mode's output, the baseline-subtracted grid, calibrated pressure,
   and tare-corrected pressure. The raw received grid goes to the recorder. The selected
   data mode goes to the plot; the baseline-subtracted grid still goes to the local web feed.
   The ESP32 may already filter values before transmission; "raw" means as received by the app.

## Modules

- **`config.py`** (gitignored - copy `config.example.py`) - MQTT broker secrets, and every
  other setting worth tuning without digging through code: grid size, value range, serial
  baud rate, cell dimensions, contact threshold, pressure plot range, history length,
  web server port, and connection timings.
- **`general.py`** - shared, dependency-light pieces every source uses: frame
  parsing/validation (`parse_frame_text`), `LatestFrame`, and `QueuedFrames`.
- **`sources/`** - one module per data source. Each exposes a class with `.start()`, `.stop()`,
  and `.latest`, so the GUI treats all three the same way.
  `simulated_source.py` also has a few named scenarios (`SCENARIOS`) - a drifting blob, a bad
  distribution, a good distribution, and a hand-press shape - plus `pause()`/`resume()` so a
  played-back recording can freeze on an exact frame instead of skipping ahead.
- **`processing/`** - logic with no GUI dependency, so a future web UI can reuse it as-is:
  `calibration.py` (display scaling, tare, and per-sensor pressure curves), `modes.py`
  (Live / rolling average / exponential average), `frames.py` (separate processing stages),
  `statistics.py` (contact mask, force, and CoP), and `recording.py` (raw JSON sessions with
  timestamps and metadata; older CSV and JSON sessions still play back). The `recordings/`
  folder is gitignored.
- **`processing/display.py`** - optional nearest or linear plot interpolation. Real-cell
  frames remain unchanged.
- **`processing/sensor_health.py`** - bounded received-value history for variance, unloaded
  noise, drift, saturation, missing/invalid values, and conservative stuck warnings.
- **`processing/analysis.py`** - ROI statistics, pressure distributions, load fractions,
  and symmetry calculations on real cells.
- **`gui/desktop.py`** - the Tkinter window itself.
- **`gui/calibration_window.py`** - the per-sensor pressure calibration editor.
- **`gui/analysis_window.py`** and **`gui/diagnostics_window.py`** - secondary analysis
  and engineering views.
- **`gui/web.py`** - a small local Flask server, off by default, toggled from the desktop app.
  Serves a live heatmap page (temporary - just for testing) plus a `/data` endpoint, which is
  what the public website's live heatmap mode actually pulls from.

## Desktop app controls

- **Source / Device** - pick Serial (USB), MQTT, or Simulated (a named scenario, or a
  recorded `.csv` or `.json` session), then **Connect**. The status label next to Connect shows whether
  the connection is healthy or has gone stale.
- **Plot** - switch between a 2D heatmap and a 3D surface.
- **Mode** - Live (no processing), Average (rolling mean over the last N frames), or
  Exponential average (same idea as the ESP32 firmware's own smoothing) - each shows its one
  adjustable parameter next to the dropdown.
- **Data** - choose Raw / received, Processed, Baseline subtracted, or Calibrated pressure.
  Pressure mode shows a clear message until every cell has a pressure calibration.
- **Tare / View tare** - capture the current reading as a baseline, or inspect it. **Reset**
  clears tare and display scaling, while leaving pressure calibration intact.
- **Pressure calibration...** - choose a cell, record its zero offset and known pressure
  points, select a linear or piecewise curve, inspect it, and save/load JSON calibration.
  Known loads in newtons can be entered when cell dimensions are configured; conversion
  assumes the load acts over the selected cell's full area. Copying a
  curve to all sensors is an explicit option for test setups; calibrating each sensor is
  preferred for real measurements. Linear calibration fits a slope through the entered
  offset; piecewise calibration interpolates between the points and holds its last value
  above the measured range.
- **Contact >** - set the pressure threshold in kPa. The Live pressure panel uses it for
  contact area, mean contact pressure, total force, and center of pressure. Force and area
  in physical units require `CELL_WIDTH_MM` and `CELL_HEIGHT_MM` in `config.py`; until then,
  contact area is shown as a count of cells.
- **Show CoP** - overlay the pressure-weighted center on the 2D heatmap. Click a 2D cell
  to open its selected-data-mode history. New recordings use saved sample times; older
  sessions use their nominal 0.1-second frame spacing. History resets on cell, source,
  or recording loop change.
- **Record** - start/stop a named recording session, saved as JSON to `recordings/`; the
  status bar shows elapsed time and frame count while recording, and confirms (or reports a
  failure) once saved. Each session stores received frames, GUI receipt timestamps, source,
  grid size, and a snapshot of calibration, tare, and processing settings when recording
  starts. Playback applies the currently selected processing and calibration settings;
  the saved snapshot remains available in the JSON file for experiment review.
- **Playback** - when a recording is connected, choose 0.25x, 0.5x, 1x, 2x, or 5x. New
  recordings use their timestamps; old sessions use the previous fixed 10 fps rate at 1x.
- **Auto-scale** - continuously rescale the display range to the live data's min/max.
- **Pause** - freeze the display without stopping an active recording; for a live source,
  unpausing jumps to whatever's currently coming in, while a played-back recording actually
  pauses and resumes at the exact next frame.
- **Show numbers** - overlay the selected data mode's cell values on the 2D heatmap.
- **Plot options...** - choose original, nearest, or linear display interpolation (scale
  1-10), optional subtle contours, and a real-cell contact boundary. Pressure contour
  levels are in kPa. Capture a real-grid reference to show current minus reference in the
  same data mode; clear it to return to the normal heatmap.
- **Analysis...** - choose two 2D cells as opposite corners of a rectangular ROI, then
  inspect real-cell ROI statistics and mean/peak history. The Distribution tab shows a
  contacted-cell histogram, cumulative percentiles, and pressure-area curve. Load and
  symmetry shows left/right, upper/lower, and quadrant percentages. The center column
  of the 15-column grid contributes half to each side.
- **Diagnostics...** - inspect sensor-health, unloaded noise, or drift heatmaps. Click a
  cell for numeric diagnostics. The selected-cell history window also shows received,
  processed, tare, pressure, recent variance/noise/drift, and calibration state.
- **Auto-reconnect** - if the connection goes stale (`STALE_AFTER_S` in `config.py`, default
  10s), automatically retry every `RECONNECT_INTERVAL_S` seconds (default 3) until data
  resumes.
- **Web UI** - start/stop the local web server (see `gui/web.py`).
- **Share live data** - while the Web UI is running, whether `/data` actually returns the
  live grid or reports itself offline.

The **About** panel on the right shows the live FPS plus a few static facts about the grid,
firmware assumptions, and app settings (including the host's LAN IP, for reaching the Web UI
from another device).

## Phase 3 measurement notes

Interpolation only changes the drawn 2D/3D field and contour placement. Contact, CoP,
ROI area, force, distributions, and load fractions always use the 16 x 15 sensor cells.
The histogram uses cells above the configured kPa contact threshold. Cumulative 90/95/99%
values use the nearest observed rank, so at least that fraction of contacted cells is below
the reported pressure. The pressure-area curve counts positive calibrated cells above each
plotted pressure threshold. Signed symmetry imbalance is `(side A - side B) / total * 100`.

Noise is the rolling standard deviation of received values while a cell appears unloaded.
Drift compares recent unloaded readings with an early unloaded reference and waits for the
configured minimum duration. Occupied cells are excluded from drift assessment. Stuck
requires a nearly constant extreme reading and varying neighbors over many frames; it is
shown as **Possible stuck**, not a defect diagnosis. All health windows are bounded by
`HEALTH_WINDOW_FRAMES` in `config.py`, alongside the other diagnostic thresholds.

Serial and MQTT currently reject malformed packets before per-cell processing. The health
system can flag missing or invalid cell values when they are provided to it, but a dropped
whole packet cannot identify which cell caused it. New raw recordings store missing values
as JSON `null`, so they can be inspected again during playback. These diagnostics are
engineering aids, not validated clinical decisions.

## Temporal analysis

**Temporal...** opens calibrated pressure, exposure, experimental burden, and relief
maps without crowding the main dashboard. Select Session or a recent 1/5/15/30/60
minute window. Click a cell on either heatmap; select an ROI on the main 2D heatmap.
The temporal window shows cell and ROI values, a selectable history plot, reset
buttons, editable analysis parameters, and manual event markers. **Diagnostics...**
also shows packet counts, rejection reasons, frame rate, and age of the last valid
frame. Source packets have no timestamps, so that field reports their absence.

Exposure is the trapezoidal integral of real calibrated cell pressure in kPa·min.
Above-threshold mode integrates `max(0, average_pressure - threshold) * dt / 60`.
Experimental burden decays by `exp(-dt / recovery_time_s)` and then adds
`max(0, average_pressure - load_threshold) * rate * dt / 60`. Relief compares
pressure with the highest observed pressure for each cell in the session. A cell
is partially relieved below the partial ratio and fully relieved below the full
ratio, after the minimum duration. ROI relief means at least the configured
fraction of ROI cells are fully relieved. These are engineering measures, not
validated clinical risk estimates.

Missing packets and invalid cells do not become zero pressure or relief. An
interval above `TEMPORAL_MAX_GAP_S` is skipped, as is the first interval after a
known malformed or dropped packet. Playback uses recorded timestamps at every
speed; pause adds no physical time. Looping a recording resets temporal state.
Recent windows use 10-second buckets for bounded memory, so window edges have
up to one bucket of timing granularity. Recordings spool raw frames to disk while
recording and save the analysis settings and event markers with the session.

## Hotspots, movement, and replayed state changes

**Show hotspots** adds boundaries and IDs to the calibrated-pressure 2D map.
Orange means newly active; red means the configured persistence duration has
been reached. **Hotspots...** lists current and recently relieved regions.
Detection uses four-neighbor connected real cells, a minimum cell count, and
separate activation/deactivation pressure thresholds. IDs are matched by cell
overlap first, then centroid distance. A merged region keeps one ID; a split
region keeps the best match and gives the other region a new or resumed ID.

**Movement...** shows the current movement components, significant movement
events, confirmed repositions, and the event timeline. The movement score is
the maximum of normalized map change, CoP travel divided by its configured
scale, and fractional contact-cell change. A reposition requires a significant
movement, a settling interval, and an after-window distribution that remains
different from the before window. Both windows must contain the configured
minimum number of contacted cells, so first loading is not a reposition.
Its detail view reports components rather
than a clinical success score. Selecting **Show after - before** uses the
existing difference heatmap. The before/after analysis keeps one-second rolling
grid summaries; full frame history is not retained.

Recording events now include the next frame index as well as a timestamp.
Tare captures, baseline clears, calibration edits/loads, processing changes,
contact threshold changes, and temporal parameter changes carry the state
needed to replay them before that frame. Initial state remains in recording
metadata. Playback uses temporary calibration, tare, temporal, hotspot, and
movement state; **Disconnect** or connecting another source restores the
live configuration. Older recordings without timed state events still load.

## Engineering validation (Phase 6)

**Engineering...** contains editable contact, hotspot, movement, reposition, and
temporal settings. **Apply values** takes effect immediately; it restarts hotspot
and movement tracking because their earlier state cannot be reconstructed from
the new thresholds. A timed settings event is saved while recording. Built-in
Default, Sensitive, Conservative, and Experimental presets are engineering
starting points. Save and load custom presets as readable JSON. The optional
hotspot activation contour is drawn only on the calibrated 2D pressure map.

Use **Annotate...** for load changes, known repositions, known hotspot ROIs,
and experiment notes. A known reposition may include before and after notes.
The Validation tab pairs each known reposition with at most one automatic
detection within the chosen time window; it reports missed annotations,
unpaired detections, and signed timing error. A hotspot ROI annotation records
its overlap and centroid distance from the nearest current hotspot. These
annotations are reference observations and do not change detection.

The Session tab shows source quality, calibration and baseline readiness,
algorithm counts, exposure, burden, and unknown temporal state. It exports a
machine-readable JSON summary. Optional experiment fields are saved in the
recording metadata. The Debug tab shows the latest movement components and
reposition decision; **Hotspots...** has per-region tracking details.

Playback offers **Reproduce recording** and **Re-analyze with current settings**.
Changing the choice restarts playback from its first frame. Reproduction uses
the recorded initial algorithm settings and timed changes. Re-analysis uses
current tuned settings and ignores recorded algorithm parameter changes while
still replaying calibration and tare changes. Live settings return when playback
ends. **Compare recorded and current settings** computes hotspot, movement,
and reposition event counts from raw frames on demand in the background; the
recording is not edited. Older recordings without timestamps use 0.1-second
frame spacing for this comparison.

A hotspot observed in the first valid frame is marked as already present, with
unknown earlier duration. Its displayed duration is only the time observed in
this session. No earlier relief is inferred. Session and recording startup
snapshots preserve what was known about calibration, tare, occupancy, source,
and active regions.

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
