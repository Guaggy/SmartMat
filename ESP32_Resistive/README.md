# SmartMat resistive firmware

ESP32 firmware for the resistive pressure-sensor mat: scans a 16x15 grid through two
CD74HC4067 multiplexers, and streams pressure readings over MQTT (and optionally serial).

## Building / flashing

Built with PlatformIO (`platformio.ini` - board `esp32doit-devkit-v1`).

    pio run                    # build
    pio run --target upload    # flash
    pio device monitor         # view serial output (115200 baud)

Copy `src/secrets.h.example` to `src/secrets.h` (gitignored) and fill in your WiFi and MQTT
broker details first.

## Wiring

- ADC read pin: GPIO34 (ADC1 - stays reliable with WiFi active, unlike ADC2)
- Row mux: enable GPIO18, select pins GPIO19/21/22/23
- Col mux: enable GPIO27, select pins GPIO26/25/33/32
- Grid: 16 rows x 15 cols = 240 cells

## Config toggles (top of main.cpp)

- `serial_debug` - print connection/status messages to serial. Keep it `false` while
  `send_frame_serial` is on: debug lines share the port and the Pi counts them as malformed frames
  (the unconditional boot lines are still printed once at startup)
- `smoothing_enabled` - exponential smoothing on each cell (`smoothing_strength`)
- `send_frame_serial` - also print each frame over serial, not just MQTT (limited to
  `serial_frame_interval_ms` = 200 ms, i.e. 5 fps)

### Serial bandwidth

Worst case a frame is 240 values x 4 digits ("1000") + 239 commas + CRLF = 1201 bytes.
115200 baud, 8N1 = 11520 bytes/s. At 5 fps that is 6005 bytes/s (about 52 % of the link);
at the 10 fps scan rate it would be 12010 bytes/s, over the limit, and `Serial.println()`
would block the loop. So the serial copy runs at 5 fps while MQTT keeps `frame_interval_ms` (10 fps).
Typical frames are shorter (idle cells are small numbers).
- `read_linear_voltage` - use `analogReadMilliVolts()` (factory-calibrated) instead of raw `analogRead()`

Over MQTT the board reports its own grid size (see below), so nothing has to match by hand.
For Serial, the grid size and baud rate must still match `Raspberry Pi/config.py`.

## MQTT identity

Each board uses its chip ID (`ESP.getEfuseMac()` as 12 lowercase hex digits, printed on
serial at boot) as its MQTT client ID and topic prefix, so several mats can share a broker:

- `smartmat/<chip_id>/frame` - the frame (NOT retained; the Pi ignores retained frames)
- `smartmat/<chip_id>/meta` - `<chip_id>,<rows>,<cols>` (retained, sent on every MQTT connect);
  this is how the Pi app finds the mat and learns its grid size

## How a scan works

1. `scan_grid()` calls `read_cell(row, col)` for each of the 240 cells.
2. `read_cell()` selects that cell (`select_cell()` addresses both muxes and waits for
   settling), discards one throwaway reading (residual charge from the last cell), then
   averages `samples_per_cell` readings.
3. Each cell is optionally smoothed against its previous value.
4. `build_frame_text()` flattens the grid into one comma-separated string, row-major -
   what the Python side and website widget both expect.
5. `send_frame()` publishes that string to MQTT topic `smartmat/<chip_id>/frame` (not retained), and to
   serial too (at most 5 fps) if `send_frame_serial` is on.

## Test checklist

1. Flash (`pio run --target upload`), open serial at 115200.
2. Expect three boot lines (name, chip id, "Boot OK"), then ~5 lines/s, each 240 comma-separated numbers 0-1000.
3. Pi app, serial path: Source = Serial, Protocol = "ESP32 text (115200)"; the 16 x 15 grid should show pressure.
4. Pi app, MQTT path: with WiFi/broker set in `secrets.h`, the mat appears in the device list as 16 x 15
   and frames arrive (they are not retained, so nothing shows while the mat is off).

## Worth verifying on real hardware

- `mux_settling_delay_us` (100us) may need tuning - the FSR sensor's resistance is highest
  at light touch, which is also where settling time matters most for accuracy.
- Real achieved frame rate may be below the nominal `frame_interval_ms` (100ms/10fps) -
  `print_fps()` (enabled via `serial_debug`) reports the actual rate.
