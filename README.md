# SmartMat

Pressure-sensing smart mat project — resistive sensor firmware, a Raspberry Pi bridge, and a web-based visualization.

**Live site (temporary domain):** https://guaggy.github.io/SmartMat/

## Folder structure

- **`ESP32/`** — ESP32 firmware for the resistive pressure mat, built with PlatformIO (`platformio.ini`, `src/`, `include/`, `lib/`); see `ESP32/README.md`.
- **`Website/`** — Two independent pieces: `site/` is the placeholder landing page auto-deployed to GitHub Pages (https://guaggy.github.io/SmartMat/, temporary domain) via `.github/workflows/deploy-pages.yml`, and `smartmat-heatmap-widget.html` is a separate browser-based heatmap widget pasted manually into the smsolutions.no Elementor site; see `Website/README.md`.
- **`Raspberry Pi/`** — Python desktop app (`main.py`) for viewing and recording the live pressure heatmap over Serial, MQTT, or simulated data; see `Raspberry Pi/README.md` for how it works and `requirements.txt` for dependencies.
