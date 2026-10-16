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

- Expression builder: let users write their own expressions over the per-cell signals (current pressure, time
  under pressure, hotspot area, ...) and view the result on the heatmap in its own window; useful for teaching.
  The weighted-term indices in `processing/indices.py` already cover most of the engine; what is missing is a
  free-form formula field (parse with a whitelisted `ast`, no `eval`) and a place to show the result.
- More heatmap layers for expressions: "time since movement" and a per-cell rolling average are not
  available as signals yet (the other layers are in the Data dropdown).
- Weighing: the load readout is indicative only (the vendor says the mat is for trends, not weighing). A
  known-weight scale-factor calibration is the next step, once real captures show how linear the mat is.
- Dark/light mode toggle
- Implement the new logos made recently into the program
- Make app for andorid and IOS, simple prototype for now. Same functionality and looks as the web UI but with notification capabiltiy 