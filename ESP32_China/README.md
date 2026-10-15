# SmartMat China mat bridge (ESP32-S3)

ESP32-S3 firmware that makes the Maxrays 20x20 USB mat wireless. The S3 is a USB host: it reads the mat
(CH340 serial, 921600 baud, 8-N-1, stream of `A5 5A` packets), decodes the 20x20 frames and publishes them
over MQTT to the SmartMat Raspberry Pi app. Engineering aid, not a medical device.

## MQTT contract

| Topic | Payload |
|---|---|
| `smartmat/<chip_id>/meta` (retained) | `<chip_id>,20,20,255` (rows, cols, value_max) |
| `smartmat/<chip_id>/frame` (NOT retained) | 400 comma-separated ints 0-255, row-major, at most 10 fps, mean of the frames decoded in each 100 ms window |
| `smartmat/<chip_id>/status` (retained) | `online` after every MQTT connect; `offline` is the last will, published by the broker when the board vanishes |

`chip_id` is the 12 hex digits of the eFuse MAC (same code as `ESP32_Resistive`). Values are raw mat units;
the Pi app scales them to its internal 0-1000 range once, using `value_max` from the meta message.

The mat streams at about 60 Hz. Instead of dropping frames, every frame decoded in a 100 ms window is added to
per-cell sums and the rounded mean is published when the window ends (nothing is published if no frame arrived).
Frames are not retained, so a subscriber never sees a stale frame as live; use the `status` topic for presence.

## Files

- `src/main.cpp` - Wi-Fi/MQTT keep-alive, USB host read, publish, `SIMULATE_MAT` blob.
- `src/frame_accumulator.h` - header-only per-window mean (uint16 sums + count, rounded), no Arduino includes.
- `src/maxrays_decoder.h` - header-only decoder, no Arduino includes. Same framing rules as
  `Raspberry Pi/sources/maxrays.py`: resync on `A5 5A`, packet end from the next header (404-436 bytes) or the
  declared length (406, or declared+4), lone trailing `A5` kept, garbage dropped, payload = bytes 4..403.
- `test/test_decoder/`, `test/test_accumulator/` - host Unity tests of the decoder and the accumulator.
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
it). Use a separate core dir and the PlatformIO python (first build downloads ~20 min of toolchains):

```
cd C:\Users\evenm\Projects\Hardware\SmartMat\ESP32_China
copy src\secrets.h.example src\secrets.h          (then edit it)
set PLATFORMIO_CORE_DIR=C:\Users\evenm\AppData\Local\Temp\claude\c--Users-evenm-Projects-Hardware-SmartMat\27902383-2feb-492a-a8cb-fa892a1b63bc\scratchpad\pio-core
C:\Users\evenm\.platformio\penv\Scripts\python.exe -m platformio run
```

That builds both `esp32-s3-devkitc-1` (real, USB host) and `esp32-s3-simulate` (`-DSIMULATE_MAT`).
Single env: add `-e esp32-s3-devkitc-1`. Flash: add `-t upload -e <env>` with the S3 on its UART port.
Pick a permanent `PLATFORMIO_CORE_DIR` (any folder) if the scratchpad is cleaned.

Decoder test (needs g++ on PATH, `C:\TDT4102-mingw64\bin` here; same core dir):

```
C:\Users\evenm\.platformio\penv\Scripts\python.exe -m platformio test -e native
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
   discarded bytes and invalid frames once a second; the mat should show up as `mat up` at about 60 frames/s
   while the Pi sees at most 10 frames/s.
6. Pull and replug the mat, and the Wi-Fi: it recovers without a reset, and `status` goes back to `online`.

Not verified without hardware: CH340 at 921600 through the host driver, enumeration on GPIO19/20, replug
rebinding, and VBUS capability of the 5V pin.
