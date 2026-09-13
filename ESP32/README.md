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

- `serial_debug` - print connection/status messages to serial
- `smoothing_enabled` - exponential smoothing on each cell (`smoothing_strength`)
- `send_frame_serial` - also print each frame over serial, not just MQTT
- `read_linear_voltage` - use `analogReadMilliVolts()` (factory-calibrated) instead of raw `analogRead()`

The grid size and baud rate here must match `Raspberry Pi/config.py` on the Python side.

## How a scan works

1. `scan_grid()` calls `read_cell(row, col)` for each of the 240 cells.
2. `read_cell()` selects that cell (`select_cell()` addresses both muxes and waits for
   settling), discards one throwaway reading (residual charge from the last cell), then
   averages `samples_per_cell` readings.
3. Each cell is optionally smoothed against its previous value.
4. `build_frame_text()` flattens the grid into one comma-separated string, row-major -
   what the Python side and website widget both expect.
5. `send_frame()` publishes that string to MQTT topic `smartmat/frame` (retained), and to
   serial too if `send_frame_serial` is on.

## Worth verifying on real hardware

- `mux_settling_delay_us` (100us) may need tuning - the FSR sensor's resistance is highest
  at light touch, which is also where settling time matters most for accuracy.
- Real achieved frame rate may be below the nominal `frame_interval_ms` (100ms/10fps) -
  `print_fps()` (enabled via `serial_debug`) reports the actual rate.
