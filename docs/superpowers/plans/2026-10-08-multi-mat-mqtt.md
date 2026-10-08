# Multi-mat MQTT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let any number of ESP32 mats share one broker, have the Pi app list them by nickname, and pick up each mat's grid size from a retained metadata message instead of a hardcoded constant.

**Architecture:** Each ESP32 uses its chip ID as MQTT client ID and topic prefix (`smartmat/<chip_id>/frame`, `smartmat/<chip_id>/meta`). On the Pi, `MqttSource()` with no chip ID is a discovery listener that fills a `chip_id -> (rows, cols)` map for the device dropdown; `MqttSource(chip_id)` streams one mat and refuses to start without that mat's metadata. When a mat is connected, `gui/desktop.py` overwrites `config.TOTAL_ROWS`/`TOTAL_COLS` (spec's Approach A) and restarts everything sized to the old grid; every consumer reads those two values live through `config.`.

**Tech Stack:** Arduino/PlatformIO + PubSubClient (ESP32); Python 3.13, paho-mqtt 2.x, Tkinter, numpy, `unittest` (Pi).

**Spec:** `docs/superpowers/specs/2026-10-07-multi-mat-mqtt-design.md`

## Global Constraints

- Meta payload is plain text `<chip_id>,<rows>,<cols>` (e.g. `a1b2c3d4e5f6,16,15`), published retained, once per MQTT connect. No new library on either side.
- Frame payload is unchanged (CSV grid values, retained); only the topic and client ID change.
- Chip ID is `ESP.getEfuseMac()` as a lowercase hex string.
- Grid shape propagation is the global `config` overwrite. Consumers use `import config` + `config.TOTAL_ROWS` / `config.TOTAL_COLS`; no function signatures change. (`gui/desktop.py` already has `import config as app_config` and keeps that name.)
- `sources/simulated_source.py` and `sources/serial_source.py` are not changed. Serial and Simulated keep `config.py`'s static shape.
- `mats.json` lives in `Raspberry Pi/`, is gitignored, schema `{"<chip_id>": "<nickname>"}`.
- No new dependencies. No commits (the working tree already carries unrelated uncommitted work on `main`; staging is left to Even). No AI attribution anywhere.
- After every task: `python -m unittest discover -s tests -v` from `Raspberry Pi/`. Baseline before this plan: 46 tests, OK.

## Where the spec did not match the code

Found while reading the current code; each is handled in the task named.

1. **Shape-dependent objects are not rebuilt on connect.** The spec says the overwrite happens "before constructing" calibration/GUI state at the point where the source is constructed. In `gui/desktop.py`, `Calibration`, `PressureCalibration`, `SensorHealth`, `TemporalAnalysis` are built once in `__init__`; `_connect()` only resets some of them. Task 5 adds `_apply_grid_shape()` which restarts them in place.
2. **Nothing puts the shape back.** `simulated_source.py` freezes its arrays at import (16x15) and Serial is config-driven, so after an MQTT mat of another size the app must return to the static default for every non-MQTT source. Task 5.
3. **The dropdown needs data before a mat is selected.** The spec has `MqttSource` take the target chip ID, but the device list has to be filled before any mat is chosen. Task 3 makes the chip ID optional: without one the source only listens for metadata (own client ID, so it does not collide with the streaming connection).
4. **16x15 and 20x12 are both 240 values.** The frame-length check cannot tell them apart, so a frame from a 20x12 mat would be silently reshaped to 16x15 if parsed too early. Task 3: a selected source ignores frames until `config` holds its mat's shape.
5. **`config.mqtt_topic` becomes dead.** Task 3 removes it; the topic prefix is a constant in `mqtt_source.py`.
6. **`tests/test_calibration_profiles.py`** was added after the spec's grep and also does `from config import TOTAL_ROWS, TOTAL_COLS`. Converted in Task 1 with the other twelve.
7. **A recording cannot span two grid sizes** (`Recorder.save()` writes the shape at save time). Task 5 saves an active recording before the grid changes.
8. **paho version.** `mqtt_source.py` already uses the paho 2.x API (`CallbackAPIVersion`); this PC has 1.6.1 and `requirements.txt` is unpinned. Tests replace the paho module with a mock so they run on either; Task 6 pins `paho-mqtt>=2.0`.

Not built, flagged only: recordings made on a non-default-size mat cannot be replayed (playback uses the static shape and `load_session` rejects the mismatch); two mats of the same size share the in-memory tare/calibration when switching.

## Review Focus

1. A frame arriving before the app has switched to the mat's shape (including the 240-value coincidence) must be ignored, not misparsed or counted as malformed. Test in Task 3.
2. Metadata that is short, non-numeric, zero/negative/huge, or whose chip ID could inject topic wildcards (`+`, `#`, `/`) must be dropped, not listed. Test in Task 3.
3. A selected mat whose metadata never arrives must fail with a clear message and leave no connection running. Test in Task 3.
4. Going from a different-sized MQTT mat back to Simulated must restore the default grid, and frames of the new size must flow through the whole per-frame pipeline. Test in Task 5.
5. A missing, corrupt or non-object `mats.json`, and two mats given the same nickname, must not break the device list. Tests in Task 4.

## File Structure

| File | Change |
|---|---|
| `ESP32/src/main.cpp` | chip-ID client ID + topics, retained meta on connect |
| `Raspberry Pi/general.py` | live shape reads; `load_mat_names`, `save_mat_names`, `mat_labels` |
| `Raspberry Pi/sources/mqtt_source.py` | `parse_meta`, discovery map, chip-ID argument, start waits for meta |
| `Raspberry Pi/gui/desktop.py` | live shape reads, `_apply_grid_shape`, live MQTT device list, Rename button |
| `gui/calibration_window.py`, `gui/diagnostics_window.py`, `gui/web.py`, `processing/calibration.py`, `processing/recording.py`, `processing/session_events.py`, `processing/session_summary.py`, `processing/sensor_health.py`, `processing/temporal.py`, `tests/test_phase4.py`, `tests/test_calibration_profiles.py` | import style only |
| `Raspberry Pi/tests/test_multi_mat.py` | new: all tests for this plan |
| `Raspberry Pi/config.example.py`, `config.py` | stale-import warning, drop `mqtt_topic` |
| `.gitignore`, `requirements.txt`, READMEs, `STATUS.md`, `notes.md` | housekeeping |

---

### Task 1: Read the grid shape live

**Files:**
- Modify: `general.py`, `gui/desktop.py`, `gui/calibration_window.py`, `gui/diagnostics_window.py`, `gui/web.py`, `processing/calibration.py`, `processing/recording.py`, `processing/session_events.py`, `processing/session_summary.py`, `processing/sensor_health.py`, `processing/temporal.py`, `tests/test_phase4.py`, `tests/test_calibration_profiles.py`, `config.example.py`, `config.py`
- Test: `tests/test_multi_mat.py` (create)

**Interfaces:**
- Produces: every module reads `config.TOTAL_ROWS` / `config.TOTAL_COLS` at call time. Test helper `use_shape(test, rows, cols)` in `tests/test_multi_mat.py`.

- [ ] **Step 1: Write the failing tests** - create `tests/test_multi_mat.py`:

```python
"""Multi-mat MQTT: live grid shape, meta handshake, nickname registry, device list."""

import unittest

import numpy as np

import config
from general import parse_frame_text_with_reason
from gui import web
from processing.calibration import IndividualCalibration
from processing.recording import Recorder, load_session
from processing.sensor_health import SensorHealth
from processing.temporal import TemporalAnalysis

DEFAULT_SHAPE = (config.TOTAL_ROWS, config.TOTAL_COLS)


def use_shape(test, rows, cols):
    """Overwrite the grid size the way the GUI does, and put it back after the test"""
    test.addCleanup(setattr, config, "TOTAL_ROWS", DEFAULT_SHAPE[0])
    test.addCleanup(setattr, config, "TOTAL_COLS", DEFAULT_SHAPE[1])
    config.TOTAL_ROWS, config.TOTAL_COLS = rows, cols


class GridShapeTests(unittest.TestCase):
    def test_consumers_read_an_overwritten_shape(self):
        use_shape(self, 20, 12)
        grid, reason = parse_frame_text_with_reason(",".join(["5"] * 240))
        self.assertIsNone(reason)
        self.assertEqual(grid.shape, (20, 12))
        self.assertEqual(TemporalAnalysis().exposure.shape, (20, 12))
        self.assertEqual(SensorHealth().states.shape, (20, 12))
        calibration = IndividualCalibration.default()
        self.assertTrue(calibration.is_calibrated(19, 11))
        self.assertEqual(calibration.apply(grid).shape, (20, 12))
        self.assertIn("var ROWS = 20;", web.index())

    def test_frame_of_the_old_size_is_rejected(self):
        use_shape(self, 10, 8)
        self.assertEqual(parse_frame_text_with_reason(",".join(["5"] * 240))[1], "grid_size")
        self.assertIsNone(parse_frame_text_with_reason(",".join(["5"] * 80))[1])

    def test_recording_keeps_the_shape_it_was_made_with(self):
        use_shape(self, 20, 12)
        recorder = Recorder("multi_mat_shape_test")
        recorder.add_frame(np.full((20, 12), 7.0), timestamp=1.0)
        path = recorder.save()
        self.addCleanup(path.unlink)
        self.assertEqual(load_session(path)[0].shape, (20, 12))
        config.TOTAL_ROWS, config.TOTAL_COLS = DEFAULT_SHAPE
        with self.assertRaises(ValueError):
            load_session(path)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, expect failure** - `python -m unittest discover -s tests -p "test_multi_mat.py" -v` -> the three tests fail (shapes stay 16x15 because the names were frozen at import).

- [ ] **Step 3: Convert the imports.** In each file listed, remove `TOTAL_ROWS, TOTAL_COLS` from the `from config import ...` line (delete the line if nothing else is left), add `import config` if the file does not have it, and prefix every use: `TOTAL_ROWS` -> `config.TOTAL_ROWS`, `TOTAL_COLS` -> `config.TOTAL_COLS`. In `gui/desktop.py` use the existing alias: `app_config.TOTAL_ROWS`. No other change. Afterwards this must print nothing:

```bash
grep -rnE "(^|[^.A-Za-z_])TOTAL_(ROWS|COLS)" --include="*.py" . | grep -v "sources/simulated_source.py" | grep -vE "config(\.example)?\.py:"
```

- [ ] **Step 4: Config comments.** In both `config.example.py` and `config.py`, directly under the module docstring:

```python
# NOTE: always read the grid size as config.TOTAL_ROWS / config.TOTAL_COLS. A
# `from config import TOTAL_ROWS` copy goes stale when an MQTT mat of another size connects.
```

and replace `# These must match src/main.cpp on the ESP32` with:

```python
# Grid size for Serial/Simulated (Serial: must match src/main.cpp). An MQTT mat reports its own.
```

- [ ] **Step 5: Run everything** - `python -m unittest discover -s tests -v` -> 49 tests, OK.

---

### Task 2: ESP32 chip-ID topics and meta handshake

**Files:**
- Modify: `ESP32/src/main.cpp`, `ESP32/README.md`

**Interfaces:**
- Produces (wire format): client ID `<chip_id>`; `smartmat/<chip_id>/frame` (retained CSV, unchanged payload); `smartmat/<chip_id>/meta` (retained `<chip_id>,<rows>,<cols>`), published right after each successful connect.

- [ ] **Step 1: Replace the topic/client constants** (`main.cpp` "Wifi and MQTT" block):

```cpp
// Wifi and MQTT
const char* mqtt_topic_prefix = "smartmat"; // topics: smartmat/<chip_id>/frame and .../meta
const uint32_t reconnect_retry_interval_ms = 5000;
const uint16_t mqtt_packet_buffer_size = 1500;  // 240-value frame is ~1.2 KB --> this leaves headroom
```

- [ ] **Step 2: Add the identity buffers** to the "Variables" block:

```cpp
char chip_id[13];     // 12 hex digits, also used as MQTT client id (must be unique per board)
char frame_topic[40];
char meta_topic[40];
char meta_text[24];   // "<chip_id>,<rows>,<cols>"
```

- [ ] **Step 3: Add `build_identity()`** above `wifi_is_connected()`:

```cpp
// Chip id --> MQTT client id, topics and the meta message that tells the Pi our grid size
void build_identity() {
  const uint64_t mac = ESP.getEfuseMac();
  snprintf(chip_id, sizeof(chip_id), "%04x%08x",
           static_cast<unsigned>(mac >> 32) & 0xFFFFU, static_cast<unsigned>(mac & 0xFFFFFFFFU));
  snprintf(frame_topic, sizeof(frame_topic), "%s/%s/frame", mqtt_topic_prefix, chip_id);
  snprintf(meta_topic, sizeof(meta_topic), "%s/%s/meta", mqtt_topic_prefix, chip_id);
  snprintf(meta_text, sizeof(meta_text), "%s,%u,%u", chip_id,
           static_cast<unsigned>(grid_rows), static_cast<unsigned>(grid_cols));
}
```

- [ ] **Step 4: Connect with the chip ID and publish meta** - replace the last two lines of `maintain_mqtt()`:

```cpp
  if (mqtt_client.connect(chip_id, mqtt_username, mqtt_password)) {
    mqtt_client.publish(meta_topic, meta_text, true); // retained: a Pi that subscribes later still gets it
    if (serial_debug) Serial.printf("MQTT connected as %s\n", chip_id);
  } else if (serial_debug) {
    Serial.println("MQTT not connected, will try again ...");
  }
```

- [ ] **Step 5: Use the new topic** in `send_frame()`: `mqtt_client.publish(frame_topic, frame_text, true);`

- [ ] **Step 6: Call `build_identity();`** in `setup()` right after `Serial.println("Smartmat Resistive V1");`, followed by `Serial.printf("Chip id: %s\n", chip_id);`.

- [ ] **Step 7: Compile** - `pio run` in `ESP32/` -> `SUCCESS`. (Flashing and the two-board check are manual, see "Hardware check".)

- [ ] **Step 8: README** - in `ESP32/README.md` replace the "grid size and baud rate must match" line and step 5 of "How a scan works" with the new topics and the meta message.

---

### Task 3: `MqttSource` discovery and per-mat streaming

**Files:**
- Modify: `sources/mqtt_source.py`, `config.example.py`, `config.py` (remove `mqtt_topic`)
- Test: `tests/test_multi_mat.py`

**Interfaces:**
- Consumes: `config.TOTAL_ROWS/COLS` read live (Task 1).
- Produces:
  - `parse_meta(text) -> (chip_id: str, rows: int, cols: int) | None`
  - `MqttSource(chip_id=None)`; attributes `chip_id`, `mats: dict[str, tuple[int, int]]`, `latest`, `quality`; properties `shape -> (rows, cols) | None`, `state -> "connecting" | "awaiting_meta" | "ready"`; `start()` raises `TimeoutError` ("no metadata from mat ...") when a selected mat's meta does not arrive within `META_TIMEOUT_S`; `stop()`.

- [ ] **Step 1: Write the failing tests** - add to `tests/test_multi_mat.py` (imports at the top: `import types`, `from unittest import mock`, `from sources import mqtt_source`, `from sources.mqtt_source import MqttSource, parse_meta`):

```python
def make_source(chip_id=None):
    with mock.patch.object(mqtt_source, "mqtt"):  # no real paho client, no network
        return MqttSource(chip_id)


def message(topic, text):
    return types.SimpleNamespace(topic=topic, payload=text.encode("ascii"))


def connect(source, failed=False):
    source._on_connect(source._client, None, None, types.SimpleNamespace(is_failure=failed))


class MetaParsingTests(unittest.TestCase):
    def test_valid_payload(self):
        self.assertEqual(parse_meta("a1b2c3d4e5f6,16,15"), ("a1b2c3d4e5f6", 16, 15))
        self.assertEqual(parse_meta(" a1b2 , 20 ,12\n"), ("a1b2", 20, 12))

    def test_malformed_payloads(self):
        for text in ("", "a1b2", "a1b2,16", "a1b2,16,15,1", "a1b2,x,15", "a1b2,16,1.5",
                     "a1b2,0,15", "a1b2,16,-1", "a1b2,16,999", ",16,15",
                     "a/b,16,15", "+,16,15", "#,16,15"):
            with self.subTest(text=text):
                self.assertIsNone(parse_meta(text))


class MqttSourceTests(unittest.TestCase):
    def test_discovery_lists_every_mat_with_valid_meta(self):
        source = make_source()
        connect(source)
        source._client.subscribe.assert_called_once_with("smartmat/+/meta")
        source._on_message(None, None, message("smartmat/aaa111/meta", "aaa111,16,15"))
        source._on_message(None, None, message("smartmat/bbb222/meta", "bbb222,20,12"))
        source._on_message(None, None, message("smartmat/ccc333/meta", "garbage"))
        source._on_message(None, None, message("smartmat/ddd444/meta", "eee555,16,15"))  # id mismatch
        self.assertEqual(source.mats, {"aaa111": (16, 15), "bbb222": (20, 12)})
        self.assertEqual(source.state, "ready")

    def test_selected_mat_goes_connecting_awaiting_meta_ready(self):
        source = make_source("bbb222")
        self.assertEqual(source.state, "connecting")
        connect(source)
        self.assertEqual([call.args[0] for call in source._client.subscribe.call_args_list],
                         ["smartmat/+/meta", "smartmat/bbb222/frame"])
        self.assertEqual(source.state, "awaiting_meta")
        self.assertIsNone(source.shape)
        source._on_message(None, None, message("smartmat/aaa111/meta", "aaa111,16,15"))
        self.assertEqual(source.state, "awaiting_meta")
        source._on_message(None, None, message("smartmat/bbb222/meta", "bbb222,20,12"))
        self.assertEqual(source.state, "ready")
        self.assertEqual(source.shape, (20, 12))

    def test_refused_connection_does_not_subscribe(self):
        source = make_source("bbb222")
        connect(source, failed=True)
        source._client.subscribe.assert_not_called()
        self.assertEqual(source.state, "connecting")

    def test_frames_wait_until_the_app_uses_the_mats_shape(self):
        source = make_source("bbb222")
        connect(source)
        frame = message("smartmat/bbb222/frame", ",".join(["5"] * 240))
        source._on_message(None, None, frame)  # before meta
        source._on_message(None, None, message("smartmat/bbb222/meta", "bbb222,20,12"))
        source._on_message(None, None, frame)  # meta known, app still on 16x15: same 240 values
        self.assertIsNone(source.latest.take())
        self.assertEqual(source.quality.snapshot()["received"], 0)
        use_shape(self, 20, 12)
        source._on_message(None, None, frame)
        self.assertEqual(source.latest.take().shape, (20, 12))
        source._on_message(None, None, message("smartmat/bbb222/frame", "1,2,3"))
        self.assertEqual(source.quality.snapshot()["unexpected_grid_size"], 1)

    def test_start_fails_clearly_when_meta_never_arrives(self):
        source = make_source("bbb222")
        with mock.patch.object(mqtt_source, "META_TIMEOUT_S", 0.01):
            with self.assertRaisesRegex(TimeoutError, "no metadata from mat bbb222"):
                source.start()
        source._client.loop_stop.assert_called_once()
        source._client.disconnect.assert_called_once()

    def test_start_returns_once_meta_is_in(self):
        source = make_source("bbb222")
        source._on_message(None, None, message("smartmat/bbb222/meta", "bbb222,20,12"))
        source.start()
        source._client.connect.assert_called_once_with(config.broker_host, config.broker_port)
        source._client.loop_stop.assert_not_called()

    def test_discovery_start_never_blocks_on_the_broker(self):
        source = make_source()
        source.start()
        source._client.connect_async.assert_called_once_with(config.broker_host, config.broker_port)
        source._client.connect.assert_not_called()
```

- [ ] **Step 2: Run, expect failure** - `python -m unittest discover -s tests -p "test_multi_mat.py" -v` -> ImportError (`parse_meta` does not exist).

- [ ] **Step 3: Implement** - replace `sources/mqtt_source.py` from the imports down to the end with:

```python
import threading

import paho.mqtt.client as mqtt
import config
from general import LatestFrame, parse_frame_text, parse_frame_text_with_reason
from processing.source_quality import SourceQuality

TOPIC_PREFIX = "smartmat"  # must match mqtt_topic_prefix in ESP32/src/main.cpp
META_TIMEOUT_S = 3.0       # how long start() waits for the selected mat's metadata
MAX_GRID_SIDE = 255        # the ESP32 keeps rows/cols in a uint8


def parse_frame(payload):
    """Decode one MQTT payload and convert it to grid"""

    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError:
        return None
    return parse_frame_text(text)


def parse_meta(text):
    """Convert a "<chip_id>,<rows>,<cols>" meta payload to (chip_id, rows, cols), None if invalid"""

    pieces = [piece.strip() for piece in text.split(",")]
    if len(pieces) != 3 or not pieces[0].isalnum():  # isalnum also keeps topic wildcards out
        return None
    try:
        rows, cols = int(pieces[1]), int(pieces[2])
    except ValueError:
        return None
    if not (1 <= rows <= MAX_GRID_SIDE and 1 <= cols <= MAX_GRID_SIDE):
        return None
    return pieces[0], rows, cols


class MqttSource:
    """Streams grids from one ESP32 mat over MQTT, using paho network thread.

    Without a chip_id it only listens for every mat's metadata (for the device list).
    """

    def __init__(self, chip_id=None):
        self.chip_id = chip_id
        self.mats = {}  # chip_id -> (rows, cols) for every mat the broker has metadata for
        self.latest = LatestFrame()
        self.quality = SourceQuality()
        self._connected = False
        self._meta_seen = threading.Event()
        # own client id for the listener, so it can stay up next to a streaming connection
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                   client_id="smartmat-pi" if chip_id else "smartmat-pi-discovery")
        self._client.username_pw_set(config.mqtt_username, config.mqtt_password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    @property
    def shape(self):
        """(rows, cols) reported by the selected mat, None until its metadata arrives"""
        return self.mats.get(self.chip_id)

    @property
    def state(self):
        """Startup progress: connecting -> awaiting_meta -> ready"""
        if not self._connected:
            return "connecting"
        if self.chip_id is not None and self.shape is None:
            return "awaiting_meta"
        return "ready"

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code.is_failure:
            print(f"MQTT broker refused the connection: {reason_code}")
            return
        self._connected = True
        print(f"Connected to {config.broker_host}:{config.broker_port}")
        client.subscribe(f"{TOPIC_PREFIX}/+/meta")  # retained, so known mats arrive right away
        if self.chip_id is not None:
            client.subscribe(f"{TOPIC_PREFIX}/{self.chip_id}/frame")

    def _on_message(self, client, userdata, message):
        try:
            text = message.payload.decode("ascii")
        except UnicodeDecodeError:
            text = None
        if message.topic.endswith("/meta"):
            meta = parse_meta(text or "")
            if meta is not None and message.topic == f"{TOPIC_PREFIX}/{meta[0]}/meta":
                self.mats[meta[0]] = meta[1:]
                if meta[0] == self.chip_id:
                    self._meta_seen.set()
            return
        if self.shape != (config.TOTAL_ROWS, config.TOTAL_COLS):
            return  # the app has not switched to this mat's grid size yet
        grid, reason = (None, "malformed") if text is None else parse_frame_text_with_reason(text)
        self.quality.packet(reason, timestamp=False)
        if grid is not None:
            if self.latest.set(grid):
                self.quality.drop()

    def start(self):
        """Connect and start paho's background network loop.

        With a mat selected this raises if the broker is unreachable or the mat's metadata
        does not arrive. The metadata listener never blocks: paho keeps retrying in its thread.
        """
        if self.chip_id is None:
            self._client.connect_async(config.broker_host, config.broker_port)
            self._client.loop_start()
            return
        self._client.connect(config.broker_host, config.broker_port)
        self._client.loop_start()
        if not self._meta_seen.wait(META_TIMEOUT_S):
            state = self.state
            self.stop()
            raise TimeoutError(f"no metadata from mat {self.chip_id} ({state})")

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()
```

Also update the module docstring's first line to `"""Reads frames from the ESP32 mats over MQTT"""`.

- [ ] **Step 4: Remove the dead setting** - delete the `mqtt_topic = "smartmat/frame"` line from `config.example.py` and `config.py`.

- [ ] **Step 5: Run everything** - `python -m unittest discover -s tests -v` -> 58 tests, OK.

---

### Task 4: Nickname registry

**Files:**
- Modify: `general.py`, `.gitignore`
- Test: `tests/test_multi_mat.py`

**Interfaces:**
- Produces: `MATS_FILE: Path`; `load_mat_names(path=MATS_FILE) -> dict[str, str]`; `save_mat_names(names, path=MATS_FILE) -> None`; `mat_labels(chip_ids, names) -> dict[label, chip_id]`.

- [ ] **Step 1: Write the failing tests** - add to `tests/test_multi_mat.py` (imports: `import tempfile`, `from pathlib import Path`, `from general import load_mat_names, mat_labels, save_mat_names`):

```python
class MatNamesTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "mats.json"

    def test_names_survive_a_restart(self):
        save_mat_names({"aaa111": "Wheelchair"}, self.path)
        self.assertEqual(load_mat_names(self.path), {"aaa111": "Wheelchair"})

    def test_missing_corrupt_or_wrong_file_means_no_names(self):
        self.assertEqual(load_mat_names(self.path), {})
        for text in ("{not json", '["aaa111"]', ""):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                self.assertEqual(load_mat_names(self.path), {})

    def test_labels_use_nickname_else_chip_id(self):
        self.assertEqual(mat_labels({"bbb222": (20, 12), "aaa111": (16, 15)}, {"bbb222": "Bed"}),
                         {"aaa111": "aaa111", "Bed": "bbb222"})

    def test_duplicate_nicknames_stay_selectable(self):
        self.assertEqual(mat_labels(["aaa111", "bbb222"], {"aaa111": "Bed", "bbb222": "Bed"}),
                         {"Bed": "aaa111", "Bed (bbb222)": "bbb222"})
```

- [ ] **Step 2: Run, expect failure** - ImportError (`load_mat_names`).

- [ ] **Step 3: Implement** - in `general.py` add `import json` and `from pathlib import Path` to the imports, and after `parse_frame_text_with_reason`:

```python
MATS_FILE = Path(__file__).resolve().parent / "mats.json"  # local nicknames, not in git


def load_mat_names(path=MATS_FILE):
    """Nicknames for MQTT mats as {chip_id: nickname}; empty if there is no usable file"""
    try:
        with open(path, encoding="utf-8") as file:
            names = json.load(file)
    except (OSError, ValueError):
        return {}
    if not isinstance(names, dict):
        return {}
    return {str(chip_id): str(name) for chip_id, name in names.items()}


def save_mat_names(names, path=MATS_FILE):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(names, file, indent=2)


def mat_labels(chip_ids, names):
    """Device-list label -> chip id: the nickname if the mat has one, else the raw chip id"""
    labels = {}
    for chip_id in sorted(chip_ids):
        label = names.get(chip_id) or chip_id
        if label in labels:  # two mats given the same nickname
            label = f"{label} ({chip_id})"
        labels[label] = chip_id
    return labels
```

- [ ] **Step 4: Gitignore** - add `Raspberry Pi/mats.json` under `Raspberry Pi/config.py` in the repo-root `.gitignore`.

- [ ] **Step 5: Run everything** - `python -m unittest discover -s tests -v` -> 62 tests, OK.

---

### Task 5: GUI device list, rename, and grid switching

**Files:**
- Modify: `gui/desktop.py`
- Test: `tests/test_multi_mat.py`

**Interfaces:**
- Consumes: `MqttSource(chip_id=None)`, `.mats`, `.shape`, `.start()`, `.stop()` (Task 3); `load_mat_names`, `save_mat_names`, `mat_labels` (Task 4).
- Produces (on `DesktopApp`): `mat_names`, `_mats`, `_mat_ids`, `_discovery`; `_apply_grid_shape(rows, cols)`, `_sync_mats()`, `_rename_mat()`; module constant `DEFAULT_SHAPE`.

- [ ] **Step 1: Write the failing tests** - add to `tests/test_multi_mat.py` (imports: `import json`, `import tkinter as tk`, `from general import LatestFrame`, `from processing.recording import RECORDINGS_DIR`, `from processing.source_quality import SourceQuality`):

```python
class FakeMqttSource:
    """Stands in for MqttSource so the GUI tests need no broker"""

    mats = {"aaa111": (20, 12), "bbb222": (16, 15)}

    def __init__(self, chip_id=None):
        self.chip_id = chip_id
        self.latest = LatestFrame()
        self.quality = SourceQuality()
        self.shape = self.mats.get(chip_id)

    def start(self):
        pass

    def stop(self):
        pass


class DesktopMatTests(unittest.TestCase):
    def setUp(self):
        from gui import desktop
        self.desktop = desktop
        for patch in (mock.patch.object(desktop, "MqttSource", FakeMqttSource),
                      mock.patch.object(desktop, "load_mat_names", return_value={"bbb222": "Bed"}),
                      mock.patch.object(desktop, "save_mat_names")):
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(setattr, config, "TOTAL_ROWS", DEFAULT_SHAPE[0])
        self.addCleanup(setattr, config, "TOTAL_COLS", DEFAULT_SHAPE[1])
        try:
            self.app = desktop.DesktopApp()
        except tk.TclError:
            self.skipTest("Tk display unavailable")
        self.addCleanup(self.app._on_close)

    def show_mats(self):
        self.app.source_var.set("MQTT")
        self.app._refresh_devices()
        self.app._sync_mats()

    def test_mqtt_devices_are_listed_by_nickname_or_chip_id(self):
        self.show_mats()
        self.assertEqual(list(self.app.device_menu.cget("values")), ["aaa111", "Bed"])
        self.assertEqual(self.app.device_var.get(), "aaa111")

    def test_rename_relabels_at_once_and_is_saved(self):
        self.show_mats()
        with mock.patch.object(self.desktop.simpledialog, "askstring", return_value=" Chair "):
            self.app._rename_mat()
        self.assertEqual(list(self.app.device_menu.cget("values")), ["Chair", "Bed"])
        self.assertEqual(self.app.device_var.get(), "Chair")
        self.desktop.save_mat_names.assert_called_once_with({"bbb222": "Bed", "aaa111": "Chair"})

    def test_connecting_to_a_mat_switches_the_grid_and_back(self):
        self.show_mats()
        self.app._connect()
        self.assertEqual(self.app.source.chip_id, "aaa111")
        self.assertEqual((config.TOTAL_ROWS, config.TOTAL_COLS), (20, 12))
        self.assertEqual(self.app.temporal.exposure.shape, (20, 12))
        self.assertEqual(self.app.sensor_health.states.shape, (20, 12))
        self.assertTrue(self.app.pressure_calibration.is_calibrated(19, 11))
        self.assertEqual(self.app.grid_info_var.get(), "Grid: 20 x 12")
        self.app._handle_new_frame(np.full((20, 12), 10.0), sample_time=1)
        self.assertEqual(self.app.frame["pressure"].shape, (20, 12))
        self.app._update_plot()

        self.app.source_var.set("Simulated")
        self.app._refresh_devices()
        self.app._connect()
        self.assertEqual((config.TOTAL_ROWS, config.TOTAL_COLS), DEFAULT_SHAPE)
        self.assertIsNone(self.app.frame)
        self.app._handle_new_frame(np.full(DEFAULT_SHAPE, 10.0), sample_time=1)
        self.assertEqual(self.app.frame["pressure"].shape, DEFAULT_SHAPE)

    def test_connect_without_a_mat_says_so(self):
        with mock.patch.object(FakeMqttSource, "mats", {}):
            self.show_mats()
            self.app._connect()
        self.assertIsNone(self.app.source)
        self.assertIn("no mat selected", self.app.status_var.get())
        self.assertEqual((config.TOTAL_ROWS, config.TOTAL_COLS), DEFAULT_SHAPE)

    def test_recording_is_saved_before_the_grid_changes(self):
        self.app._handle_new_frame(np.full(DEFAULT_SHAPE, 10.0), sample_time=1)
        self.app.recorder = Recorder("multi_mat_switch_test")
        self.app.recorder.add_frame(self.app.raw_grid, timestamp=1)
        self.app._apply_grid_shape(20, 12)
        self.assertIsNone(self.app.recorder)
        saved = list(RECORDINGS_DIR.glob("multi_mat_switch_test_*.json"))
        self.assertEqual(len(saved), 1)
        self.addCleanup(saved[0].unlink)
        self.assertEqual(json.loads(saved[0].read_text())["grid_shape"], list(DEFAULT_SHAPE))
```

- [ ] **Step 2: Run, expect failure** - AttributeError (`load_mat_names` not in `gui.desktop`).

- [ ] **Step 3: Imports and constant** in `gui/desktop.py`:

```python
from general import load_mat_names, mat_labels, save_mat_names
from processing.calibration import Calibration, IndividualCalibration, PressureCalibration, UniformCalibration
```

and below `HEATMAP_COLORS`:

```python
DEFAULT_SHAPE = (app_config.TOTAL_ROWS, app_config.TOTAL_COLS)  # config.py's own size, used by Serial/Simulated
```

- [ ] **Step 4: State** - in `__init__`, after `self.web_server = None`:

```python
        self.mat_names = load_mat_names()  # chip id -> nickname
        self._mats = {}                    # chip id -> (rows, cols), as last shown in the device list
        self._mat_ids = {}                 # device-list label -> chip id
        self._discovery = None             # MqttSource that only listens for mats' metadata
```

- [ ] **Step 5: Rename button** - in `_build_connection_bar`, right after `self.device_menu.pack(...)`:

```python
        self.rename_button = ttk.Button(bar, text="Rename...", command=self._rename_mat)
        self.rename_button.pack(side=tk.LEFT, padx=(0, 8))
```

- [ ] **Step 6: Live grid label** - in `_build_about_panel` replace the `Grid:` info line with:

```python
        self.grid_info_var = tk.StringVar(value=f"Grid: {app_config.TOTAL_ROWS} x {app_config.TOTAL_COLS}")
        ttk.Label(panel, textvariable=self.grid_info_var).pack(anchor="w")
```

- [ ] **Step 7: Device list** - in `_refresh_devices`, after `previous = self.device_var.get()` add:

```python
        self.rename_button.state(["!disabled" if source == "MQTT" else "disabled"])
```

and replace the MQTT branch with:

```python
        elif source == "MQTT":
            if self._discovery is None:
                try:
                    discovery = MqttSource()  # no mat selected: only listens for mats' metadata
                    discovery.start()
                    self._discovery = discovery
                except Exception as error:
                    self.status_var.set(f"Could not look for mats: {error}")
            selected = self._mat_ids.get(previous)
            self._mat_ids = mat_labels(self._mats, self.mat_names)
            values = list(self._mat_ids)
            # keep the same mat selected even if it was just renamed
            default = next((label for label, chip_id in self._mat_ids.items() if chip_id == selected),
                           values[0] if values else "")
```

Then add below `_refresh_devices`:

```python
    def _sync_mats(self):
        """Relist the MQTT devices when the broker has reported a new or changed mat"""
        if self._discovery is not None and self._discovery.mats != self._mats:
            self._mats = dict(self._discovery.mats)
            if self.source_var.get() == "MQTT":
                self._refresh_devices()

    def _rename_mat(self):
        chip_id = self._mat_ids.get(self.device_var.get())
        if chip_id is None:
            self.status_var.set("Select a mat to rename")
            return
        name = simpledialog.askstring(
            "Rename mat", f"Name for mat {chip_id} (leave empty to show the chip ID):",
            initialvalue=self.mat_names.get(chip_id, ""), parent=self.root)
        if name is None:
            return
        if name.strip():
            self.mat_names[chip_id] = name.strip()
        else:
            self.mat_names.pop(chip_id, None)
        try:
            save_mat_names(self.mat_names)
        except OSError as error:
            self.status_var.set(f"Could not save mat name: {error}")
        self._refresh_devices()
```

- [ ] **Step 8: Grid switching** - add above `_connect`:

```python
    def _apply_grid_shape(self, rows, cols):
        """Switch the app to a mat's grid size; everything sized to the old grid starts over"""
        if (rows, cols) == (app_config.TOTAL_ROWS, app_config.TOTAL_COLS):
            return
        if self.recorder is not None:
            self._toggle_recording()  # a recording cannot span two grid sizes: save it at the old one
        app_config.TOTAL_ROWS, app_config.TOTAL_COLS = rows, cols
        self.calibration.baseline = None
        try:
            self.pressure_calibration.individual = IndividualCalibration.default()
        except ValueError:  # the configured startup calibration file is for another grid size
            self.pressure_calibration.individual = IndividualCalibration()
        self.pressure_calibration.uniform = UniformCalibration()
        self.pressure_calibration.use("individual")
        for mode in MODES:
            mode.reset()
        self.temporal.reset_all()
        self.hotspots.reset()
        self.motion.reset()
        self.sensor_health.reset()
        self.frame = self.raw_grid = self.current_grid = self.pre_baseline_grid = None
        self.reference_grid = self.comparison_grid = None
        self.difference_var.set(False)
        self.selected_cell = None
        self.selected_cell_var.set("Cell: click the 2D plot")
        self.roi = self.roi_corner = None
        self.selecting_roi = False
        self.cell_history.clear()
        self.cop_history.clear()
        self.roi_history.clear()
        self.grid_info_var.set(f"Grid: {rows} x {cols}")
        web.update_grid(None)
        self._update_stats()
        self._build_plot()
```

- [ ] **Step 9: Connect flow** - in `_connect`, the `try:` block starts with:

```python
            if source_name != "MQTT":
                self._apply_grid_shape(*DEFAULT_SHAPE)  # only MQTT mats report their own size
            if source_name == "Serial":
                self.source = SerialSource(device)
            elif source_name == "MQTT":
                if device not in self._mat_ids:
                    raise ValueError("no mat selected (none has reported to the broker yet)")
                self.source = MqttSource(self._mat_ids[device])
```

and directly after `self.source.start()`:

```python
            if source_name == "MQTT":
                self._apply_grid_shape(*self.source.shape)  # start() only returns once the mat reported it
```

- [ ] **Step 10: Poll and close** - in `_poll`, first line of the body: `self._sync_mats()`. In `_on_close`, before `if self.web_server is not None:`:

```python
        if self._discovery is not None:
            self._discovery.stop()
```

- [ ] **Step 11: Run everything** - `python -m unittest discover -s tests -v` -> 67 tests, OK.

---

### Task 6: Docs and housekeeping

**Files:**
- Modify: `Raspberry Pi/requirements.txt`, `Raspberry Pi/README.md`, `Raspberry Pi/STATUS.md`, `Raspberry Pi/notes.md`

- [ ] **Step 1:** `requirements.txt`: `paho-mqtt` -> `paho-mqtt>=2.0`.
- [ ] **Step 2:** `README.md` "First run": one line on MQTT mats appearing in the Device list by chip ID and the **Rename...** button.
- [ ] **Step 3:** `STATUS.md`: mark the design doc as built and link this plan; add `general.py`/`mats.json` and the `MqttSource` discovery mode to the file map; note that `config.TOTAL_ROWS/COLS` is overwritten at runtime.
- [ ] **Step 4:** `notes.md`: narrow the "Multi-mat MQTT support" bullet to what is still open (several mats connected at once, per-mat recording) and add the two flagged-but-not-built limitations plus the pending hardware check.
- [ ] **Step 5: Final run** - `python -m unittest discover -s tests -v` -> 67 tests, OK; `pio run` in `ESP32/` -> SUCCESS.

---

## Hardware check (manual, from the spec)

1. Flash two ESP32 boards with the new firmware. Each prints `Chip id: <12 hex digits>` on serial at boot, and `MQTT connected as <chip id>` once online.
2. Leave both running for a few minutes. Neither should log `MQTT not connected, will try again ...` repeatedly (that pattern is the client-ID kick the chip ID is there to prevent).
3. On the broker: `mosquitto_sub -v -t 'smartmat/+/meta'` shows one retained line per board, e.g. `smartmat/a1b2c3d4e5f6/meta a1b2c3d4e5f6,16,15`.
4. In the Pi app choose Source = MQTT. Both boards appear as separate Device entries. Rename one, restart the app, and confirm the name is still there.
5. Connect to each in turn and confirm the heatmap follows the mat you press on.
6. Power one board off: it stays in the list (known, not online) and the app shows "No data for Ns" when it is selected.
7. Old retained data: the pre-change topic `smartmat/frame` still holds a retained frame on the broker. Clear it once with `mosquitto_pub -t smartmat/frame -r -n`.
