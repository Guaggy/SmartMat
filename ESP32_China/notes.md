### Notes for future improvements and bugfixes

Current state (2026-10-25): compiles and passes the host tests. It has run once on hardware with the real Maxrays mat (see "First hardware run" below); most of the bring-up checklist is still unchecked. Wiring, power,
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

## First hardware run (2026-10-25)

What the commits show (`38b97d0`, `5109231`): with the real mat attached, frames did not decode. A `DUMP_RAW` build
(`pio run -e esp32-s3-dump`) prints the first ~900 bytes as hex. The dump showed this mat sends `A5 5A 01 96`, a 406-byte
payload and then 4 trailer bytes `01 99 01 99`, so each packet is 408 bytes, not 406 + 2. The decoder (here and in
`sources/maxrays.py`) now waits for the next header instead of discarding a packet that is longer than declared; there is a
host test with 4 trailer bytes in small chunks. The fix is covered by unit tests; a hardware re-run after the fix (frames/s,
discarded/invalid flat, MQTT to the server) is not written down anywhere yet.

## Open / untested without hardware

- CH34x at 921600 through the host driver, enumeration on GPIO19/20, replug rebinding, VBUS from the 5V pin.
- Two-core timing during a real broker outage; the 8 KB network stack (watch `net stack free`, raise
  `network_stack_bytes` if under ~1 KB).
- Trailer/checksum of the packets is still undocumented (needs the vendor). The 4 trailer bytes are known now, but not what they mean.

## Future product work (not planned now)

- Wi-Fi provisioning (captive portal instead of `secrets.h`) and OTA updates.
