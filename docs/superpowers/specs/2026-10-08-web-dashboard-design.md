# Web dashboard: per-mat quick glance

## Goal

`gui/web.py` serves one global grid on a temporary test page and has no idea
which mat it is showing. This change turns it into a small read-only local
dashboard: pick a known mat, and for the mat that is live see its heatmap,
active hotspots, patient state and custom-index values.

It is the "quick remote glance", not the desktop toolset. Nothing on the page
configures anything.

Out of scope: background listeners for mats the desktop does not have open
(planned next, see "Planned follow-up"), any controls or settings, history or
trend charts, map-index heatmaps, login, and the public website.

## How several mats get onto the dashboard

The desktop app processes one mat at a time; its tare, calibration, hotspot
tracking, patient indicator and indices all belong to the connected mat. It
also holds one grid size at a time (`config.TOTAL_ROWS`/`TOTAL_COLS`).

So in this build:

- Every known mat is listed, with the same chip-ID / nickname identity as the
  desktop's MQTT device list (`MqttSource.mats` + `mats.json`).
- The mat the desktop is connected to is **live** and shows the full glance,
  using the desktop's own pipeline (so its tare and calibration apply).
- Every other mat shows name, chip ID and grid size, and "not open in the
  desktop app".
- A non-MQTT source (Simulated, Serial, recording playback) appears as one
  extra entry with the fixed ID `local`, named after the source and device,
  so the dashboard works without hardware.

The web side is keyed by mat ID from the start, so the follow-up only has to
add more publishers.

## `gui/web.py`

### Store

Module-level, guarded by one lock:

- `update(mats, live_id=None, snapshot=None)` replaces the known-mat list
  (`[{"id", "name", "rows", "cols"}]`), records which one is live, and, when a
  snapshot is given, stores it for `live_id` with the time it arrived.
  `live_id=None` means nothing is live; snapshots of mats that are no longer
  live are dropped.
- `build_snapshot(frame, hotspot_tracks, occupied, monitor)` is a pure function
  that turns the desktop's state into the JSON-ready snapshot (below).

### Addresses (all GET, read-only)

| Address | Returns |
|---|---|
| `/` | the dashboard page |
| `/api/mats` | `{"mats": [{"id", "name", "rows", "cols", "live"}]}` |
| `/api/mats/<mat_id>` | that entry plus `"snapshot"` (or `null`), `"age_s"`, `"stale"`; 404 `{"error": "unknown mat"}` for an ID that is not known |

`stale` is true when the live mat's snapshot is older than `STALE_AFTER_S`
(the existing desktop constant), so a frozen picture is never shown as live.

The old `/data` address and `update_grid()` are removed. The only other user
of `/data` was the public website widget, which cannot read it since the CORS
header was removed.

### Snapshot

```json
{
  "unit": "kPa",
  "scale_max": 50.0,
  "grid": [[0.0, 1.2, null, ...], ...],
  "occupied": true,
  "hotspots": [{"id": 3, "peak_kpa": 31.2, "cells": [[2, 4], [2, 5]], "active_s": 42.0, "persistent": true}],
  "indices": [{"name": "Mat overview", "layer": "summary", "value": 0.42, "threshold": 1.0, "near": 0.8, "state": "ok"}]
}
```

- `grid` is calibrated pressure in kPa when the frame has it (`scale_max` =
  `PRESSURE_DISPLAY_MAX_KPA`); otherwise the baseline-subtracted signal with
  `"unit": "relative"` (`scale_max` = `VALUE_MAX_DEFAULT`). It does not follow
  the desktop's Data dropdown. Non-finite cells are `null`.
- `occupied` is `true`, `false` or `null` (unknown).
- `hotspots` are `HotspotTracker.active`.
- `indices` lists every defined index. `value` is `IndexMonitor.compared(name)`
  (a map index's peak cell), `null` when unknown; `near` is
  `near_fraction * threshold`; `state` is the monitor's state.

### Page

One HTML page with inline CSS and plain JavaScript, no libraries:

- A dropdown of mats (live ones marked), filled from `/api/mats`.
- For a live mat: the heatmap on a canvas sized from `rows`/`cols`, hotspot
  cells outlined (red when persistent, orange otherwise), the patient state,
  a hotspot list (peak kPa, active time), an index list (value / threshold,
  coloured by state), the unit, and "updated N s ago" or a stale notice.
- For any other mat: name, chip ID, grid size, "not open in the desktop app".
- Polls once a second. All text from the server is written with
  `textContent`, never as HTML, since nicknames are user-entered.
- Wording: "index" and "threshold", never "risk"; one line stating this is an
  engineering aid and not a medical device.

## `gui/desktop.py`

- `_publish_web(force=False)` builds the known-mat list and, when a frame
  exists, the snapshot, and calls `web.update(...)`. Called from
  `_handle_new_frame` (throttled to once a second, replacing
  `web.update_grid`), and forced on connect, disconnect, a change in the
  discovered mats, a rename, and a grid-size change.
- The live ID is the connected `MqttSource`'s chip ID, or `local` for any
  other source.
- The About panel and the "Web UI running at ..." status show
  `http://<hostname>.local:<port>` (`socket.gethostname()`), with the LAN IP
  kept beside it as a fallback. Raspberry Pi OS ships Avahi enabled, so no new
  dependency; this has not been confirmed on the deployed Pi.

"Share live data" needs no code change: the checkbox, `set_sharing()`, the
gate on `/data` and the CORS header are already gone. Only the `notes.md`
line asking for it is removed.

## Planned follow-up (not built now)

A light background listener per known mat, so mats the desktop does not have
open show a live raw heatmap. It needs a frame-reading path that does not
depend on the app's current grid size, and one extra MQTT connection per mat.
Analysis (hotspots, patient state, indices) stays limited to the connected
mat until per-mat tare/calibration exists.

## Testing

`tests/test_web.py`, `unittest`, using Flask's test client:

- Store and addresses: mat list with the live flag; unknown mat is a 404;
  a non-live mat has no snapshot; a stale snapshot is flagged; switching the
  live mat drops the old snapshot.
- `build_snapshot`: kPa and relative units, NaN cells become `null`, hotspots,
  the three patient states, index values (summary, map peak, unknown).
- The page is served and contains no server-rendered mat names.
- Desktop (skipped without a display): connecting publishes a live `local`
  mat with a snapshot; known MQTT mats are listed by nickname; disconnecting
  leaves nothing live; the shown address uses `<hostname>.local`.
