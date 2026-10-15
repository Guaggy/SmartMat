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
- Choices: `mqtt_client.setSocketTimeout(2)` (this alone did not stop USB overflow, see N1); decoder reset on mat unplug; a retained frame stays on the broker while the mat is unplugged (no "offline" signal yet - add if the Pi app needs it).
- Python decoder behaviour kept on purpose: a false header followed by two real frames within 32 bytes can emit one garbage frame; only the capture will tell if that matters.
- Untested without hardware: everything USB (CH34x at 921600, enumeration, replug, VBUS), Wi-Fi/MQTT on the real board, publish rate under load.

# F1-F3 follow-up (2026-10-15)

- F1: `src/frame_accumulator.h` averages all frames decoded in each 100 ms publish window (uint16 sums, rounded mean, publish only if count > 0; at most 257 frames per window so the sums cannot overflow). Replaces "keep only the newest frame". Native tests in `test/test_accumulator` (mean, rounding, count reset, saturation at 255).
- F2: MQTT last will `smartmat/<chip_id>/status` = `offline` (retained), `online` (retained) published after each connect. Frames are now NOT retained (the Pi app ignores retained frames); meta stays retained. Resolves the B2 "no offline signal" gap.
- F3: power numbers, shopping list and the B3 checklist are in `README.md`.
- Future product work (not planned now): Wi-Fi provisioning (captive portal instead of `secrets.h`) and OTA updates.

# N1 network task + preset in meta (2026-10-15)

- Fixed (was a review finding): Wi-Fi/MQTT connect blocked the single loop for TCP connect + up to 2 s every 5 s while the broker or Wi-Fi was down; at ~24.4 kB/s the 8 KB USB buffer lasts ~0.34 s, so frames were lost and the decoder resynced.
- Now: all networking in `network_task` (core 0, priority 1, 8 KB stack, 10 ms poll); `loop()` (core 1) only reads USB, decodes, averages and fills a latest-wins mailbox (`src/frame_mailbox.h`, `portMUX` spinlock) once per 100 ms window. Windows taken while MQTT is down count as `net dropped` in the 1 Hz stats, which also print the network task's free stack. Serial TX buffer 1 KB so debug prints never block the loop.
- Meta is now `<chip_id>,<rows>,<cols>,<value_max>,<model>,<width_mm>,<height_mm>` (`MC266,343,358`; size read from the datasheet drawing, +/-5 %, verify with a ruler). Bad model/size constants halt at boot with a UART message.
- Native tests: `test/test_mailbox` (mailbox sequence, CSV, meta). Untested without hardware: the two-core timing under a real broker outage, the 8 KB stack figure (check `net stack free`).
