### Notes for future improvements and bugfixes

Current state (2026-10-15): compiles and passes the host tests; **not yet run on hardware**. Wiring, power,
build commands and the bring-up checklist are in `README.md`; the step-by-step test is in `../SETUP_AND_TEST.md`.

## Toolchain

- pioarduino platform 55.03.312-1 (Arduino-ESP32 3.3.12, IDF libs 5.5.5) + `tanakamasayuki/EspUsbHost@2.10.0`
  (own CH34x VCP driver, Arduino Stream API) + `knolleary/PubSubClient@2.8`, board `esp32-s3-devkitc-1`.
- Envs: `esp32-s3-devkitc-1` (real), `esp32-s3-simulate` (`-DSIMULATE_MAT`, moving blob, no USB), `native`
  (host tests, needs g++ on PATH). `default_envs` are the two firmware envs, so `pio run` skips native.
- Build gotcha: pioarduino 55.x installs its own core into `<core_dir>/penv` with uv. Running it from
  `~/.platformio/penv/Scripts/pio.exe` fails on Windows (exe locked) and leaves that penv half-uninstalled
  (repair: `penv\Scripts\python -m pip install platformio==6.2.0 urllib3 esp-pylib`). Use a separate core dir
  (`PLATFORMIO_CORE_DIR=%USERPROFILE%\.pio-core-s3`) and `penv\Scripts\python -m platformio run`. pioarduino
  54.03.21 compiles but its esptool 5.0.0-dev breaks with click 8.5 at the .bin step.

## Design (why it looks like this)

- The mat streams about 60 fps x 406 B = 24.4 kB/s and the USB receive buffer is 8 KB (0.34 s). So `loop()`
  (core 1) only reads USB, decodes, averages the frames of each 100 ms window and fills a latest-wins mailbox
  (`frame_mailbox.h`); all Wi-Fi/MQTT work runs in `network_task` (core 0) and can block without losing data.
- Frames are the per-window mean (`frame_accumulator.h`), not dropped frames: less noise on an 8-bit sensor.
- MQTT: meta retained (`<id>,20,20,255,MC266,343,358`), frames not retained, `status` online/offline via last will.
- The decoder mirrors `Raspberry Pi/sources/maxrays.py` (same framing rules, confirmed by declared length).
  Known quirk kept on purpose: a false header followed by two real frames within 32 bytes can emit one
  garbage frame; the raw capture will show whether it matters.

## Open / untested without hardware

- CH34x at 921600 through the host driver, enumeration on GPIO19/20, replug rebinding, VBUS from the 5V pin.
- Two-core timing during a real broker outage; the 8 KB network stack (watch `net stack free`, raise
  `network_stack_bytes` if under ~1 KB).
- Trailer/checksum of the packets is still undocumented (needs the raw capture or the vendor).

## Future product work (not planned now)

- Wi-Fi provisioning (captive portal instead of `secrets.h`) and OTA updates.
