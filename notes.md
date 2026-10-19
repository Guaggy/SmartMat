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
