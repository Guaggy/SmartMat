# SmartMat

Pressure-sensing smart mat project — resistive sensor firmware, a Raspberry Pi bridge, and a web-based visualization.

**Live site (temporary domain):** https://guaggy.github.io/SmartMat/

## Folder structure

- **`ESP32_Resistive/`** — ESP32 firmware for the resistive pressure mat (16 x 15, multiplexed ADC), built with PlatformIO; see `ESP32_Resistive/README.md`.
- **`ESP32_China/`** — ESP32-S3 firmware that makes the Maxrays 20 x 20 USB mat wireless: it hosts the mat's USB-serial chip and publishes the frames over MQTT; see `ESP32_China/README.md` (it needs its own PlatformIO setup).
- **`Website/`** — Two independent pieces: `site/` is the placeholder landing page auto-deployed to GitHub Pages (https://guaggy.github.io/SmartMat/, temporary domain) via `.github/workflows/deploy-pages.yml`, and `smartmat-heatmap-widget.html` is a separate browser-based heatmap widget pasted manually into the smsolutions.no Elementor site; see `Website/README.md`.
- **`Raspberry Pi/`** — Python desktop app (`main.py`) for viewing and recording the live pressure heatmap over Serial (ESP32 text or the Maxrays USB mat), MQTT, or simulated data, with a Windows exe build; see `Raspberry Pi/README.md` for how it works and `requirements.txt` for dependencies.
