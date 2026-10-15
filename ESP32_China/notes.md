# B1 toolchain spike (compile-only, 2026-10-15)

- Route A compiled: pioarduino platform 55.03.312-1 (Arduino-ESP32 3.3.12, IDF libs 5.5.5, xtensa gcc 14.2.0, esptool 5.4.0) + tanakamasayuki/EspUsbHost@2.10.0 (has its own CH34x VCP driver, Arduino Stream API) + knolleary/PubSubClient@2.8. Board esp32-s3-devkitc-1. Route B not needed.
- `pio run` tail: `RAM 17.7% (58120/327680)  Flash 29.8% (996736/3342336)  [SUCCESS] Took 1327 s` (first run, includes all downloads). WiFi + PubSubClient link in the same image.
- Build gotcha: pioarduino 55.x installs its own `pioarduino` core into `<core_dir>/penv` with uv. Running it from `~/.platformio/penv/Scripts/pio.exe` fails on Windows (exe locked) and leaves that penv half-uninstalled (repair: `penv\Scripts\python -m pip install platformio==6.2.0 urllib3 esp-pylib`). Safe options: a separate core dir (`PLATFORMIO_CORE_DIR=...` then `penv\Scripts\python -m platformio run`, how this was built), or `penv\Scripts\python -m platformio run` so pio.exe is not locked (this converts the global core to pioarduino). Older pioarduino 54.03.21 compiled the code but its esptool 5.0.0-dev breaks with click 8.5 at the .bin step.
- Unverified without hardware: CH34x at 921600 (library uses the Linux ch341 divisor math, which supports it; RX ring set to 8192 B since the 512 B default is ~5 ms at 921600), mat enumeration/full-speed on GPIO19/20, replug rebinding, and whether the breakout's VBUS (5V pin) can power the mat.
- B2 recommendation: Sonnet, normal effort. Arduino route means it can follow ESP32_Resistive/src/main.cpp almost 1:1; only new piece is `EspUsbHostCdcSerial` reads feeding the decoder.

# B2 firmware (2026-10-15)

- Built: `src/main.cpp` (USB host -> decoder -> MQTT, `SIMULATE_MAT` blob), `src/maxrays_decoder.h` (header-only, ported from `Raspberry Pi/sources/maxrays.py`, same rules incl. declared+4 and next-header confirmation), `test/test_decoder` (Unity, 7 cases), `README.md` (wiring, power, build, B3 checklist).
- Envs: `esp32-s3-devkitc-1` (RAM 18.7%, flash 29.9%), `esp32-s3-simulate`, `native` (host test, g++ from `C:\TDT4102-mingw64\bin`). `default_envs` = the two firmware envs, so `pio run` skips native.
- Verified: both firmware envs build; `pio test -e native` 7/7 pass; ESP32_Resistive still builds with the global PlatformIO after B1's repair.
- Choices: `mqtt_client.setSocketTimeout(2)` so a blocked connect cannot overflow the 8 KB USB ring buffer (the decoder would resync anyway); decoder reset on mat unplug; a retained frame stays on the broker while the mat is unplugged (no "offline" signal yet - add if the Pi app needs it).
- Python decoder behaviour kept on purpose: a false header followed by two real frames within 32 bytes can emit one garbage frame; only the capture will tell if that matters.
- Untested without hardware: everything USB (CH34x at 921600, enumeration, replug, VBUS), Wi-Fi/MQTT on the real board, publish rate under load.
