### Notes for future improvements and bugfixes

- `site/index.html` is the placeholder landing page deployed to GitHub Pages (via
  `.github/workflows/deploy-pages.yml`, which publishes `Website/site` on push to
  `main` under `Website/**`). It's separate from `smartmat-heatmap-widget.html`, which
  is pasted manually into the Elementor site and is not part of the Pages deploy.
- Swap `site/index.html` for the real project site when there's something to show;
  until then it's just branding + an animated pressure-grid motif, no real data.
- If the real site ever needs more than one file (assets, extra pages), they all go
  under `site/` since that whole folder is what gets published as-is.
- `smartmat-heatmap-widget.html`'s "Live" mode is now fully broken, not just a stale
  tunnel URL: it points at the Pi app's old `/data` endpoint, which no longer exists
  after the Raspberry Pi web dashboard was reworked to be multi-mat aware (new API is
  `/api/mats` and `/api/mats/<mat_id>`, different shape). See `Raspberry Pi/notes.md`.
  Needs updating if the widget is reconnected to something real.