# Multi-mat MQTT support: chip-ID topics, grid-shape handshake, UI nicknames

## Goal

Today exactly one ESP32 can talk to the Pi over MQTT: both sides hardcode the
topic (`smartmat/frame`) and the grid shape (`TOTAL_ROWS`/`TOTAL_COLS` in
`config.py`, `grid_rows`/`grid_cols` in `main.cpp`). Two physical mats would
collide on the same topic and MQTT client ID, and swapping in a
different-sized mat means manually editing `config.py` to match.

This change lets:
- Any number of ESP32 mats connect to the same broker without colliding.
- The Pi discover which mats exist and list them in the UI.
- The user give each mat a nickname that's remembered across restarts.
- The Pi pick up a mat's grid size automatically instead of it being a
  hardcoded constant.

Out of scope: the Serial (USB) source. It stays on the current
config-driven fixed shape — multi-mat switching and topic collisions don't
apply to a single wired connection, and Serial is already being phased out
for the home deployment per `Raspberry Pi/notes.md`. Also out of scope: the
GUI-declutter work and anything related to the public website — separate,
unrelated changes.

## ESP32 side (`ESP32/src/main.cpp`)

- At boot, read the chip ID via `ESP.getEfuseMac()` and format it as a
  lowercase hex string (e.g. `a1b2c3d4e5f6`). No manual per-board config
  needed.
- Use that string as both:
  - The MQTT client ID (replaces the hardcoded `mqtt_client_name`). Required
    even for a single extra mat — two boards sharing one client ID make the
    broker kick whichever connected first.
  - The topic prefix: `smartmat/<chip_id>/frame` and `smartmat/<chip_id>/meta`.
- Publish the `meta` message once per MQTT connect (in `maintain_mqtt()`,
  right after a successful `connect()`), **retained**, so a Pi that
  subscribes later still gets it immediately without waiting for the ESP32
  to reconnect.
- Meta payload format matches the existing frame style — plain text, no new
  library:
  ```
  <chip_id>,<rows>,<cols>
  ```
  e.g. `a1b2c3d4e5f6,16,15`.
- `smartmat/frame` payload format is unchanged (still just the CSV grid
  values) — only the topic name and client ID change.

## MQTT topic/meta scheme (summary)

| Purpose | Topic | Retained | Payload |
|---|---|---|---|
| Frame data | `smartmat/<chip_id>/frame` | yes (existing behavior) | CSV grid values |
| Mat metadata | `smartmat/<chip_id>/meta` | yes | `<chip_id>,<rows>,<cols>` |

## Pi side — discovery (`Raspberry Pi/sources/mqtt_source.py`)

- On connect, subscribe to the wildcard `smartmat/+/meta` so retained
  metadata from every mat ever seen arrives right away — including mats
  that are currently powered off (their last-known meta is still retained
  on the broker). The discovered list is "known mats," not "online mats."
- Maintain an in-memory map of `chip_id -> (rows, cols)` built from incoming
  meta messages, exposed so the GUI can populate its device dropdown.
- Selecting a specific mat subscribes to that mat's own
  `smartmat/<chip_id>/frame` (and keeps the meta subscription for shape).
  `MqttSource` takes the target `chip_id` as a constructor argument instead
  of connecting with no argument like today.
- State while a mat is selected: `connecting -> awaiting_meta -> ready`. If
  meta for the selected `chip_id` hasn't arrived within a short timeout
  (e.g. a few seconds), surface a clear "no metadata from this mat" error
  instead of silently guessing a shape.

## Grid shape propagation — Approach A (global `config` overwrite)

Once a mat's `(rows, cols)` is known (from its retained meta message), the
Pi sets `config.TOTAL_ROWS` / `config.TOTAL_COLS` to those values *before*
constructing any of the shape-dependent objects for that session
(calibration, recordings, GUI state, etc.) — the same point in
`gui/desktop.py` where a source is already (re)constructed today when the
user changes source/device.

This requires changing every consumer of these two constants from:
```python
from config import TOTAL_ROWS, TOTAL_COLS
```
to:
```python
import config
# ... config.TOTAL_ROWS, config.TOTAL_COLS
```
so each read happens live rather than being frozen at import time. Affected
files (confirmed by grep, mechanical change only — no function signatures
change):

- `general.py`
- `gui/desktop.py`
- `gui/calibration_window.py`
- `gui/diagnostics_window.py`
- `gui/web.py`
- `processing/calibration.py`
- `processing/recording.py`
- `processing/session_events.py`
- `processing/session_summary.py`
- `processing/sensor_health.py`
- `processing/temporal.py`
- `tests/test_phase4.py`

`sources/simulated_source.py` is **not** changed — it generates synthetic
data independent of any real mat, computing some module-level arrays
(`_ROWS`, `_COLS`) at import time from the config defaults. That's fine:
simulated scenarios aren't representing a specific physical mat, so they
keep using whatever `config.py`'s static defaults are.

Existing behavior that already supports this for free: `calibration.py` and
`recording.py` already save a `"grid_shape"` field in their JSON files and
reject loading one that doesn't match the current shape — so an old
16×15 calibration won't silently get applied to a 20×12 mat.

Known sharp edge (worth a one-line comment at the top of `config.py`):
anyone who writes `from config import TOTAL_ROWS` again in new code will
silently get a stale value instead of the live one.

## Pi side — nickname registry (`Raspberry Pi/mats.json`, new file)

- Gitignored, same pattern as `Raspberry Pi/config.py` and
  `Raspberry Pi/recordings/` — local, per-deployment data, not code.
- Schema: `{"<chip_id>": "<nickname>"}`.
- Loaded once at startup. If a discovered `chip_id` has no entry, the UI
  shows the raw chip ID until renamed.
- A rename action in the GUI (e.g. an "edit name" control next to the MQTT
  device dropdown) writes the new nickname into `mats.json` and
  immediately relabels the list — no reconnect needed to see the new name.

## GUI changes (`gui/desktop.py`)

- The MQTT branch of the existing device dropdown (currently a static
  `["(configured broker)"]` placeholder) becomes a live list built from
  `MqttSource`'s discovered `chip_id -> shape` map, each entry labeled with
  its nickname (from `mats.json`) or raw chip ID if unnamed.
- Add the rename control described above.
- No change to the Serial/Simulated branches of the dropdown.

## Testing

- Small `assert`-based self-check (or `test_*.py`, matching the existing
  `tests/` convention) for:
  - Meta payload parsing (`"<chip_id>,<rows>,<cols>"` → tuple), including
    the malformed/short-payload case.
  - That selecting a mat correctly overwrites `config.TOTAL_ROWS`/`COLS`
    before any shape-dependent object reads them.
- Existing `tests/test_phase4.py` already imports `TOTAL_ROWS`/`TOTAL_COLS`
  from config — update its import style along with the rest, no behavior
  change expected since config's static defaults are unchanged (16×15).
- Hardware-level check (manual, not automated): flash two ESP32 boards,
  confirm both stay connected simultaneously and both appear as separate
  entries in the Pi's mat list.
