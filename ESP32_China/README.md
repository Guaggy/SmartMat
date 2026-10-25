# SmartMat China mat bridge (ESP32-S3)

ESP32-S3 firmware that makes the Maxrays 20x20 USB mat wireless. The S3 is a USB host: it reads the mat
(CH340 serial, 921600 baud, 8-N-1, stream of `A5 5A` packets), decodes the 20x20 frames and publishes them
over MQTT to the SmartMat Raspberry Pi app. Engineering aid, not a medical device.

## MQTT contract

| Topic | Payload |
|---|---|
| `smartmat/<chip_id>/meta` (retained) | `<chip_id>,<rows>,<cols>,<value_max>,<model>,<width_mm>,<height_mm>`, e.g. `a1b2c3d4e5f6,20,20,255,MC266,343,358`. Model: letters, digits, `_`, `-`; sizes: sensing area in whole mm (`MAT_MODEL`, `MAT_WIDTH_MM`, `MAT_HEIGHT_MM` in `main.cpp`; MC266 size read from the datasheet drawing, about +/-5 %) |
| `smartmat/<chip_id>/frame` (NOT retained) | 400 comma-separated ints 0-255, row-major, at most 10 fps, mean of the frames decoded in each 100 ms window |
| `smartmat/<chip_id>/status` (retained) | `online` after every MQTT connect; `offline` is the last will, published by the broker when the board vanishes |

`chip_id` is the 12 hex digits of the eFuse MAC (same code as `ESP32_Resistive`). Values are raw mat units;
the Pi app scales them to its internal 0-1000 range once, using `value_max` from the meta message.

The mat streams at about 60 Hz. Instead of dropping frames, every frame decoded in a 100 ms window is added to
per-cell sums and the rounded mean is published when the window ends (nothing is published if no frame arrived).
Frames are not retained, so a subscriber never sees a stale frame as live; use the `status` topic for presence.

## Architecture (two cores)

- **Core 1, Arduino `loop()`**: drains the USB receive buffer, decodes, averages, and at the end of each 100 ms
  window puts the mean into a mailbox. No network calls and nothing that blocks.
- **Core 0, `network_task`** (priority 1, 8 KB stack, next to the Wi-Fi and lwIP tasks): Wi-Fi reconnect, MQTT
  connect/loop, meta and status, and frame publish. `PubSubClient`/`WiFiClient` are only touched here.
- **Mailbox** (`frame_mailbox.h`): 400 averaged bytes + sequence number + valid flag behind a spinlock
  (`portMUX`, held only for a 400 B copy). Latest wins: the loop never waits; the network task formats the CSV
  and publishes when MQTT is up and the sequence changed. Windows that arrive while MQTT is down are dropped and
  counted (`net dropped` in the UART stats).

Why: the mat streams 60 fps x 406 B = about **24.4 kB/s**, and the USB receive buffer is 8 KB, so it overflows
after 8192 / 24400 = about **0.34 s** without a read. With the broker or Wi-Fi down, `mqtt_client.connect()`
blocks for the TCP connect plus up to 2 s (socket timeout) every 5 s; in one loop that lost USB data and made
the decoder resync. On its own core it only delays publishing, never the USB read.

## Files

- `src/main.cpp` - USB host read and window mean (loop), Wi-Fi/MQTT network task, `SIMULATE_MAT` blob.
- `src/frame_mailbox.h` - header-only latest-wins mailbox, frame CSV and meta formatting, no Arduino includes.
- `src/frame_accumulator.h` - header-only per-window mean (uint16 sums + count, rounded), no Arduino includes.
- `src/maxrays_decoder.h` - header-only decoder, no Arduino includes. Same framing rules as
  `Raspberry Pi/sources/maxrays.py`: resync on `A5 5A`, packet end from the next header (404-436 bytes) or the
  declared length (406, or declared+4), lone trailing `A5` kept, garbage dropped, payload = bytes 4..403. The real mat
  sends 4 trailer bytes (`01 99 01 99`), so its packets are 408 bytes; the decoder waits for the next header.
- `esp32-s3-dump` env (`-DDUMP_RAW`): real firmware that also prints the first ~900 raw bytes from the mat as hex on the UART,
  for finding out why frames do not decode.
- `test/test_decoder/`, `test/test_accumulator/`, `test/test_mailbox/` - host Unity tests.
- `src/secrets.h.example` - copy to `src/secrets.h` (gitignored) and fill in Wi-Fi and MQTT values.

## Wiring (USB-A breakout on the S3 native USB port)

| USB-A breakout | ESP32-S3 DevKitC-1 |
|---|---|
| D+ | GPIO20 |
| D- | GPIO19 |
| GND | GND |
| VBUS | 5V pin |

The mat plugs into the breakout with its own USB-C to USB-A cable.

## Power

Datasheet figures for the mat: 5 V supply, 200 mA maximum, idle values only a few counts. The vendor says it is
not for weighing, so treat the values as relative pressure only.

- Worst case, ESP32-S3 (Wi-Fi transmitting, roughly 0.3 A) plus mat (0.2 A) is about **0.5 A**. Use a power bank
  or a 1 A phone charger. A laptop USB port (500 mA) is borderline: it may work, it may brown out when Wi-Fi
  transmits.
- Power the S3 from the **UART (COM) USB port** or a power bank, not from the mat. The native USB port is the
  host port here and is not assumed to source 5 V; the board's 5V pin is what feeds the breakout's VBUS.
- With both ports on a PC the UART port also gives the debug log (115200 baud).
- Measure the mat's idle and pressed current with the inline USB-C meter before relying on the 5V pin (it is
  fed from the UART port's USB 5 V, so a weak hub or a back-powered board will brown out).

## Shopping list

- USB-A **female** breakout board (the mat's own USB-C to USB-A cable plugs into it) plus jumper wires to the S3.
  Why not a bare USB-C breakout: a USB-C receptacle has no CC pull-up on its own, so a USB-C-to-USB-C mat cable
  would not be supplied with VBUS (a USB-A breakout has no such handshake).
- Power bank (or a 1 A+ USB charger) for the S3's UART port.
- Inline USB-C power meter (voltage and current) to read the mat's real draw.

## Build (this PC)

Plain `pio` on PATH is too old, and pioarduino 55.x must not run in the global PlatformIO core (it converts
it). Use a separate core dir and the PlatformIO python (the first build downloads about 20 minutes of
toolchains into the core dir; keep that folder, it is reused):

```
cd ESP32_China
copy src\secrets.h.example src\secrets.h          (then edit it)
set PLATFORMIO_CORE_DIR=%USERPROFILE%\.pio-core-s3
%USERPROFILE%\.platformio\penv\Scripts\python.exe -m platformio run
```

That builds both `esp32-s3-devkitc-1` (real, USB host) and `esp32-s3-simulate` (`-DSIMULATE_MAT`).
Single env: add `-e esp32-s3-devkitc-1`. Flash: add `-t upload -e <env>` (and `--upload-port COMx`) with the
S3 on its UART port. Monitor: `... -m platformio device monitor -b 115200`.

Decoder/mailbox/accumulator host tests (needs `g++` on PATH, e.g. a MinGW install; same core dir):

```
%USERPROFILE%\.platformio\penv\Scripts\python.exe -m platformio test -e native
```

## B3 hardware bring-up checklist

1. Multimeter: with the S3 powered from the UART port, VBUS on the breakout (from the 5V pin) is about 5 V and
   not shorted to GND.
2. Build and flash the `esp32-s3-simulate` env first (no mat attached): the Pi app lists a new mat (20x20) and
   shows the moving blob.
3. Check the status topic (`mosquitto_sub -v -t 'smartmat/+/status'`): `online` right after connect; unplug the
   S3's power and `offline` appears after the keep-alive timeout (about 15 s by default).
4. Inline meter on the mat: note idle and pressed current; confirm the 5V pin can supply it (supply: power
   bank or 1 A charger, see Power).
5. Flash the real `esp32-s3-devkitc-1` build with the mat attached: the mat appears. Compare frame by frame with
   the direct-USB view on the PC (same orientation, same range). The UART log prints bytes/s, frames/s,
   discarded bytes, invalid frames, dropped windows and the network task's free stack once a second; the mat
   should show up as `mat up` at about 60 frames/s while the Pi sees at most 10 frames/s.
6. Pull and replug the mat, and the Wi-Fi: it recovers without a reset, and `status` goes back to `online`.
   Stop the broker for 30 s: frames/s stays at about 60 and `discarded`/`invalid` do not grow, only
   `net dropped` does. If `net stack free` falls under about 1 KB, raise `network_stack_bytes`.

Status 2026-10-25: step 5 has been tried once with the real mat (frames did not decode at first; the raw dump led to the
4-trailer-byte decoder fix, see `notes.md`). Steps 1-4 and 6 and the result of step 5 after the fix are not recorded.

Not verified without hardware: CH340 at 921600 through the host driver, enumeration on GPIO19/20, replug
rebinding, and VBUS capability of the 5V pin.
