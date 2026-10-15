# SmartMat China mat bridge (ESP32-S3)

ESP32-S3 firmware that makes the Maxrays 20x20 USB mat wireless. The S3 is a USB host: it reads the mat
(CH340 serial, 921600 baud, 8-N-1, stream of `A5 5A` packets), decodes the 20x20 frames and publishes them
over MQTT to the SmartMat Raspberry Pi app. Engineering aid, not a medical device.

## MQTT contract

| Topic | Payload |
|---|---|
| `smartmat/<chip_id>/meta` (retained) | `<chip_id>,20,20,255` (rows, cols, value_max) |
| `smartmat/<chip_id>/frame` (retained) | 400 comma-separated ints 0-255, row-major, at most 10 fps, latest frame only |

`chip_id` is the 12 hex digits of the eFuse MAC (same code as `ESP32_Resistive`). Values are raw mat units;
the Pi app scales them to its internal 0-1000 range once, using `value_max` from the meta message.

## Files

- `src/main.cpp` - Wi-Fi/MQTT keep-alive, USB host read, publish, `SIMULATE_MAT` blob.
- `src/maxrays_decoder.h` - header-only decoder, no Arduino includes. Same framing rules as
  `Raspberry Pi/sources/maxrays.py`: resync on `A5 5A`, packet end from the next header (404-436 bytes) or the
  declared length (406, or declared+4), lone trailing `A5` kept, garbage dropped, payload = bytes 4..403.
- `test/test_decoder/` - host Unity test of the decoder.
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

- Power the S3 from the **UART (COM) USB port** or a power bank, not from the mat. The native USB port is the
  host port here and is not assumed to source 5 V; the board's 5V pin is what feeds the breakout's VBUS.
- With both ports on a PC the UART port also gives the debug log (115200 baud).
- Measure the mat's idle and pressed current with the inline USB meter before relying on the 5V pin (it is
  fed from the UART port's USB 5 V, so a weak hub or a back-powered board will brown out).

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
2. Flash the `esp32-s3-simulate` build: the Pi app lists a new mat (20x20) and shows the moving blob.
3. Inline meter on the mat: note idle and pressed current; confirm the 5V pin can supply it.
4. Flash the real build: the mat appears. Compare frame by frame with the direct-USB view on the PC (same
   orientation, same range). The UART log prints bytes/s, frames/s, discarded bytes and invalid frames
   once a second; the mat should show up as `mat up`.
5. Pull and replug the mat, and the Wi-Fi: it recovers without a reset.

Not verified without hardware: CH340 at 921600 through the host driver, enumeration on GPIO19/20, replug
rebinding, and VBUS capability of the 5V pin.
