# SmartMat: headless server, web dashboard, desktop theme (design + plan)

Approved by Even on 2026-10-16 (chat). Local doc (docs/ is gitignored). Engineering aid, not a medical device:
load/kg is a rough estimate, posture and risk are heuristics for testing the pipeline. Keep disclaimer wording.

## Architecture

```
ESP32 / Maxrays --MQTT--> broker (Pi) --> server (Pi or Windows, always on)  --REST + web UI--> browsers, phones
USB mat --serial--> server (owns the port) --bridged to MQTT--> broker
desktop app --MQTT raw frames (own processing, deep analysis)--> broker
desktop app --REST + PIN (profiles, labels, log)--> server
```
- Data plane = MQTT (`smartmat/<chip>/meta|frame|status`, unchanged contract). Control plane = REST on the server
  (same port as the web UI). Desktop's MQTT source keeps its name; Engineering > Connection gets a second group
  "SmartMat server" (URL).
- The server imports `processing/`, `sources/`, `general.py`, `paths.py`, `app_settings.py` and NEVER `gui/` or tkinter.
  Python only (Flask, paho, numpy, pyserial, sqlite3), runs on Windows and Raspberry Pi OS.
- Serial ports have one owner: the server owns USB mats and republishes their frames/meta to MQTT.
- Demo mats: chip ids starting with `demo-` (config `DEMO_PREFIX`), replayed from `samples/seat_take1.json`; shown
  with a visible DEMO label everywhere (web, desktop device list).

## Shared design tokens (single source: `branding.py`)

`PALETTE_LIGHT` / `PALETTE_DARK` dicts and `HEATMAP_STOPS` (list of (t, (r,g,b))). Brand: navy #10182B, sage #5E9C83.
Light: bg #E9EDF1, panel #FFFFFF, panel2 #F4F6F8, line #D3DAE2, ink #10182B, muted #586377, accent #2F7A62, accent_fill
#5E9C83, brandbar #FFFFFF, hm_bg #F1F4F7, ok #2E7D5B, warn #B7791F (text #8A5A00), bad #A8231B, idle #566074.
Dark: bg #0A101D, panel #111A2D, panel2 #0D1525, line #243049, ink #E6EBF2, muted #93A0B5, accent #74B89C,
accent_fill #5E9C83, brandbar #141824 (the navy behind logo_lockup_dark.png), hm_bg #0A101D, ok #6FC49C, warn #E6B45A, bad #F08A80, idle #9AA6BA.
Heatmap ramp stops: 0 (207,230,222), .25 (126,189,168), .5 (233,196,106), .75 (224,123,57), .9 (179,38,30),
1 (107,15,26); cells below ~2 % of full scale fade into hm_bg. The web UI reads these via `/api/theme`.
Style rules (desktop and web): flat, square, hairline rules, no shadows, no card-in-card, no dot-pills, state = text
with a small coloured square or a solid status cell, readouts as aligned label/value tables with tabular numerals,
accent only on primary button / active tab / links, system font (Segoe UI), light theme default.
Logos: `assets/logo_*.png|jpg` light and dark variants (lockup + mark); the dark brand bar uses the logo navy.

## Server design (`Raspberry Pi/server/`)

- Entry: `python -m server` (and `main.py --server`), options `--demo`, `--port`, `--data-dir`. Data dir = `paths.APP_DIR`.
- `engine.py` `MatEngine(chip_id, rows, cols, value_max, profile)`: `feed(grid_0_1000, t)` runs orient, tare, pressure
  calibration (profile from `profiles/<mat_id>.json`), occupancy, hotspots, temporal, motion, indices, posture, and
  exposes `snapshot()` (same JSON shape as `gui/web.build_snapshot` plus posture, time_in_position_s, risk,
  saturated_cells, online). No tkinter, no matplotlib.
- Posture (`processing/posture.py`, pure): centre of pressure vs mat centre in oriented cells. |dx| >
  `POSTURE_SIDE_CELLS` (default 2.0) -> "left"/"right"; else dy > `POSTURE_FORWARD_CELLS` (default 2.5) -> "forward";
  else "centred"; unoccupied -> "none". Debounced `POSTURE_HOLD_S` (default 3). time_in_position = seconds since the
  debounced class last changed, also reset by a detected reposition. Orientation respected.
- Risk (pure): worst state of the summary index (OVER -> "high", NEAR -> "medium", OK -> "low"), "none" when
  unoccupied, "offline" when no frame for `STALE_AFTER_S` or mat status offline. Sort order: offline, high, medium,
  low, none; ties by time_in_position desc.
- Store (`store.py`, sqlite3, `smartmat.db` in the data dir): tables `users(id,name,role,pin_hash,salt,active)`,
  `mats(chip_id,name,room,seat,unit)`, `events(id,t,chip_id,kind,user,detail)` append-only (alert raised/cleared/
  acknowledged/ignored, config changed, calibration pushed, user added), `timeline(chip_id,t_start,t_end,posture,risk)`.
  Retention `RETENTION_DAYS` (default 30). No patient names anywhere.
- Auth: viewing needs no login. Every write needs `pin` in the request body (JSON). PIN hash = hashlib.scrypt with
  per-user salt. Lockout: `PIN_LOCKOUT_ATTEMPTS` (default 0 = off) and `PIN_LOCKOUT_S` (default 60). First run: no
  users -> `POST /api/users` with a role admin is allowed once without a PIN to create the first admin; afterwards
  only admins add/disable users or reset PINs. Each action is written to `events` with the user name.
- Alerts (`alerts.py`): per mat, raise when risk is "high" for `ALERT_HIGH_HOLD_S` (default 30) or the mat goes
  offline for `ALERT_OFFLINE_S` (default 30); an alert is open until the condition clears; acknowledge/ignore needs a
  PIN and records who. Open alerts drive the bell. No push yet.
- REST (all JSON): `GET /api/overview` (small rows for the table: id, name, room, seat, unit, demo, online, risk,
  posture, time_in_position_s, saturated, open_alerts, since-relief), `GET /api/mats/<id>` (the row + snapshot, age_s,
  stale), `GET /api/mats/<id>/timeline?hours=`, `GET /api/mats/<id>/log`, `GET /api/alerts`,
  `POST /api/alerts/<id>/ack|ignore`, `PUT /api/mats/<id>/meta`, `PUT /api/mats/<id>/profile` + `GET` (profile JSON,
  version int), `GET|POST /api/users`, `PUT /api/users/<id>`, `GET /api/theme`, `GET /api/health`. Errors: JSON `{error}` with 4xx.
- Deployment: `deploy/smartmat-server.service` (systemd, Pi) and `deploy/install_windows_server.ps1` (startup task);
  windows exe `SmartMatServer.exe` via a second spec (console-less).
- Config (all in config.example.py): `SERVER_PORT` (default 8000, same as WEB_PORT today), `DEMO_PREFIX`,
  `POSTURE_*`, `ALERT_*`, `RETENTION_DAYS`, `PIN_LOCKOUT_*`, `SATURATION_WARN_CELLS`.

## Web dashboard v2 (`server/static/` index.html, app.js, style.css; plain JS, no build step)

Follows slide 3 of the product presentation: top bar (logo, unit filter, "Sort by" dropdown: risk, room, device,
time in position; search; bell with red dot and count; help), table (Device, Room, Seat, Data OK, Status pill
text "<posture> > <time>" on a solid status cell), a row expands to a posture/risk timeline with acknowledge
markers, right panel with the pressure map (shared ramp), peak, time since relief, saturation note. Norwegian
(bokmaal) first with an English toggle (`i18n` dict in app.js), light default, dark toggle, phone layout (cards,
installable: manifest.json + icons, no service worker push). Acknowledge/ignore/edit asks for the user's PIN in a small
dialog and shows who handled it. Help page: what the colours mean, what to do on an alert, disclaimer. Demo mats carry
a DEMO label. Poll /api/overview every 2 s and the selected mat every 1 s.

## Desktop

- Theme: `gui/theme.py` `apply_theme(root, mode)` builds a flat ttk theme (base "clam") from the branding palette,
  restyles plain tk widgets, matplotlib figures and open tool windows live; mode saved in settings.json
  (`theme`: "light" default). Header: theme toggle, logo variant by theme, brand bar navy in dark.
- Layout B: header brand bar; toolbar regrouped into labelled groups (Source / Calibrate / Record); tabs
  (Live, Analysis, Timeline, Hotspots, Movement, Indices, Diagnostics, Calibration, ROI, Engineering, Help) in a
  Notebook; the tool windows build into a page frame instead of a Toplevel (`gui/page.py` adapter exposing
  title/geometry/protocol/winfo_exists/lift/destroy so window classes stay as is) with a "Pop out" button that rebuilds
  the class in a Toplevel; non-visible tabs skip refresh. About, annotation note, mat size and plot options stay
  dialogs. Easy (Simple) mode hides the tab strip (Live only) and starts by default.
- Saturation: `processing/statistics.saturated_cells(raw_scaled, value_max)` counts cells >= value_max minus
  `HEALTH_SATURATION_MARGIN` (existing). When >= `SATURATION_WARN_CELLS` (default 1) the readout shows
  "N cells at sensor limit: load and peak read low", the load text becomes ">= X kg (rough)" else "~X kg (rough)".
  Also in Diagnostics and the server snapshot.
- Connection tab: "SmartMat server" group (URL) with Test, "Send calibration to server" (asks PIN), "Get from server",
  a read-only log view, and a "profile matches server" marker (version compare).
- Demo: "Load demo recording" menu entry plays `samples/seat_take1.json`; `tools/publish_demo_mat.py` replays it to the
  configured broker as retained meta + frames for chip id `demo-take1` (credentials from `app_settings.effective_mqtt`,
  never in the repo).

## Retune (assumption-based until more takes exist)

Capture facts: 8-bit counts (1 count = 3.9 app units), idle noise <= 1 count, seated: ~370/400 cells loaded, peak
median 234/255, saturation up to 19 cells, hotspots fired ~every 0.5 s with 20/15 kPa thresholds (default curve 255
counts = 50 kPa). Work: `tools/replay_tune.py` replays a recording through the pipeline (no GUI) and prints events per
minute and states per setting. Choose thresholds as fractions of full scale / relative to the loaded-area mean so they
stay valid under saturation; acceptance on seat_take1: idle 30 s no hotspot/contact, seated segment no hotspot flapping
(<= 3 new hotspot ids per minute after settling), one major movement at sit-down. Document that this is one 40 s take
and must be re-checked with more takes. Also find why the stream arrives at ~7.7 fps against `SERIAL_TARGET_FPS` 10.

## Conventions

Branch per package, tests in `Raspberry Pi/tests` (`python -m pytest -q` from `Raspberry Pi`), keep all 230 passing.
Commit by explicit path, one commit per package, NO AI attribution lines, never `git add -A`, never push, never flash.
Healthcare wording as in README. Reuse existing code; no new dependencies without need.
