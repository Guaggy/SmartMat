# STATUS.md - context doc for Claude, not for humans

Purpose: let a fresh session get oriented on the Pi app without re-reading every
file. Backlog detail lives in `notes.md` (human + Claude) - this file is the
architecture map, conventions, and pointers. Keep this updated when the
backlog in `notes.md` changes shape significantly; don't duplicate its content
here.

## What this is

Tkinter desktop app that visualizes a live pressure-sensor mat for
pressure-injury-prevention use (sitting posture, for now). Reads frames from
an ESP32 over MQTT/Serial (or simulated/recorded data), runs them through
calibration + analysis + detection algorithms, displays heatmaps and derived
metrics, and can record/export sessions. Explicitly not a medical device -
see README's "Not a medical device" section before changing any
risk/exposure-adjacent wording or defaults.

## Data flow

```
ESP32 --MQTT/Serial--> sources/*Source --> processing/frames.process_frame()
  --> mode (modes.py) --> tare baseline (calibration.Calibration)
  --> pressure calibration (calibration.PressureCalibration) --> kPa
  --> statistics/analysis/temporal/hotspots/motion/sensor_health
  --> gui/desktop.py main view + tool windows --> optional recording
```

## File map

`processing/` (the algorithms):
- `frames.py` - per-frame pipeline: raw -> mode -> baseline -> pressure.
- `modes.py` - Live / rolling-Average / Exponential-average smoothing.
- `calibration.py` - `Calibration` (tare/display range) + `PressureCalibration`
  (per-cell raw->kPa curves, linear or piecewise) + `UniformCalibration` (one
  shared curve applied to the whole grid at once). `DesktopApp.pressure_calibration`
  points at whichever profile is active; tare also recalibrates both.
- `statistics.py` - shared primitives (contact mask, weighted center, basic
  pressure stats) used by nearly everything else.
- `analysis.py` - ROI stats (over a cell mask), pressure-distribution
  histogram, whole-mat left/right/upper/lower load-balance split.
- `roi.py` - an ROI is a boolean mask of cells (`DesktopApp.roi`, set only
  through `set_roi`); builders for box/polygon/paint-stroke masks, and
  `roi_balance` (load share around the region's own centre, right/up positive).
- `temporal.py` - per-cell exposure (kPa*min), burden (load/decay), 4-state
  relief state machine, rolling windows. Densest math in the codebase.
- `hotspots.py` - connected-component (flood fill) high-pressure region
  tracking with frame-to-frame ID matching (merge/split/relief/resume).
- `motion.py` - per-frame movement score + a before/settle/after sustained-
  redistribution check for reposition detection.
- `signals.py` - registry of named signals (cell grids or whole-mat numbers)
  read from temporal/hotspots/motion; no math of its own.
- `indices.py` - user-defined indices: weighted combinations of signals in
  two fixed layers (map = grid, summary = one number), their validation, and
  `IndexMonitor` (OK/near/over warning state with a hold time; inactive when
  no patient is detected). Definitions are plain dicts stored under
  `"indices"` in the engineering settings, so presets/recordings carry them.
- `occupancy.py` - "Patient detected / No patient / unknown" from the
  contact-cell count with enter/exit hold times (status-bar indicator).
- `sensor_health.py` - per-cell rolling diagnostics -> one of 8 states
  (Healthy/Noisy/Drifting/Saturated/Possible stuck/Missing/Invalid/
  Uncalibrated).
- `source_quality.py` - packet-level health (rate, drops, malformed) shared
  by all live sources.
- `recording.py` / `session_state.py` / `session_summary.py` / `timeline.py` -
  save/load sessions, session-start snapshot, end-of-session report, flat
  event log.
- `reanalysis.py` - replays recorded state-change events during playback.
- `settings.py` - engineering presets, validate/save/load/apply settings for
  temporal + hotspots + motion.
- `display.py` - plot-only interpolation (does not affect any statistic).
- `validation.py` - compares manual "Known reposition" annotations against
  auto-detected repositions/hotspots, for engineering validation.

`gui/` (Tkinter):
- `desktop.py` - main window, source/device selection, main plot, toggles.
- One file per tool window: `calibration_window.py`, `analysis_window.py`,
  `diagnostics_window.py`, `temporal_window.py`, `hotspot_window.py`,
  `motion_window.py`, `engineering_window.py`, `annotation_window.py`,
  `roi_window.py` (ROI selection on a frozen snapshot + all ROI output),
  `indices_window.py` (live index values), `index_editor.py` (the Indices tab
  inside the Engineering window),
  `help_window.py`.
- `web.py` - local read-only Flask dashboard toggled from the desktop app
  ("Web UI"). The desktop is the only producer: `_publish_web()` calls
  `web.update(mats, live_id, snapshot)` about once a second. Addresses: `/`
  (static page that polls), `/api/mats`, `/api/mats/<id>`. Only the mat the
  desktop is connected to has data; non-MQTT sources appear as id `local`.

`sources/` - `mqtt_source.py`, `serial_source.py`, `simulated_source.py`, all
expose the same `latest`/`quality`/`start`/`stop` shape. `MqttSource(chip_id)`
streams one mat (`smartmat/<chip_id>/frame`) and will not start without that
mat's retained meta message; `MqttSource()` with no chip ID only listens on
`smartmat/+/meta` to fill the device list.

`general.py` - frame parsing, plus the mat nickname registry (`mats.json`,
gitignored, `{chip_id: nickname}`).

`config.py` (gitignored, copy from `config.example.py`) holds every
threshold/constant used by the modules above, and the default grid size.
`config.TOTAL_ROWS`/`TOTAL_COLS` are overwritten at runtime when an MQTT mat of
another size connects (`DesktopApp._apply_grid_shape`, which also restarts
everything sized to the old grid) and set back for Serial/Simulated. Always
read them as `config.TOTAL_ROWS` - a `from config import TOTAL_ROWS` copy goes
stale. `sources/simulated_source.py` is the one deliberate exception.

## Active design docs

- `docs/superpowers/specs/2026-10-07-multi-mat-mqtt-design.md` - chip-ID MQTT
  topics, retained grid-shape handshake, `mats.json` nickname registry.
  Built 2026-10-08 from `docs/superpowers/plans/2026-10-08-multi-mat-mqtt.md`
  (that plan also lists where the spec did not match the code). Automated
  tests in `tests/test_multi_mat.py`; the two-board hardware check at the end
  of the plan has not been run yet.

- `docs/superpowers/specs/2026-10-08-custom-indices-design.md` - signal
  registry, weighted map/summary indices, near-threshold warnings. Built
  2026-10-08 from `docs/superpowers/plans/2026-10-08-custom-indices.md` (which
  lists where the spec did not match the code). Tests in `tests/test_indices.py`.

- `docs/superpowers/specs/2026-10-08-roi-window-design.md` - cell-set ROI and
  the ROI window. Built 2026-10-08 from
  `docs/superpowers/plans/2026-10-08-roi-window.md`. Tests in `tests/test_roi.py`.

- `docs/superpowers/specs/2026-10-08-web-dashboard-design.md` - per-mat web
  dashboard. Built 2026-10-08 from
  `docs/superpowers/plans/2026-10-08-web-dashboard.md`. Tests in `tests/test_web.py`.
  Planned follow-up (background listener per mat) is described in the spec.

## Current backlog

See `notes.md` for the live list (known bugs, known limitations of shipped
features, what's still to build, and what's already shipped). Don't copy
that list into this file - it drifts. As of 2026-10-08: multi-mat MQTT,
custom indices, patient-detected, the ROI rework, the web dashboard, and the
Tier 1/2 bounded-polish + calibration-rework batch are all built and tested
(147 tests passing). Open: the "Ignore signal" display bug, the
`user_guide.md` decision, the web dashboard's per-mat background listener,
area-per-cell/weight-estimate, and body-part recognition (deliberately not
started).

## Working conventions for this repo

- Ponytail (lazy/minimal) is the default stance: reuse what's there, don't
  add abstractions or dependencies the current ask doesn't need.
- No AI attribution in SmartMat commits/PRs (user's standing preference).
- Bounded changes get a short chat design + explicit go-ahead before editing
  code; bigger ones (new subsystems, protocol/interface changes) get a
  written spec, then a plan via the writing-plans skill (see
  `docs/superpowers/specs/` and `docs/superpowers/plans/` - each recent plan
  also documents where the spec didn't match the actual code, worth reading
  before touching that feature again).
- This is a healthcare-adjacent tool - be deliberate about wording and
  defaults anywhere risk/exposure/pressure-injury language shows up.

## Model guidance for this project

- Sonnet: mechanical/bounded UI edits (toggles, defaults, button renames,
  moving a config value between windows).
- Opus: anything with real design or correctness weight - new subsystems,
  protocol/data-format changes, or features that don't have a design yet
  (body-part recognition, the web dashboard's background-listener follow-up).
