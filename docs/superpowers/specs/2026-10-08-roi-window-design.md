# ROI rework: cell-set ROI, its own window, polygon and paint selection, balance plot

## Goal

Today a region of interest (ROI) is a rectangle `(row0, row1, col0, col1)`
picked with two clicks on the main heatmap, and its numbers sit in the first
tab of the Analysis window. This change:

- Makes an ROI a set of cells of any shape.
- Moves selection and all ROI output into one new "ROI" window.
- Adds polygon and paint selection next to the two-corner box, on a frozen
  snapshot of the pressure map, with add/remove editing and an explicit Apply.
- Adds a mini grid of selected cells, a left/right and upper/lower balance
  plot, a centre of pressure within the ROI, and more ROI statistics.

Out of scope: several named ROIs at once, saving ROIs to a file, an adjustable
brush size, body-region presets, and remembering the ROI across restarts.

## ROI representation

An ROI is a boolean numpy array of shape `(config.TOTAL_ROWS, config.TOTAL_COLS)`,
`True` for selected cells, or `None` when there is no ROI. A mask with no
selected cell is never stored; it is treated as "no ROI". `DesktopApp.roi`
holds it. A rectangle is just a mask whose selected cells form a box.

Everything that reads an ROI changes from the four-number form to the mask.
There is no second representation kept alongside.

## `processing/roi.py` (new)

Pure functions, no GUI:

- `rectangle_mask(shape, first, second)` - cells in the box spanned by two
  `(row, col)` cells, in any order.
- `polygon_mask(shape, corners)` - cells whose centre is inside or on the
  outline of the polygon through the given `(row, col)` corners. Fewer than
  three corners gives an empty mask. Works for concave polygons.
- `stroke_cells(first, second)` - the cells on the straight line between two
  `(row, col)` cells inclusive, so a fast drag leaves no gaps.
- `mask_from_cells(shape, cells)` / `mask_to_cells(mask)` - to and from a
  sorted list of `[row, col]` pairs (the JSON form).
- `mask_from_legacy(shape, value)` - accepts the JSON form or the old
  `[row0, row1, col0, col1]` list and returns a mask; anything else, or cells
  outside the grid, raises `ValueError`.
- `roi_centre(mask)` - mean `(row, col)` of the selected cells.
- `roi_balance(grid, mask)` - see "Balance" below.

Cells outside the grid are ignored by the builders rather than raising, since
they come from pointer positions.

## Consumers

| Where | Change |
|---|---|
| `processing/analysis.py` `roi_statistics(grid, roi, ...)` | `roi` is a mask. `sensors` = selected cells; mean/peak/min/std/force/contact over selected cells only; `center_x`/`center_y` stay in mat cell coordinates. Adds `centre_offset_x`/`centre_offset_y` (CoP minus `roi_centre`, in cells; `None` without load). |
| `processing/temporal.py` `roi(bounds)`, `_roi_bounds`, `clear_roi()` | Take and store a mask (compared with `np.array_equal`). Fractions and exposure/burden statistics over selected cells. Time-since-relief tracking in `update()` uses the mask. |
| `gui/desktop.py` ROI history sample | Mean/peak/pressure mean over the mask. |
| `gui/desktop.py` heatmap | The rectangle patch is replaced by a contour around the selected cells (blue, same weight as today). A mask covering the whole mat draws the mat border. |
| `gui/temporal_window.py` | Passes the mask; text unchanged. |
| `gui/desktop.py` `add_annotation` | "Known hotspot" payload stores `"roi": mask_to_cells(mask)`. |
| `processing/validation.py` `compare_hotspot_roi(roi, tracks)` | `roi` is a mask: `expected` = its cells, `center` = `roi_centre`. |
| `processing/indices.py` `_reduce` | `region: "roi"` reduces `grid[mask]`. |
| Anything reading a recorded annotation's `"roi"` | Goes through `mask_from_legacy`, so recordings made before this change still load. |

## Balance (`roi_balance`)

Answers "is the load even within this region". The dividing point is the
region's own centre (`roi_centre`), not the mat's centre line.

- Weights are the finite, positive values of the grid inside the mask.
- A cell exactly on the dividing row or column counts half to each side
  (as `load_distribution` already does for the mat's middle row/column).
- Returns `left`, `right`, `upper`, `lower` and the four quadrant shares, each
  in percent of the ROI's load, plus `x = (right - left) / 100` and
  `y = (upper - lower) / 100`, both in -1..1. Right and up are positive.
- Returns `None` when the region carries no positive load.

"Left" and "right" mean left and right as drawn on screen. The app does not
know how the mat is oriented under the person, and the window says so.

This is deliberately the opposite sign convention to the existing whole-mat
`left_right_imbalance` ("positive = left"), because a plotted dot should move
the way the load moves. The whole-mat figure is not changed.

## ROI window (`gui/roi_window.py`, new; "ROI..." button in the main window)

### Selection

- **Canvas:** a frozen snapshot of the grid the main window is showing
  (calibrated pressure, or the baseline-subtracted signal when pressure is
  unavailable), with a faint cell grid. Selected cells are tinted. "New
  snapshot" re-freezes from the live frame. With no frame yet, the canvas is
  blank and selection still works.
- **Mode:** 2 corners / Polygon / Paint.
  - 2 corners: click a cell, click the opposite cell; a preview box follows
    the pointer in between.
  - Polygon: click cells to place corners; double-click, or click the first
    corner again, to close. Closing with fewer than three corners does nothing.
  - Paint: press and drag; every cell crossed is included, using
    `stroke_cells` between successive pointer positions. One-cell brush.
- **Add / Remove:** decides whether the finished action adds its cells to the
  working selection or removes them. Applies to all three modes.
- **Undo** (one action per step, 20 steps kept; a whole paint stroke is one
  action), **Clear**, **Invert** (both undoable).
- **Escape** cancels a half-drawn box or polygon.
- **Apply** makes the working selection the live ROI. Until then nothing live
  changes. Applying an empty selection clears the ROI. Applying resets the ROI
  history and the temporal time-since-relief tracking, as changing the ROI
  does today.
- Opening the window loads the current live ROI as the working selection.

### Output (for the live ROI, refreshed with the other tool windows)

- **Mini grid:** selected cells green, others grey, a cross at the ROI's
  centre of pressure.
- **Statistics:**
  - Pressure: cells, area, mean, peak, minimum, standard deviation, force,
    contact cells, contact area.
  - Position: centre of pressure, and its offset from the region's centre.
  - Over time: time since the region was last relieved; share of cells loaded
    and relieved; mean and peak exposure; mean and peak burden.
  - Hotspots: number of active hotspots sharing at least one cell with the ROI.
- **Balance plot:** one square plot, both axes -1..1 with zero lines; one dot
  at `(x, y)`; a trail of the last 60 samples; the four quadrant percentages
  in the four corners. With no load the dot and trail are omitted and the plot
  says "No load in this region".
- **History line:** ROI mean and peak against time since Apply (moved from the
  Analysis window).

## Removed

- The Analysis window's "ROI" tab and its "Select ROI" / "Clear ROI" buttons.
  It keeps "Distribution" and "Load and symmetry".
- Two-click ROI selection on the main heatmap (`selecting_roi`, `roi_corner`,
  `_begin_roi_selection`). A click there selects a cell for the history view
  only.

## Other behaviour

- A grid-size change clears the ROI (already the case) and closes nothing: an
  open ROI window resets its working selection and snapshot to the new size.
- `README.md`, the in-app Help text and `STATUS.md` are updated to describe
  the new window.

## Testing

`tests/test_roi.py`, `unittest`:

- `rectangle_mask` in any corner order; `polygon_mask` for a triangle, a
  concave shape, and fewer than three corners; `stroke_cells` for a diagonal
  fast drag and a single cell; builders ignoring out-of-range cells.
- `mask_to_cells` / `mask_from_cells` round trip; `mask_from_legacy` for the
  old four-number list, the new form, and invalid input.
- `roi_statistics` and `TemporalAnalysis.roi` over an L-shaped region give the
  values of exactly those cells; time-since-relief tracking with a mask.
- `roi_balance`: all load on one side gives +/-1; an even region gives 0; a
  cell on the dividing line splits; no load gives `None`; a region off to one
  side of the mat can still read balanced.
- `compare_hotspot_roi` and the indices `"roi"` reducer with a mask.
- GUI (skipped without a display): drive each mode through its handlers with
  Add and Remove, Undo, Clear, Invert; Apply sets `app.roi`; empty Apply
  clears it; a "Known hotspot" annotation stores the cell list.
- Existing tests that pass a four-number ROI (`test_phase3`, `test_phase4`,
  `test_indices`) are updated to masks.
