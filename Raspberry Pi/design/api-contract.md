# SmartMat web dashboard: API contract

What `server/static/app.js` consumes. `tools/mock_api.py` implements exactly this, so run it next to the real
server to compare shapes (`python tools/mock_api.py`, PIN 1234). Times are unix seconds (float or int), durations
are seconds. All bodies are JSON. Errors are `{"error": "<text>"}` with a 4xx status; the dashboard shows the text
as is, so write it for a nurse.

Static files are served from `/` (`index.html`, `app.js`, `style.css`, `manifest.json`, `img/`); the page uses
relative URLs and polls: `/api/overview` every 2 s, `/api/mats/<id>` (selected mat) every 1 s,
`/api/mats/<id>/timeline` every 5 s while a row is expanded, `/api/alerts` while the bell list is open. Polling
pauses while the browser tab is hidden. Send `Cache-Control: no-store` on `/api/*`.

## Reads

### GET /api/overview

```json
{"mats": [{
   "id": "sm-101", "name": "SmartMat 1", "room": "101", "seat": "A", "unit": "Avd. A",
   "demo": false, "online": true,
   "risk": "high|medium|low|none|offline",
   "posture": "left|right|forward|centred|none",
   "time_in_position_s": 718, "since_relief_s": 5400,
   "saturated_cells": 12, "open_alerts": 1}],
 "open_alerts": 2, "server_time": 1792141655.2}
```

- `risk`: `offline` means no frames for `STALE_AFTER_S` or status offline. The dashboard never shows an offline mat
  as healthy, and also treats `online: false` as offline whatever `risk` says. An unknown `risk` string is drawn as
  "none" (grey), never green.
- `posture` `none` means unoccupied. Then `time_in_position_s` is how long it has been unoccupied ("No user for 2:53").
  `left`/`right` are the sitter's own left and right (clinical convention). With the front at the bottom of the map,
  column 0 is the sitter's right; the mat's Mirror H setting swaps them.
  For an offline mat `posture` and `time_in_position_s` are ignored by the UI.
- `since_relief_s` is `null` when unknown (shown as a dash).
- `saturated_cells >= 1` shows "N cells at sensor limit: load and peak read low".
- `open_alerts` on a row counts that mat's alerts in state `open`; the top-level `open_alerts` drives the bell.
- `server_time` lets the browser correct for a wrong clock (alert ages, timeline axis).
- `room`, `seat` and `unit` are always strings (`""` when not set); the unit filter is built from the distinct non-empty values.
- Demo mats are marked with `demo: true` (chip id starts with `demo-`); the UI adds a DEMO label.

### GET /api/mats/<id>

The overview row, plus:

```json
{"snapshot": {
   "unit": "kPa|relative", "scale_max": 50.0,
   "grid": [[0.0, 3.1, null]], "occupied": true,
   "hotspots": [{"id": 1, "peak_kpa": 46.0, "cells": [[9, 4], [9, 5]], "active_s": 12.5, "persistent": false}],
   "indices": [{"name": "Peak pressure (kPa)", "layer": "pressure", "value": 46.0, "threshold": 45.0, "state": "ok|near|over"}],
   "peak_kpa": 46.0},
 "age_s": 0.4, "stale": false}
```

- `grid`: rows x cols, values in `unit`, `null` for a dead/unknown cell (drawn as 0). Orientation is the oriented
  grid: **row 0 is the back of the seat, the last row the front** (the panel labels the bottom edge "Front").
  Colour is `value / scale_max` through the ramp from `/api/theme`; the browser upsamples bilinearly (8x), so any
  rectangular size works.
- `unit: "relative"` (not calibrated): the UI says "relative signal, not pressure" and hides the kPa readout; send
  `peak_kpa: null`.
- `hotspots[].cells` are `[row, col]`; the browser draws a dashed outline round each area (thicker if `persistent`).
- `indices[].state` is `ok`, `near` or `over`.
- `occupied`: `true`, `false` (the UI says "Nobody is on the mat" and shows no peak) or `null` (unknown).
- `age_s`: seconds since the last frame; `stale: true` (age > `STALE_AFTER_S`) dims the map and shows "no new data".
  For an offline mat keep returning the last snapshot with a growing `age_s` and `stale: true`; if there is none,
  send `snapshot: null` (the map stays empty, the note and readouts still show).
- A mat that has not sent a frame yet has `snapshot: null`, `age_s: null`, `stale: true`.
- 404 `{"error"}` for an unknown mat; the dashboard drops its selection.

### GET /api/mats/<id>/timeline?hours=5

```json
{"segments": [{"t_start": 1792123655, "t_end": 1792129171, "posture": "right", "risk": "high|medium|low|none"}],
 "markers": [{"t": 1792130000, "kind": "handled", "user": "Test Nurse"}]}
```

- Segments are in time order and may have gaps (drawn empty = "no data"). The current segment ends at "now" (or at the
  moment the mat went offline). Anything older than `hours` may be omitted or is clipped by the browser.
- Segment colour comes from `risk`; the label inside from `posture`.
- `markers` are acknowledge/ignore events (red markers, tooltip "Handled by <user>").

### GET /api/alerts

```json
{"alerts": [{"id": "a1", "chip_id": "sm-101", "name": "SmartMat 1", "room": "101",
             "kind": "high_risk|offline", "t_raised": 1792141100,
             "state": "open|acknowledged|ignored", "by": null}]}
```

`by` is the user name once handled. The list is newest first or in any order (the UI sorts open first, then newest,
and shows at most 30). The real server sends the alerts whose condition is still present (state `open` or
`acknowledged`/`ignored`) plus the last 30 handled ones that have cleared since; an unhandled alert that clears
disappears. Only `open` alerts count in the bell (`open_alerts`).

### GET /api/theme

```json
{"light": {"bg": "#E9EDF1", "...": "..."}, "dark": {"...": "..."}, "heatmap_stops": [[0.0, [207, 230, 222]], [1.0, [107, 15, 26]]]}
```

From `branding.py` (`PALETTE_LIGHT`, `PALETTE_DARK`, `HEATMAP_STOPS`). The dashboard only reads `heatmap_stops`
(stops sorted by t, 0..1) and keeps a built-in copy as fallback. The palette tokens live in `style.css` as CSS
variables; keep both in step with `branding.py` when a colour changes.

### GET /api/health

`{"ok": true, "version": "0.1.0", "needs_admin": false}`

`needs_admin: true` means the server has no users yet: the dashboard opens "Create first user (admin)". The real
server adds `time` and `mats` (count).

### GET /api/users

```json
{"users": [{"id": 1, "name": "Test Nurse", "role": "admin|user", "active": true}], "needs_admin": false}
```

Viewing needs no login; never any PIN hash. Role `user` is shown as "Nurse" in the dashboard.

### GET /api/settings

```json
{"settings": [{"key": "alert_high_hold_s", "group": "alerts", "type": "int|float|bool", "value": 30, "default": 30,
               "min": 5, "max": 3600, "unit": "s", "advanced": false, "changed": false}]}
```

Everyone can read. `value` is what is in force, `default` what `config.py` says, `changed` is true while an override
is saved. `min`/`max` are null for a bool. Groups: `alerts`, `risk`, `mats`, `data`, `posture`; `advanced` ones are
shown under "Advanced". The labels and explanations are in the page (`s_<key>`, `s_<key>_h`), not in the API.
Keys: `alert_high_hold_s`, `alert_offline_s`, `push_enabled`, `relief_minutes`, `near_percent`, `stale_after_s`,
`saturation_warn_cells`, `posture_hold_s`, `posture_side_cells`, `posture_forward_cells`, `retention_days`.

### GET /api/hidden-mats

`{"mats": [{"id", "name", "room", "seat", "unit", "demo"}]}`: mats an admin removed (kept for a restore).

## Writes (all need `pin` in the JSON body)

Wrong PIN: 403 with `{"error": "Wrong PIN"}`. Success returns the handling user's name in `user`; the
dashboard shows "Acknowledged by <user>". Error texts start with a capital and are shown as they are.

| Call | Body | Success |
|---|---|---|
| `POST /api/alerts/<id>/ack` | `{"pin"}` | `{"ok": true, "user": "name"}` |
| `POST /api/alerts/<id>/ignore` | `{"pin"}` | `{"ok": true, "user": "name"}` |
| `PUT /api/mats/<id>/meta` | `{"pin", "name", "room", "seat", "unit"}` (admin only) | `{"ok": true, "user": "name"}` (the real server adds the mat's id/name/room/seat/unit/demo) |
| `PUT /api/settings` | `{"pin", "values": {"<key>": value, "<key>": null}}` (admin only; `null` = back to the default) | `{"ok": true, "user": "name", "settings": [...]}` |
| `POST /api/mats/<id>/hide` | `{"pin"}` (admin only) | `{"ok": true, "user": "name"}`; 409 "Only a mat that is offline can be removed" |
| `POST /api/mats/<id>/show` | `{"pin"}` (admin only) | `{"ok": true, "user": "name"}`; 404 if the mat is not removed |
| `POST /api/users` | `{"pin", "name", "role": "admin\|user", "new_pin"}` | 201 `{"ok": true, "user": "acting admin", "created": {id, name, role, active}}` |
| `PUT /api/users/<id>` | `{"pin", "active"?, "new_pin"?}` | `{"ok": true, "user": "acting admin", "updated": {id, name, role, active}}` |

- Acknowledging or ignoring an alert that is no longer `open` (handled, cleared or unknown id): 409 with an `{"error"}` text.
- Users: PINs are per person, 4-8 digits, and unique (a taken PIN is a 400 "That PIN is already in use, choose another").
  `POST /api/users` needs no `pin` while there are no users, and then only with `role: "admin"` (the first admin);
  afterwards both user calls need an admin's PIN (403 "Only an admin can do this"). The last active admin cannot be
  disabled (400). The settings page's "Open users" button lists users and offers add, disable/enable and reset PIN.
- `meta`: all four fields are sent every time (the edit dialog sends the full set). Reject an empty name with 400.
  Only admins change mat details (a nurse gets 403 "Only an admin can do this").
- `settings`: all or nothing. An unknown key, a wrong type, a non-whole number for an `int` or a value outside
  `min`/`max` is a 400 and nothing changes. Changes apply at once (no restart) and are logged as `settings changed`
  with the old and new value and the admin's name. The dashboard's settings page (gear button, "Innstillinger") sends
  only what differs from the server, validates in the browser first and lists the changes in the PIN dialog.
- `hide`: stops reading the mat, closes its open alerts and drops it from the overview, alerts and mat calls; it stays
  removed after a restart. `show` lets discovery open it again (it reappears when it next sends data).
- After a write the dashboard re-reads overview, alerts, the mat and the timeline at once.

## What the dashboard stores in the browser

`localStorage` keys (all optional, every access in try/catch): `sm.lang` (`nb`|`en`), `sm.theme` (`light`|`dark`),
`sm.sort`, `sm.unit`. Nothing about patients; no PIN is ever stored.

## Phone app (push devices)

Used by `Phone App/`, not by the dashboard. `POST /api/devices` body `{expo_push_token, platform, name, pin, lang,
tz, quiet_from, quiet_to}` registers a phone (needs a valid staff PIN, wrong PINs count towards the lock-out);
`PUT /api/devices/<token>` updates language and quiet hours and `DELETE /api/devices/<token>` removes it (no PIN: the push
token is the secret of the phone). One push is sent per raised alert (`server/push.py`, Expo push service, mat name and room
only), none when it clears. Settings: `PUSH_ENABLED`, `PUSH_ACCESS_TOKEN` in `config.py`. See `Phone App/README.md`.
