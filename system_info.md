# SmartMat: how the system works

Pressure-sensing seat/bed mat that warns about pressure-injury risk (Verdian Medical).

## Pipeline

```
mat (20x20 sensors)
  -> ESP32 bridge  (ESP32_China: USB host for the Maxrays mat; ESP32_Resistive: mux + ADC)
  -> MQTT broker   (Mosquitto on the Pi, topics smartmat/<chip_id>/frame|meta|status|passport...)
  -> server        (Raspberry Pi/server: one MatEngine per mat -> posture, hotspots, movement, risk indices)
  -> AlertManager  (high-risk / offline alerts, persisted in sqlite, grace period after restart)
  -> web dashboard + REST API  (nurses/admins, PIN login)  and  push to the phone app (Expo)
```

- A frame is 400 raw values, about 10 per second. The server converts them to kPa with the mat's calibration profile.
- Everything that changes behaviour is logged with who, when and why.

## Setups

| | Institution (hospital, care home) | Individual / education |
|---|---|---|
| Main part | Headless server on a Pi + web dashboard + phone app | Desktop app (`main.py`) |
| Mat connection | ESP32 over Wi-Fi to MQTT | Serial/USB directly, or ESP32 over MQTT |
| Network | Private SSID/Ethernet, or the Pi's own access point | None needed for serial; same Wi-Fi as the broker for MQTT |
| Used for | Live monitoring, alerts, history | Playback of recordings, deep analysis, calibration, teaching |

The two can be combined: the desktop talks to the same broker and server as everything else.

## Settings (per mat, in layers)

- Order: factory values < site < mat. A mat only overrides what it sets itself.
- Every change is a new version (append-only) with user, time and reason. Rollback creates a new version. Each alert carries the settings stamp that raised it (for example `s3.m2`).
- Admin PIN is needed for changes; nurses can acknowledge alerts.
- Desktop and server can compare and exchange the analysis settings of a mat (Engineering > Connection > SmartMat server). The desktop can also preview a recording through the server's own engine before anything is sent.

## Mat passport (calibration travels with the mat)

- Each ESP32 keeps two flash slots, `factory` (needs a service key) and `custom`. A slot is a blob of at most 16 KB with a CRC; the firmware never parses it.
- Contents: calibration profile, size, model, optionally the mat's own analysis settings. Names, rooms, thresholds and users stay at the site.
- Uses: back up a calibration, ship a calibrated mat, and zero-touch setup (a new mat at a server with no profile gets its passport adopted automatically).
- Who can use it: web (mat's Analyse page), desktop (Passport on the mat panel, direct over MQTT), `tools/passport_tool.py`, REST `/api/mats/<id>/passport...`.
- Protocol: `ESP32_China/PASSPORT.md`.

## Where things are

| Folder | What |
|---|---|
| `Raspberry Pi/server/` | server, REST API, dashboard (`static/`), alerts, layered settings, passport service |
| `Raspberry Pi/gui/`, `main.py` | desktop app |
| `Raspberry Pi/processing/`, `sources/` | analysis and calibration; serial/MQTT/recording sources |
| `Raspberry Pi/tools/` | `e2e_check.py`, `publish_demo_mat.py`, `passport_tool.py`, `fake_passport_device.py` |
| `ESP32_China/`, `ESP32_Resistive/` | firmware (PlatformIO) |
| `Phone App/` | phone app (alerts) |
| `SETUP_AND_TEST.md`, `notes.md` | setup, test plans, open work |

## Status

- Server, layered settings, desktop sync and passport are done and tested without hardware (unit tests plus an end-to-end run over a real broker).
- Hardware: the ESP32-S3 bridge has run once with the real Maxrays mat (raw dump taken; the decoder was fixed for the 4 trailer bytes
  this mat sends). Not yet checked on hardware: the passport code in the firmware, the resistive board, two boards together, the
  server on the real Pi, push to a real phone.
- Open for regulated use: MQTT login with TLS, HTTPS, a test that runs one recording through both the desktop and the server engine, exporting the audit log, per-mat occupancy settings. The full list is in `notes.md`.
