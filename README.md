# SmartMat

Pressure-sensing smart mat project — resistive sensor firmware, a Raspberry Pi bridge, and a web-based visualization.

## Git / GitHub basics

Day-to-day loop after making changes in VS Code:

```
git status                  # see what changed
git add -A                  # stage everything (or `git add <file>` for specific files)
git commit -m "message"     # commit staged changes locally
git push                    # send commits to GitHub
```

Getting changes down (e.g. after editing on another machine or in the GitHub web UI):

```
git pull
```

Useful extras:

```
git log --oneline           # quick commit history
git diff                    # see uncommitted changes before staging
git branch                  # confirm which branch you're on
```

VS Code's Source Control panel (branch icon in the left sidebar) does the same thing without the terminal: `+` stages a file, the checkmark commits, and the sync (↕) button pulls then pushes in one click.

## Folder structure

- **`ESP32/`** — ESP32 firmware for the resistive pressure mat, built with PlatformIO (`platformio.ini`, `src/`, `include/`, `lib/`); see `ESP32/README.md`.
- **`Website/`** — Two independent pieces: `site/` is the placeholder landing page auto-deployed to GitHub Pages (guaggy.github.io/SmartMat) via `.github/workflows/deploy-pages.yml`, and `smartmat-heatmap-widget.html` is a separate browser-based heatmap widget pasted manually into the smsolutions.no Elementor site; see `Website/README.md`.
- **`Raspberry Pi/`** — Python desktop app (`main.py`) for viewing and recording the live pressure heatmap over Serial, MQTT, or simulated data; see `Raspberry Pi/README.md` for how it works and `requirements.txt` for dependencies.
