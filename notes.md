### Notes for future improvements and bugfixes

- Live site is currently just a placeholder at guaggy.github.io/SmartMat, deployed
  automatically from `Website/site/` on every push to `main` (see
  `.github/workflows/deploy-pages.yml`). Swap in the real site when there's something
  to show.
- Custom domain: decided to stick with the default `guaggy.github.io/SmartMat` for now
  rather than a free `is-a.dev` subdomain (needs a volunteer maintainer to merge a PR,
  out of our control) or buying a real domain. Revisit if/when it matters.
- `.gitignore` uses folder-agnostic patterns (`**/.pio/`, `**/CLAUDE.local.md`,
  `**/secrets.h`), so renaming or adding an `ESP32_*` folder keeps build artifacts and
  secrets ignored. Run `git check-ignore -v <path>` after adding a new secrets file.
- See each subfolder's own `notes.md` (`ESP32_Resistive/`, `ESP32_China/`, `Raspberry Pi/`,
  `Website/`) for component-specific TODOs.

### Thoughts
- Implement expression builder to make own expressions using the different variables. Current pressure, time of pressure, Hotspot area etc for each cell and make our own expressions that can be viewed on the heatmap in a new window etc. Can be used for educational purposes at schools etc
- make the main heatmap display the different maps available. Current, Calibrated, Pressure, average, time of pressure, time since release, time since movement etc or other parameters that can easily be used in later ecpressions and building. Also creates easy visializations
- Make a swith to toggle between advances and regular mode. Nice for school and showcase purposes
- Make it possible to save the raw/calibrated/pressure data in a csv or excell file for education or later analysis. Or is this already implemented by the record function.Maybe be able to save png of heatmaps and a snapshot of the current data to cvs or something. 
- Improove the UI looks and feel. Implement the colours and logo etc from our website: www.verdianmedical.com. Maybe add a link to it and a contact mail etc in the program.  
- implement method of weighing patient
- Add clickable link to both web UI links in app