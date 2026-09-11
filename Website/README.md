# SmartMat website widget

Self-contained HTML/JS/CSS heatmap widget for embedding in the smsolutions.no Elementor
site (no build step, no dependencies) - `smartmat-heatmap-widget.html`.

## Using it

Paste the whole file's contents into an Elementor "HTML" widget. It renders a 16x15 grid
(matching the ESP32/Raspberry Pi side) with 5 selectable scenarios:

- **No pressure / Bad distribution / Good distribution / Hand** - static placeholder
  scenarios, generated in-browser (or your own recorded data, see below).
- **Live** - fetches `LIVE_DATA_URL` (near the top of the `<script>` block) and renders
  whatever the Raspberry Pi app is currently sharing. Honestly reports "offline" instead of
  showing fake data if the URL is blank, unreachable, or nothing is being shared.

## Dropping in real recorded data

Once you have a real capture (e.g. a `.csv` recording from the Raspberry Pi app), paste it
into `RECORDED_FRAMES` (search for it) as a flat array of `ROWS*COLS` (240) numbers, 0..1,
row-major. Leave an entry `null` to keep that scenario's generated placeholder.

## Wiring up Live

`LIVE_DATA_URL` needs to point at the Raspberry Pi app's `/data` endpoint (`gui/web.py`),
reachable from the internet and served over HTTPS (a Cloudflare Tunnel is the easiest way -
see `Raspberry Pi/README.md`). It must be HTTPS - this site is HTTPS, and browsers block a
plain `http://` fetch from it as mixed content.

## Grid orientation

`ROWS`/`COLS` here (16x15) must match `TOTAL_ROWS`/`TOTAL_COLS` in `Raspberry Pi/config.py`
and `grid_rows`/`grid_cols` in `SmartMat_Resistive/src/main.cpp`. If any of these change,
update all three, and rescale the placeholder scenarios' hardcoded coordinates to match.
