### Notes for future improvements and bugfixes

- `index.html` in this folder is the placeholder landing page deployed to GitHub Pages
  (via `.github/workflows/deploy-pages.yml`, triggered on push to `main` under
  `Website/**`). It's separate from `smartmat-heatmap-widget.html`, which is pasted
  manually into the Elementor site and is not part of the Pages deploy.
- Swap `index.html` for the real project site when there's something to show; until
  then it's just branding + an animated pressure-grid motif, no real data.