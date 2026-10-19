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
| `Phone App/` | Expo (React Native) app for status and alerts. Expo SDK 54, so the App Store's Expo Go can run it. |
| `Data/` | Reference material: mat datasheet, presentation, logo. |
| `test_reports/` | Dated reports from test passes on real machines. |
