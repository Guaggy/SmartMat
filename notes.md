### Notes for future improvements and bugfixes

- The public website is not part of this repo any more (no `Website/` folder, no Pages workflow).
- See each subfolder's own `notes.md` (`ESP32_Resistive/`, `ESP32_China/`, `Raspberry Pi/`)
  for component-specific TODOs, and `SETUP_AND_TEST.md` for installing and testing the devices.

### Backlog (2026-10-25 plan)

Built 2026-10-25, all untested on real hardware (no Tk, Pi or iPhone in the cloud session). Checks to do yourself are marked "verify".

- Desktop (Tk) CPU: the cost was the matplotlib redraw, not the analysis. The heatmap is blitted (`gui/blit.py`) and redrawn at `UI_MAX_FPS` (5); knobs `UI_*` in `config.example.py`; findings in `Raspberry Pi/docs/perf_tk.md`. Verify on a real desktop: stale pixels, colorbar after resize/theme/tab change, CPU against `UI_BLIT = False`. "Show numbers" still costs ~300 ms per redraw; tool-tab figures are still rebuilt on each refresh.
- Web heatmap: sharp bicubic WebGL (2D fallback), hotspot outline that follows the real cell shape, tweening, layer and view dropdowns, hotspot list, balance bars, indicative load, optional alert sound (off by default). Verify on the Pi kiosk Chromium (WebGL vs `--disable-gpu`) and on a tablet/phone.
- History: a snapshot every `HISTORY_INTERVAL_S` (300 s) and at each alert raise/clear (`HISTORY_ENABLED`), playback in the web dashboard (Live | History) and in the Tk app (Engineering > Connection > SmartMat server > History...), save as recording. The history rows only keep the hotspot centre and size, so the web draws an approximate ring. Verify the Tk window on a real desktop.
- Alerts: open alerts were already persisted (`store.save_alert`, restored at startup with the offline grace period).
- Forget mat (admin PIN, logged, clears the broker's retained `meta`/`status`); restore through the removed-mats list. The real-broker clearing is untested.
- CSV exports: `/api/export/audit.csv`, `/api/mats/<id>/history.csv`, `/api/mats/<id>/repositioning.csv`. Open reads like the rest of the read API.
- Repositioning, light: time since movement on the mat rows (`since_movement_s`, `since_reposition_s`), "movements in the last hour" in the panel, one switch to hide it (Settings > This screen). No chart.
- Phone: Expo Go works without remote push; in-app banner, vibration and local notification while the app is open; optional ntfy channel from the server (`NTFY_*`, off by default) for background alerts on an iPhone without an Apple account. Steps in `Phone App/README.md`. Verify on the iPhone over Tailscale.
- Demo mode: `python -m server --demo-scenario [--demo-speed X]` (off by default, demo mats do not push); `tools/seed_demo_history.py` fills a demo history. Check that the live demo mats show movement ages (a direct engine run does; the live server showed null once).
- Still open: hardware tests (test H on the Pi, the passport on a real board, the resistive board, two boards together; the S3 bridge with the real mat has run once, see `ESP32_China/notes.md`), Apple Developer account for native push/TestFlight.
- Regulated path: MQTT TLS, HTTPS through `tailscale serve`, a golden test (one recording through both the desktop pipeline and the server engine), per-mat occupancy and index-hold settings.
- Run the full test suite once on a machine with Tk: 16 test files need tkinter and did not run in the cloud session.

### Thoughts

Still open (everything else from this list is shipped - see "Shipped" in `Raspberry Pi/notes.md`):

- More heatmap layers for the Expression window: "time since movement" and a per-cell rolling average are not
  available as signals yet (the other layers are in the Data dropdown).
- Weighing: the load readout is indicative only (the vendor says the mat is for trends, not weighing). A
  known-weight scale-factor calibration is the next step, once real captures show how linear the mat is.
- Phone app (`Phone App/`, Expo): prototype is merged and the server side (device registration + Expo push) is on main, but a real push to a real phone is untested. Needs the one-time Expo/EAS setup in `Phone App/README.md`; open: Apple Developer account (iOS push/TestFlight), HTTPS or Tailscale for use outside the LAN, iOS time-sensitive notifications. 
- Web UI follows slide 3 of SmartMat-Produktpresentasjon.pdf now (rounded pills and cards, icon header with "Filter (n av m
  matter)", chevron rows, posture-coloured timeline with a risk strip and the red "Handle nå" link, soft map with Front on
  top, details folded away). Open: check it on a real tablet and phone with real mats; the "+" icon of the slide has no
  counterpart yet (adding mats happens on its own when they connect).
- Checks that are still open (replaces the old "thorough check of the program"): run the whole suite on the Pi
  (`pytest` from `Raspberry Pi/`), the Windows tests that need Tk (I step 5 in `SETUP_AND_TEST.md`), and the open hardware tests
  in the backlog above.
- Headless server: built and tested in simulation (alerts survive restarts, one failing mat does not stop the others,
  WAL database, systemd unit). Open: run it on the real Pi (`SETUP_AND_TEST.md` test H).
- Dashboard configuration page: done (gear button "Innstillinger": mats edit/remove/restore, alert holds, push on/off,
  risk sensitivity, stale limit, retention, advanced posture values, users; admin PIN to save, changes logged). Open:
  the risk-sensitivity defaults (relief time 120 min, medium from 80 %) are untuned placeholders, like the indices
  they drive. Then the web UI polish above.
- Two setups (decided 2026-10-19): **institution** = headless server + web UI + phone app (hospitals, the Pi can host a
  private SSID for the mats and use Ethernet to the hospital LAN; only the Pi's own Wi-Fi for schools/pilots) and
  **individual / education** = desktop app (serial, ESP32 bridge, playback, deep analysis over MQTT). The hospital setup is
  heading for regulated use, so traceability comes first. Plan, in order:
  1. DONE: analysis settings per mat in layers (factory < site < mat), append-only versions with who/when/why, rollback,
     the version stamped on every alert, "Analyse" page per mat in the dashboard (`server/settings.py`, `design/api-contract.md`).
  2. DONE in code, UNTESTED in the real window (no tkinter in the cloud; Windows test I step 5): desktop Engineering >
     Connection > SmartMat server > Compare / Preview on a recording / Send analysis settings / Get analysis settings, per mat
     (`client/analysis_sync.py` holds the logic and is tested against the live server; `gui/server_panel.py` is the thin window,
     tested through a stand-in for tkinter in `tests/test_server_panel_logic.py`). The preview replays a recording through the
     server's own engine and alert rules, in small steps on the main thread. Files = the existing Save/Load preset. The old
     desktop Web UI (`gui/web.py`) is removed.
  3. Mat "passport" on the ESP32: DONE in code, firmware glue UNTESTED on hardware (full PlatformIO build failed here on a
     certificate problem; `main.cpp` is only syntax-checked against stub headers). Two flash slots (factory: service key;
     custom: broker login), opaque blob `SMP1`+zlib(JSON) <= 16 KB with CRC-32, MQTT protocol in `ESP32_China/PASSPORT.md`.
     Rules are in `src/mat_passport.h` (28 host test cases) and mirrored in `matlink/passport_device.py`; client `matlink/passport_link.py`;
     server routes `GET /api/mats/<id>/passport`, `POST .../passport/adopt|write` and zero-touch adoption (`server/passports.py`,
     `tests/test_server_passport.py`, e2e part 13 over a real broker); `tools/passport_tool.py`, `tools/fake_passport_device.py`.
     Also done: buttons in the web UI (the mat's Analyse page), a "Passport on the mat" panel in the desktop (direct over MQTT,
     `client/passport_sync.py`; Tk itself untested like the server panel), and the same code in `ESP32_Resistive`
     (`passport_service.h` + `mat_passport.h`, identical copies, a test checks it). Still open: flashing and trying a real board.
  Open for the regulated path: MQTT login + TLS, HTTPS, a golden test that runs one recording through both the desktop
  pipeline and the server engine, occupancy/index-hold settings are still global (not per mat yet), exporting the audit log.
