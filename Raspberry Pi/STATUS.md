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
  tracking with frame-to-frame ID matching (merge/split/relief/resume). Thresholds are the kPa values,
  raised to `HOTSPOT_*_FRACTION` x the loaded-area mean when set (`thresholds()`; 0 = kPa only);
  `HOTSPOT_RELIEF_GRACE_S` ignores short dropouts. Presets/recordings without these keys load them as 0.
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
- `export.py` - pure CSV export: one frame (long, one row per cell, `raw_scaled_0_1000` = received value scaled to the app range; Export snapshot button, which also saves the
  heatmap PNG) and a recordings/*.json to a wide CSV (Engineering > Session & export). No dependencies.
- `validation.py` - compares manual "Known reposition" annotations against
  auto-detected repositions/hotspots, for engineering validation.

`gui/` (Tkinter):
- `desktop.py` - main window, source/device selection, main plot, toggles. The Data dropdown is
  `DesktopApp.data_modes` (`DATA_MODES` plus the cell signals and each map index, rebuilt in `_set_indices`);
  signal/index maps are `_derived_grid(key)`, not frame keys. CoP/ROI/analysis use `_base_key()`, i.e. pressure.
  Simple / Advanced view (top-right "View:" switch, `config.START_IN_SIMPLE_MODE`): widgets registered with `_adv()` /
  `_checkbox(advanced=True)` are `pack_forget`-ed in Simple and put back in their original place by `_apply_view` (rows are
  recorded by `_remember_rows`; Serial's capture button goes through `_place_capture_button`). Geometry only - no state is
  touched. Simple keeps source/device/protocol, Connect/Disconnect, Tare, Record, Export snapshot, 2D/3D, Data, the heatmap and
  the Peak / Estimated load / Hotspots lines + patient chip. Tests: `tests/test_view_mode.py`. A new main-window widget that
  is not part of that set must be registered with `_adv()`.
- `theme.py` - flat light/dark ttk theme ("smartmat", on clam) from `branding.PALETTE_*`: `apply_theme(root, mode)`
  restyles ttk styles, plain tk widgets (walks every open window) and every figure made with `theme.figure()` live;
  `heatmap_cmap()` is the shared ramp fading into `hm_bg`; `contrast`/`text_on` are pure. Mode saved as `theme` in
  settings.json (`app_settings.theme()/save_theme`, light default); Light/Dark switch in the brand bar
  (`DesktopApp._set_theme`). Layout B: brand bar (lockup per theme, selected mat, View, Light/Dark, About), toolbar
  rows of labelled groups (Source, Playback while a recording plays, Calibrate + Record, Display, Tools, Options),
  readouts column of label/value rows (`_readout` splits a "Name: value" StringVar), status bar (patient cell, index
  cells, source health, status text, disclaimer). Tests: `tests/test_theme.py`.
- One file per tool window: `calibration_window.py`, `analysis_window.py`,
  `diagnostics_window.py`, `temporal_window.py`, `hotspot_window.py`,
  `motion_window.py`, `engineering_window.py`, `annotation_window.py`,
  `roi_window.py` (ROI selection on a frozen snapshot + all ROI output),
  `indices_window.py` (live index values), `index_editor.py` (the Indices tab
  inside the Engineering window),
  `help_window.py`.
- `web.py` - local read-only Flask dashboard toggled from the desktop app
  ("Web UI"). The desktop is the only producer: `_publish_web()` calls
  `web.update(mats, live_id, snapshot)` about once a second. The About panel shows the two addresses as clickable links
  (`DesktopApp._link`, webbrowser.open). Addresses: `/`
  (static page that polls), `/api/mats`, `/api/mats/<id>`. Only the mat the
  desktop is connected to has data; non-MQTT sources appear as id `local`.

`sources/` - `mqtt_source.py`, `serial_source.py`, `simulated_source.py`, all
expose the same `latest`/`quality`/`start`/`stop` shape plus the mat info
`shape` (rows, cols), `value_max` (raw full scale) and `mat_id`. Every source
range-checks raw units against its own `value_max` and scales to 0-1000 once,
right before `latest.set` (the app range stays 0-1000 everywhere after that).
`MqttSource(chip_id)` streams one mat (`smartmat/<chip_id>/frame`) and will not
start without that mat's retained meta message
(`parse_meta` accepts exactly three forms: `<chip_id>,<rows>,<cols>` (value_max 1000, resistive firmware),
`...,<value_max>` and `<chip_id>,<rows>,<cols>,<value_max>,<model>,<width_mm>,<height_mm>`, e.g.
`a1b2c3d4e5f6,20,20,255,MC266,343,358`; 5, 6 or 8+ fields, bad numbers, a model with anything but
letters/digits/`_`/`-`, or non-positive sizes are invalid); `mats` stays `{chip_id: (rows, cols)}`, value_max lives in
`value_maxes`, the announced preset in `presets` (`model` / `default_size_mm` properties, same names as SerialSource). `MqttSource()`
with no chip ID only listens on `smartmat/+/meta` to fill the device list. Both also subscribe
`smartmat/+/status` (retained `online`/`offline`, ESP32_China only) into `status` {chip_id: state}; other payloads are
ignored and the device dropdown appends " (offline)" for offline mats (unknown/online unchanged, still selectable).
`SerialSource(port, profile)` picks a `PROFILES` entry: "ESP32 text (115200)"
(config grid, value_max 1000, mat_id = port) or "Maxrays 20x20 (921600)"
(`sources/maxrays.py` decoder, 20x20, value_max 255, mat_id `maxrays-usb`, preset model "MC266" + default sensing
size 343 x 358 mm; datasheet facts in `notes.md`). The Maxrays stream (~60 fps) is averaged (float) over
1/`config.SERIAL_TARGET_FPS` s (default 10; 0 or negative = off; None/non-numeric = 10) into ONE scaled grid per window (windows on a fixed schedule, so slow polls do not stretch the rate); merged frames are not drops,
`serial_stats` has `frames_per_s` (decoded) and `output_per_s`. `MqttSource` ignores frame messages with the retain
flag (stale after a reconnect); retained meta is still used. The
desktop shows a Protocol dropdown for Serial and applies the source's shape
before connecting; `list_ports()` returns `Port(device, label)`.

`tools/replay_tune.py` replays a recording through the analysis classes without the GUI and prints event counts per
minute (`--set NAME=value`, `--sweep NAME=a,b,c`, `--file`); `tests/test_retune.py` asserts the tuned defaults on
`samples/seat_take1.json`.

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
active), orientation, the mat size the user typed and its ROI (`roi` {shape, cells}, restored only when the shape
equals the oriented grid; `processing.calibration.profile_roi`; a connecting real mat never inherits another mat's
ROI), at its oriented grid shape. Only Serial/MQTT sources with a `mat_id` get one (not
`SimulatedSource`, i.e. synthetic data and recordings). `DesktopApp._save_profile` runs at the top of `_connect`,
in `_disconnect` and `_on_close`; `_load_profile` runs in `_connect` once the source shape is known: it restores
the orientation, applies the *oriented* shape (so the first frame through `_orient` does not reset again), then
always `_reset_calibration()` and, if the file's grid shape matches, puts its state back. So a real mat never
inherits another mat's tare; a mat without a (matching) profile starts clean and keeps the current orientation.
The profile also carries `size_mm` (the mat's physical sensing size, width x height as built; old profiles without it load
fine and fall back to the source's preset `default_size_mm` (Maxrays MC266, or the MQTT meta's size), then `config.MAT_WIDTH_MM/MAT_HEIGHT_MM`, then
the per-cell `CELL_*_MM`). Only a size the user typed ("Mat size...") or that is already in the profile is saved
(`DesktopApp._user_size_mm`); a preset size is never written, so a later firmware/Python preset change takes effect.
The About panel shows "Mat: <vendor> <model>" (MQTT: just the model). The calibration window shows which profile is active. Design: `docs/superpowers/specs/2026-10-15-per-mat-profiles-design.md`.

Mat size / load estimate: `DesktopApp.mat_size_mm` ("Mat size..." button in the toolbar's Calibrate group, kept in the mat's profile) feeds ONE
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

`paths.py` - `APP_DIR` / `DATA_MODE` (`choose_data_dir`, pure and tested): source tree = the project folder; frozen =
the exe's folder if `portable.txt` sits next to the exe (portable) or config.py/mats.json/recordings/profiles already
do (legacy), else `%LOCALAPPDATA%\SmartMat` (user; falls back to the exe's folder if unavailable). `general.MATS_FILE`,
`processing.recording.RECORDINGS_DIR`, the profiles folder and a relative `DEFAULT_PRESSURE_CALIBRATION_FILE` resolve
against it; `main.py` imports it first so a frozen build puts that folder on `sys.path` (config.py is excluded from the
bundle and copied from the bundled `config.example.py` on first run). Bundled read-only files go through
`resource_path()` (`sys._MEIPASS`, which is also the temp extraction folder of the one-file build). Builds:
`build_exe.bat` -> `SmartMat.spec` (onedir, windowed) -> `dist\SmartMat\SmartMat.exe` + `dist\SmartMat.zip`
(about 2 s start), and `build_exe_onefile.bat` -> `SmartMat-onefile.spec` (same Analysis, keep in sync) ->
`dist\onefile\SmartMat.exe` (one 41 MB file, about 6-8 s start, extracts to `%TEMP%` each launch).
`SmartMat.exe --selftest` is a headless smoke test (writes `selftest.txt` with app_dir and mode to APP_DIR).
Source-tree behaviour is unchanged.

`app_settings.py` - `settings.json` in `paths.APP_DIR` (gitignored, plaintext) holds the MQTT broker;
`effective_mqtt()` = settings.json > config.py (only the example credential placeholders count as unset; the host never does) > `localhost:1883`, no
credentials. `MqttSource` reads it at construction and only calls `username_pw_set` for a non-empty user;
Engineering > Connection edits it (Test = `check_broker`, Save restarts discovery via
`DesktopApp.restart_discovery`). An open MQTT connection keeps its old broker until it reconnects.

`branding.py` - product/company names, website, contact address (contact@verdianmedical.com, confirmed), `VERSION` (About, window title "SmartMat 0.1.0", first line
of `selftest.txt`), disclaimer text and the accent
palette. `PALETTE_LIGHT` / `PALETTE_DARK` / `HEATMAP_STOPS` are the shared design tokens (ACCENT/DARK/MUTED/HEADER_BG
are aliases of the light palette). Logos come from `branding_source/Logo.jpg` via `tools/make_branding.py` into
`assets/logo_{mark,lockup}_{light,dark}.png`, `icon_256.png` (window icon) and `icon.ico` (exe icon in both PyInstaller
specs). The brand bar (lockup by theme, View switch, Light/Dark, About) is `DesktopApp._build_header`; the app starts in Easy
(Simple) mode (`START_IN_SIMPLE_MODE`, default True). Bundled read-only files go through
`resource_path()` (`sys._MEIPASS`, which is also the temp extraction folder of the one-file build). Builds:
`build_exe.bat` -> `SmartMat.spec` (onedir, windowed) -> `dist\SmartMat\SmartMat.exe` + `dist\SmartMat.zip`
(about 2 s start), and `build_exe_onefile.bat` -> `SmartMat-onefile.spec` (same Analysis, keep in sync) ->
`dist\onefile\SmartMat.exe` (one 41 MB file, about 6-8 s start, extracts to `%TEMP%` each launch).
`SmartMat.exe --selftest` is a headless smoke test (writes `selftest.txt` with app_dir and mode to APP_DIR).
Source-tree behaviour is unchanged.

`app_settings.py` - `settings.json` in `paths.APP_DIR` (gitignored, plaintext) holds the MQTT broker;
`effective_mqtt()` = settings.json > config.py (only the example credential placeholders count as unset; the host never does) > `localhost:1883`, no
credentials. `MqttSource` reads it at construction and only calls `username_pw_set` for a non-empty user;
Engineering > Connection edits it (Test = `check_broker`, Save restarts discovery via
`DesktopApp.restart_discovery`). An open MQTT connection keeps its old broker until it reconnects.

`branding.py` - product/company names, website, contact address (contact@verdianmedical.com, confirmed), `VERSION` (About, window title "SmartMat 0.1.0", first line
of `selftest.txt`), disclaimer text and the accent
colours taken from verdianmedical.com; `assets/logo.png` is the site's header icon. The brand bar is `DesktopApp._build_header`; the accent colour only touches the
Connect/Record buttons (`Accent.TButton`), the selected switch/tab and links; state cells use ok/warn/bad/idle. Bundled read-only
files (`assets/`) are found with `paths.resource_path()` (frozen: inside the PyInstaller bundle; `SmartMat.spec` datas), user
data still goes through `APP_DIR`. Missing logo = text-only header.

`config.py` (gitignored, copy from `config.example.py`) holds every
threshold/constant used by the modules above, and the default grid size.
`config.TOTAL_ROWS`/`TOTAL_COLS` are overwritten at runtime when an MQTT mat of
another size connects or a recording of another size is played
(`DesktopApp._apply_grid_shape`, which also restarts everything sized to the
old grid) and set back for Serial/Simulated. Always
read them as `config.TOTAL_ROWS` - a `from config import TOTAL_ROWS` copy goes
stale. `sources/simulated_source.py` is the one deliberate exception.

`server/` - headless server (`python -m server [--demo [N]]`, `main.py --server`; never imports gui/ or tkinter).
`engine.py` `MatEngine` = the desktop's per-frame pipeline per mat (orient, tare, pressure calibration from the mat's
profile, temporal, hotspots, motion, occupancy, indices, `processing/posture.py`), `snapshot()` = gui/web's snapshot
plus posture, time_in_position_s, risk, saturated_cells, since_relief_s, online. processing/* reads the grid size from
`config.TOTAL_*`, so `engine.grid_shape()` sets it per mat under one global lock. `alerts.py` = alert state machine,
`store.py` = sqlite (users with scrypt PINs, mats, events, timeline), `app.py` = Flask `create_app` (REST, PIN in the
JSON body of every write), `__main__.py` = MQTT discovery (one `MqttSource(chip, client_id=...)` per mat), serial
bridge (`SERVER_SERIAL_PORTS`, republished as `usb<port>`), demo mats (`DemoMat`, faster clocks), pump (4 frames/s per
mat) and 1 s tick. Design: `docs/superpowers/specs/2026-10-16-server-and-ui-design.md`. Tests: `tests/test_server_*.py`.

Desktop server connection (control plane): `server_client.py` (`ServerClient` over urllib, `(ok, data_or_text)` and never raises;
`profile_fingerprint`/`compare_profiles` ignore `version`, `mat_id` and every `*_at` timestamp) and `gui/server_panel.py` (plain ttk
group "SmartMat server" at the bottom of Engineering > Connection: URL, Test, Send calibration (PIN dialog), Get from server
(through `DesktopApp._load_profile`, restores the old state if the profile does not fit), Server log, matches/differs marker). The URL is
`server_url` in settings.json (`app_settings.effective_server_url`). The mat id is `DesktopApp._profile_mat_id()`. The server's
profile PUT now also returns `ok` and `user`. Tests: `tests/test_server_client.py`. Not verified against real hardware or a real Pi server.

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
(147 tests passing at the time; 230 now). Open: the web dashboard's per-mat background listener,
the expression builder, known-weight load calibration, body-part recognition (deliberately not
started); hardware validation is tracked in `../SETUP_AND_TEST.md`.

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
