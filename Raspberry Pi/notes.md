### Notes for future improvements and bugfixes

- Web UI's `/` page is a temporary live-heatmap view just for testing - replace with something real or drop it once no longer needed
- Public website "Live" currently relies on a free Cloudflare quick tunnel (URL changes every restart) - switch to a named tunnel or a proper always-on relay before relying on this day to day
- /data's CORS header is wide open (Access-Control-Allow-Origin: *) - fine for testing, tighten to the real site's origin before going live
- Website widget's RECORDED_FRAMES are still all null (placeholders only) - drop in real captured recordings once available
- Raspberry Pi deployment at home: needs a headless service (nobody there to click through the GUI), systemd auto-start/restart for the tunnel and the app, and MQTT instead of Serial (no one to plug in a USB cable)
- ESP32: mux_settling_delay_us and the ADC calibration assumptions haven't been verified against real hardware yet (only tested in simulation so far)
