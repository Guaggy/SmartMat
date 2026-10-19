### Notes for future improvements and bugfixes

- Live site is currently just a placeholder at guaggy.github.io/SmartMat, deployed
  automatically from `Website/site/` on every push to `main` under `Website/**` (see
  `.github/workflows/deploy-pages.yml`). Swap in the real site when there's something
  to show.
- Custom domain: decided to stick with the default `guaggy.github.io/SmartMat` for now
  rather than a free `is-a.dev` subdomain (needs a volunteer maintainer to merge a PR,
  out of our control) or buying a real domain. Revisit if/when it matters.
- See each subfolder's own `notes.md` (`ESP32_Resistive/`, `ESP32_China/`, `Raspberry Pi/`,
  `Website/`) for component-specific TODOs, and `SETUP_AND_TEST.md` for installing and testing the devices.

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
- Do a thorough check of the program
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
     (`analysis_sync.py` holds the logic and is tested against the live server; `gui/server_panel.py` is the thin window,
     tested through a stand-in for tkinter in `tests/test_server_panel_logic.py`). The preview replays a recording through the
     server's own engine and alert rules, in small steps on the main thread. Files = the existing Save/Load preset. The old
     desktop Web UI is off by default and says so when the port is taken (it crashed the desktop at start when the server
     ran on the same PC); removing `gui/web.py` and its selftest use is still open (needs the desktop tests run on Windows).
  3. Mat "passport" on the ESP32 (NVS: serial, calibration profile, size, model, a factory copy and a custom copy, versions
     and checksums; firmware does not listen to commands or store anything yet; zero-touch: the server adopts the passport
     of a new mat when it has nothing; only device-bound data travels with the mat, names/rooms/thresholds/users stay at the site).
  Open for the regulated path: MQTT login + TLS, HTTPS, a golden test that runs one recording through both the desktop
  pipeline and the server engine, occupancy/index-hold settings are still global (not per mat yet), exporting the audit log.
