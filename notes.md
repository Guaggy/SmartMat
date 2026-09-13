### Notes for future improvements and bugfixes

- Live site is currently just a placeholder at guaggy.github.io/SmartMat, deployed
  automatically from `Website/site/` on every push to `main` (see
  `.github/workflows/deploy-pages.yml`). Swap in the real site when there's something
  to show.
- Custom domain: decided to stick with the default `guaggy.github.io/SmartMat` for now
  rather than a free `is-a.dev` subdomain (needs a volunteer maintainer to merge a PR,
  out of our control) or buying a real domain. Revisit if/when it matters.
- `.gitignore` entries are path-specific (`ESP32/.pio/`, `ESP32/CLAUDE.local.md`,
  `ESP32/src/secrets.h`) — after renaming a top-level folder, double check these still
  match, otherwise build artifacts/secrets can silently start getting tracked again.
- See each subfolder's own `notes.md` (`ESP32/`, `Raspberry Pi/`, `Website/`) for
  component-specific TODOs.
