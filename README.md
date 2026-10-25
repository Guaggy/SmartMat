# SmartMat

Pressure-sensing smart mat system (Verdian Medical): mats, ESP32 bridges, a headless analysis server with a web dashboard,
a desktop app for analysis and calibration, and a phone app for alerts. An engineering and teaching tool, not a validated medical device.

How the system works (pipeline, setups, settings, passport): [system_info.md](system_info.md).
Setting up and testing devices: [SETUP_AND_TEST.md](SETUP_AND_TEST.md). Backlog and open items: [notes.md](notes.md).

## Folders

| Folder | What |
|---|---|
| `Raspberry Pi/` | All the Python: the **headless server** (`server/`, runs on a Pi or a PC), the **desktop app** (`main.py`, `gui/`, `client/`), and code they share. See `Raspberry Pi/README.md` for the layout. |
| `ESP32_China/` | ESP32-S3 firmware: USB host for the Maxrays 20x20 mat, publishes frames over MQTT, keeps the mat passport. PlatformIO. |
| `ESP32_Resistive/` | ESP32 firmware for the resistive 16x15 mat (multiplexed ADC). PlatformIO. |
| `Phone App/` | Expo (React Native) app for status and alerts. Expo SDK 57, so the App Store's Expo Go can run it. Without an Apple Developer account: test in Expo Go over Tailscale, background alerts through the free ntfy app (`Phone App/README.md`). |
| `Data/` | Reference material: mat datasheet, presentation, logo. |
| `test_reports/` | Dated reports from test passes on real machines. |

## Network and logins (home test setup)

Real credentials are not kept in this file. The home-test values (Wi-Fi SSID and password, the Pi's address, MQTT user and
password) live only in the gitignored files below. Copy each `*.example` file and fill it in.

| What | Where |
|---|---|
| WiFi SSID / password | `ESP32_Resistive/src/secrets.h` and `ESP32_China/src/secrets.h` (copy `secrets.h.example`) |
| Raspberry Pi (broker + server) | `<pi-address>`, MQTT port 1883, dashboard `http://<pi-address>:8000` |
| MQTT user / password | `Raspberry Pi/config.py` (`mqtt_username`, `mqtt_password`; copy `config.example.py`), the `secrets.h` files, and the desktop app under Engineering > Connection |

`broker_host` stays `localhost` in `config.py` on the Pi itself. If a password was ever committed, treat it as exposed and change it
on the Wi-Fi router and in Mosquitto.
