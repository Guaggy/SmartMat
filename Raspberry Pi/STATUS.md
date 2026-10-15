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
ESP32 --MQTT/Serial--> sources/*Source (raw 0..value_max -> 0-1000, general.scale_to_app_range)
  --> processing/frames.process_frame()
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
- `export.py` - pure CSV export: one frame (long, one row per cell; Export snapshot button, which also saves the
  heatmap PNG) and a recordings/*.json to a wide CSV (Engineering > Session & export). No dependencies.
- `validation.py` - compares manual "Known reposition" annotations against
  auto-detected repositions/hotspots, for engineering validation.

`gui/` (Tkinter):
- `desktop.py` - main window, source/device selection, main plot, toggles. The Data dropdown is
  `DesktopApp.data_modes` (`DATA_MODES` plus the cell signals and each map index, rebuilt in `_set_indices`);
  signal/index maps are `_derived_grid(key)`, not frame keys. CoP/ROI/analysis use `_base_key()`, i.e. pressure.
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
expose the same `latest`/`quality`/`start`/`stop` shape plus the mat info
`shape` (rows, cols), `value_max` (raw full scale) and `mat_id`. Every source
range-checks raw units against its own `value_max` and scales to 0-1000 once,
right before `latest.set` (the app range stays 0-1000 everywhere after that).
`MqttSource(chip_id)` streams one mat (`smartmat/<chip_id>/frame`) and will not
start without that mat's retained meta message
(`<chip_id>,<rows>,<cols>[,<value_max>]`, 3 fields = 1000); `mats` stays
`{chip_id: (rows, cols)}`, value_max lives in `value_maxes`. `MqttSource()`
with no chip ID only listens on `smartmat/+/meta` to fill the device list.
`SerialSource(port, profile)` picks a `PROFILES` entry: "ESP32 text (115200)"
(config grid, value_max 1000, mat_id = port) or "Maxrays 20x20 (921600)"
(`sources/maxrays.py` decoder, 20x20, value_max 255, mat_id `maxrays-usb`). The
desktop shows a Protocol dropdown for Serial and applies the source's shape
before connecting; `list_ports()` returns `Port(device, label)`.

`SerialSource.start_raw_capture(path, seconds)` tees the exact port bytes to
`recordings/raw_<profile>_<time>.bin` (desktop "Capture raw (5 s)" button, shown for Serial, enabled while
connected; `tools/capture_raw.py` does the same without the GUI). `serial_stats()` (protocol, bytes/s,
frames/s, discarded bytes, invalid frames) feeds the Diagnostics window. Orientation (Rotate 0/90/180/270,
Mirror H/V; `frames.orient_grid`) is applied in `DesktopApp._poll` to live grids only (recordings are
already oriented), before `process_frame`; a change or a 90/270 turn of a non-square mat goes through
`_apply_grid_shape` (analysis state resets). So `config.TOTAL_*` is the *oriented* grid and sources must not
read it: MQTT/Serial pass the mat's own shape to `parse_frame_text_with_reason(..., shape)`.

Per-mat profiles: `<APP_DIR>/profiles/<mat_id>.json` (gitignored; `processing/calibration.py`
`save_profile/load_profile/apply_profile`) hold a real mat's tare baseline, both pressure calibrations (+ which is
active) and orientation, at its oriented grid shape. Only Serial/MQTT sources with a `mat_id` get one (not
`SimulatedSource`, i.e. synthetic data and recordings). `DesktopApp._save_profile` runs at the top of `_connect`,
in `_disconnect` and `_on_close`; `_load_profile` runs in `_connect` once the source shape is known: it restores
the orientation, applies the *oriented* shape (so the first frame through `_orient` does not reset again), then
always `_reset_calibration()` and, if the file's grid shape matches, puts its state back. So a real mat never
inherits another mat's tare; a mat without a (matching) profile starts clean and keeps the current orientation.
The profile also carries `size_mm` (the mat's physical sensing size, width x height as built; old profiles without it load
fine and fall back to `config.MAT_WIDTH_MM/MAT_HEIGHT_MM`, then to the per-cell `CELL_*_MM`). The calibration window shows which profile is active. Design: `docs/superpowers/specs/2026-10-15-per-mat-profiles-design.md`.

Mat size / load estimate: `DesktopApp.mat_size_mm` (About panel > "Mat size...", kept in the mat's profile) feeds ONE
`cell_size_mm` / `cell_area_m2` property (`processing/calibration.cell_size_mm`: width / cols, height / rows of the oriented
grid, axes swap on a 90/270 rotation). Area, force, hotspots, analysis, calibration-window newtons, the "Cell: W x H mm" line and
the readiness warning all read it - never `config.CELL_*` directly. "Estimated load: X kg (indicative)" = force_N / 9.81
(`statistics.load_estimate_text`); marked "default curve, not calibrated" while `PressureCalibration.is_default_curve`.
An engineering aid, not a weight measurement. Tests: `tests/test_mat_size.py`.

`general.py` - frame parsing (`parse_frame_text_with_reason(text, value_max)`),
`scale_to_app_range(grid, value_max)`, plus the mat nickname registry
(`mats.json`, gitignored, `{chip_id: nickname}`).

Recordings store frames after scaling; `metadata.value_max`/`mat_id` say where
they came from (missing value_max = 1000). `load_session` returns frames at the
recording's own `grid_shape`, and playback applies that size first.

`paths.py` - `APP_DIR`: the project folder, or the exe's folder when frozen (PyInstaller). `general.MATS_FILE`,
`processing.recording.RECORDINGS_DIR` and a relative `DEFAULT_PRESSURE_CALIBRATION_FILE` resolve against it;
`main.py` imports it first so a frozen build puts that folder on `sys.path` (config.py is excluded from the bundle
and copied from the bundled `config.example.py` on first run). Build: `build_exe.bat` -> `SmartMat.spec`
(onedir, windowed) -> `dist\SmartMat\SmartMat.exe` + `dist\SmartMat.zip`; `SmartMat.exe --selftest` is a headless
smoke test (writes `selftest.txt` next to the exe). Source-tree behaviour is unchanged.

`config.py` (gitignored, copy from `config.example.py`) holds every
threshold/constant used by the modules above, and the default grid size.
`config.TOTAL_ROWS`/`TOTAL_COLS` are overwritten at runtime when an MQTT mat of
another size connects or a recording of another size is played
(`DesktopApp._apply_grid_shape`, which also restarts everything sized to the
old grid) and set back for Serial/Simulated. Always
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
(147 tests passing at the time; 201 now). Open: the "Ignore signal" display bug, the
`user_guide.md` decision, the web dashboard's per-mat background listener,
body-part recognition (deliberately not
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
