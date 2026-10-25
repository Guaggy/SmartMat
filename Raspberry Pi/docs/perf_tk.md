# Desktop app CPU use (Tk)

Profiled headless: `python tools/profile_frame_path.py` times the per-frame processing and a matplotlib Agg stand-in
for the heatmap redraw (this container has no Tk). Recording: `samples/seat_take1.json`, 20x20, about 8 frames/s.
Agg draws the same figure Tk would, so the ms numbers are a good guide; the Tk copy-to-screen cost is not included.

## Findings, biggest first

| # | Cost | Before | Why |
|---|---|---|---|
| 1 | Heatmap redraw (`DesktopApp._update_plot` -> `canvas.draw_idle`) | 42-47 ms per redraw, 10 per second (about 45 % of a core); 54-58 ms with hotspot overlays; ~320 ms with "Show numbers" | Every redraw lays out all tick labels and the colorbar again (nearly all of the 45 ms is text layout); the image itself is about 8 ms. On top of that `set_clim` and `set_cmap` ran every frame and each one re-lays-out the colorbar even when nothing changed. |
| 2 | Redraw rate and hidden redraws | 10 per second, also behind another tab or minimised | `DRAW_INTERVAL_S` was a constant 0.1 s; `draw_idle` on an unmapped canvas still draws. |
| 3 | Sensor health (`processing/sensor_health.py`) | 0.97 ms/frame, half the processing time | 400 Python `is_calibrated(row, col)` calls per frame, and the 50-frame window re-masked on every pass. |
| 4 | Hotspot region search (`processing/hotspots.py`) | 0.53 ms/frame | `connected_regions` took `min(unseen)` per region and hashed numpy scalars. |
| 5 | Poll loop and Tk traffic | every 50 ms, even with no source | Capture-button state, patient chip, connection text, readout StringVars (each write fires a trace that relayouts two labels) were written every poll or frame, changed or not. Tool tabs redrew at 2 Hz. |

Processing (items 3, 4) is small: about 2 ms per frame, 2 % of a core at 10 frames/s. Drawing was the cost.
Not a cost (checked): temporal state machine (0.14 ms), motion (0.11 ms), indices (0.1 ms, already 1 Hz), occupancy,
`process_frame` (0.05 ms) - all already numpy.

## Changes

* `gui/blit.py` (new): the 2D heatmap is blitted. Axes, ticks, labels and colorbar are a cached bitmap; each update
  restores it and draws only the image, overlays (contours, hotspot outlines and labels, ROI, markers, numbers) and the
  spines. A full draw happens when the colour scale, colormap, difference mode or data mode changes, on resize,
  on theme change, and when the tab becomes visible again. 3D surface always draws in full. `UI_BLIT = False` turns it off.
* `_update_plot` only touches `set_clim` / `set_cmap` / `set_extent` / `set_interpolation` when the value changed.
* `UI_MAX_FPS` (default 5, was a fixed 10) caps heatmap redraws; every frame is still processed.
* No redraw while the Live tab is hidden or the window is minimised (`_plot_visible`); it catches up on `<Map>`.
* `UI_IDLE_POLL_MS` (default 250): poll slowly while no source is connected.
* Status/readout variables and Tk widgets are written only when the text changed (`_show`, capture button, patient chip).
* `UI_TOOL_REFRESH_S` (default 1.0, was 0.5): refresh rate of open tool tabs; the time check now runs before the Tk visibility check.
* Sensor health: `calibrated_mask()` on the calibration (cached by the existing revision counter) and the unloaded-value
  mask computed once per frame. `connected_regions`: sorted scan, plain ints.
* All four knobs are read with `getattr` defaults, so an old `config.py` keeps working.

## Numbers (this container, Agg, Python 3.13, matplotlib 3.10)

| | Before | After |
|---|---|---|
| Heatmap update, default view (20x20, Linear x2) | 46 ms | 8.5 ms (5x) |
| Same, hotspot overlays on | 58 ms | 16 ms (3.6x) |
| Same, all overlays (contours, boundary, threshold, ROI, hotspots) | 112 ms | 30 ms |
| Same, "Show numbers" (400 text labels) | 320 ms | 300 ms (text drawing dominates; unchanged) |
| Redraws per second | 10 | 5 |
| Heatmap CPU in the default view (update ms x redraws/s) | about 460 ms/s | about 43 ms/s (about 10x less) |
| Processing per frame (all analysis steps) | 1.97 ms | 1.51 ms |
| of which sensor health / hotspots | 0.97 / 0.53 ms | 0.54 / 0.48 ms |
| Poll cycles with no source | 20 per second | 4 per second |

## Equivalence

Processing results are unchanged: `tests/test_perf_equivalence.py` keeps the previous `SensorHealth.update` and
`connected_regions` as references and compares every state array exactly (and hotspot events/tracks on the recording).
`tests/test_blit.py` checks on an Agg canvas that a blitted frame is pixel-identical to a full draw, including NaN
(transparent) cells, a changed colour scale, a resize and `invalidate()`. Pixel identity of the real `_draw_plot` code
(all overlays) against a plain full draw was also checked once with a scripted Agg harness.

## Left alone (ideas)

* "Show numbers" costs 300 ms per redraw whatever is done here (400 `Text` artists): lower `UI_MAX_FPS` while it is on.
* Tool tabs (diagnostics, temporal, analysis, ...) rebuild their figures on each refresh (`figure.clear()` + `tight_layout`);
  only the selected tab refreshes, and now at 1 Hz. Blitting them would be the next step.
* `Blitter.update` copies the whole figure to the Tk image; limiting it to the axes box would save a little more.
