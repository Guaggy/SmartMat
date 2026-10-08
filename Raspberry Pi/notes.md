### Notes for future improvements and bugfixes

- Public website "Live" currently relies on a free Cloudflare quick tunnel (URL changes every restart) - and its target endpoint no longer exists at all (see "Known limitations" below). Switch to a named tunnel or a proper always-on relay if/when the widget is reconnected to something real.
- Website widget's RECORDED_FRAMES are still all null (placeholders only) - drop in real captured recordings once available
- Raspberry Pi deployment at home: needs a headless service (nobody there to click through the GUI), systemd auto-start/restart for the tunnel and the app, and MQTT instead of Serial (no one to plug in a USB cable)

## Known bugs

- "Ignore signal <=" threshold is skipped when Data = Calibrated pressure (`gui/desktop.py` ~line 1473, `elif key != "pressure":`) - should apply there too.
- `Raspberry Pi/user_guide.md` was deleted from the working tree but never committed as a removal, and nothing currently references it - decide: restore it, rewrite it, or leave it gone.

## Known limitations (shipped deliberately scoped down, not bugs)

- Multi-mat: a recording made on a mat that is not the `config.py` default size cannot be played back - playback uses the default size and `load_session` rejects the mismatch. Fix when a second mat size actually exists (take the size from the recording's own `grid_shape`).
- Multi-mat: tare and pressure calibration reset when the grid size changes, but two mats of the same size share whatever is in memory when you switch between them - re-tare / load the right calibration after switching. Per-mat calibration files would be the real fix.
- Multi-mat: the two-board hardware check (flash two boards, confirm both stay connected and both show up in the device list) has not been run yet - steps at the end of `docs/superpowers/plans/2026-10-08-multi-mat-mqtt.md`. Also clear the old retained `smartmat/frame` topic on the broker once.
- Multi-mat: the app needs paho-mqtt 2.x. This PC has 1.6.1 because esphome pins it, so MQTT does not work here until the app runs in its own venv - not a concern on a dedicated Pi.
- Indices: every default reference value is an untuned placeholder - set real ones before reading anything into an index. Map indices aren't in the main Data dropdown and there are no sound/pop-up alerts (only the status-bar chip).
- Patient-detected indicator only means "enough cells loaded for long enough" - calibration weights also read as a patient. Not yet: timeline events, recording it.
- ROI: several named ROIs at once, saving ROIs to a file, an adjustable brush size, and remembering the ROI across restarts are all not built.
- Web dashboard: only the mat currently open in the desktop app shows a live heatmap/hotspots/patient-state/indices - other known mats are listed but not live (see "Still to build" for the planned fix). `http://<hostname>.local:8000` relies on Avahi/mDNS, which Raspberry Pi OS runs by default, but this has not been confirmed on the deployed Pi yet (the IP is shown beside it as a fallback).
- The public website widget's "Live" mode is fully broken, not just a stale tunnel URL: `Website/smartmat-heatmap-widget.html` still points at the old `/data` address, which no longer exists after the web-dashboard rework (the new API is `/api/mats` and `/api/mats/<mat_id>`, shaped differently). See `Website/notes.md`.
- ESP32: `mux_settling_delay_us` and the ADC calibration assumptions haven't been verified against real hardware yet (only tested in simulation so far).

## Still to build

- Web dashboard: a light background listener per known mat, so mats the desktop app doesn't have open also show a live raw heatmap. Needs a frame-reading path independent of the app's current grid size, plus one extra MQTT connection per mat. Hotspots/patient-state/indices stay limited to the connected mat until per-mat tare and calibration exist.
- Multi-mat: connect to and record multiple mats at once (today you switch between them one at a time) - advanced per-cell stuff doesn't need to run for every mat automatically (save compute).
- Area-per-cell setting (for N/kg calculations) and an option to estimate patient/body-part weight from a marked ROI.
- Body-part recognition (deliberately deferred for now - mat position -> anatomical region, posture-dependent).

## Shipped (see docs/superpowers/ for the design/plan trail)

- Multi-mat MQTT support: chip-ID topics, grid-shape handshake, device list, nicknames (`mats.json`). `docs/superpowers/specs/2026-10-07-multi-mat-mqtt-design.md`, `docs/superpowers/plans/2026-10-08-multi-mat-mqtt.md`.
- Custom indices: weighted combinations of signals (map + summary layers), near/over-threshold warnings with a hold time. `docs/superpowers/specs/2026-10-08-custom-indices-design.md`, `docs/superpowers/plans/2026-10-08-custom-indices.md`.
- Patient-detected indicator (`processing/occupancy.py`, status bar).
- ROI rework: cell-set based selection (box/polygon/paint) on a frozen snapshot, its own window. `docs/superpowers/specs/2026-10-08-roi-window-design.md`, `docs/superpowers/plans/2026-10-08-roi-window.md`.
- Web dashboard: multi-mat aware, per-mat pressure/hotspots/occupancy/indices, hostname-based URL, "Share live data" removed entirely. `docs/superpowers/specs/2026-10-08-web-dashboard-design.md`, `docs/superpowers/plans/2026-10-08-web-dashboard.md`.
- Bounded-polish + calibration-rework batch: startup toggle defaults, plot-options cleanup (Linear/scale=2 default, Nearest removed, reference buttons split out), diagnostics health rollup narrowed to Saturated-Invalid, Temporal cell-click-to-history removed, Movement before/after as its own window (`gui/reposition_window.py`), contact threshold removed from the main menu, per-window explanatory blurbs, Engineering reframed as the advanced tab, the calibration raw-grid-getter fix, tare also setting pressure-calibration offsets, and the individual/uniform calibration profile split (`gui/calibration_window.py`, `processing/calibration.py`'s `UniformCalibration`).
