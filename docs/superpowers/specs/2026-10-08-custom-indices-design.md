# Custom indices: named signals, weighted combinations, near-threshold warnings

## Goal

Today every derived quantity (exposure, burden, time since relief, hotspot
duration, reposition count) lives in its own module with its own window, and
combining two of them means writing new processing code. There is also no
generic way to be told that a value is getting close to a limit.

This change adds:

- A registry of standard named signals, read from the trackers that already
  compute them. No new signal math.
- User-defined **indices**: weighted combinations of those signals, defined in
  a table, not in code.
- One warning rule (OK / near threshold / over threshold) that works on any
  index. This is the "warning when a risk/exposure value is near its
  threshold" item from `Raspberry Pi/notes.md`; it is built on the indices
  rather than as a separate system.

An index is a user-defined engineering quantity, not a validated score. The UI
says "index" and "threshold" throughout and never "risk". See the README's
"Not a medical device" section.

Out of scope: map indices as entries in the main window's Data dropdown
(follow-up once this has settled), sound or pop-up alerts, the web UI,
body-region awareness, and any pre-tuned "recommended" weights.

## Two layers

| Layer | What it is | Terms | Output |
|---|---|---|---|
| Map index | weighted combination of cell signals | cell signals | a grid (rows x cols) |
| Summary index | weighted combination of single numbers | mat signals; or a reducer of a map index or cell signal over a region | one number |

Exactly two layers. A summary index cannot be a term of another index. This
keeps every index explainable in one table and rules out cycles.

## Signal registry (`processing/signals.py`, new)

One entry per signal: `name`, `label`, `unit`, `level` (`"cell"` or `"mat"`),
`default_reference`, `windowed` (bool), and a getter. Getters take the trackers
(`temporal`, `hotspots`, `motion`), the current pressure grid, the contact
threshold, the current timestamp, and a window in minutes (`None` = session).

Cell signals (getter returns a grid, NaN where unknown):

| Name | Source | Unit | Windowed | Default reference |
|---|---|---|---|---|
| `pressure` | current calibrated pressure frame | kPa | no | `HOTSPOT_ACTIVATE_KPA` |
| `exposure` | `TemporalAnalysis.rolling(minutes)[0]` | kPa*min | yes | 300 |
| `burden` | `TemporalAnalysis.burden` | - | no | 300 |
| `since_relief` | `TemporalAnalysis.time_since_relief()` | s | no | 7200 |
| `loaded_time` | `TemporalAnalysis.loaded_s` | s | no | 7200 |
| `relief_percent` | `TemporalAnalysis.relief_percent(minutes)` | % | yes | 100 |

Mat signals (getter returns a float, or `None` when unknown):

| Name | Source | Unit | Windowed | Default reference |
|---|---|---|---|---|
| `repositions` | `MotionAnalyzer.repositions`, counted by record timestamp | count | yes | 2 |
| `movements` | `MotionAnalyzer.movements`, counted by record timestamp | count | yes | 10 |
| `active_hotspots` | `len(HotspotTracker.active)` | count | no | 1 |
| `longest_hotspot` | max `active_s` over active tracks, 0 if none | s | no | `HOTSPOT_PERSISTENCE_S` |
| `contact_cells` | `contact_mask(pressure, threshold).sum()` | cells | no | 60 |

Default references are starting values the user is expected to change, not
recommendations. Allowed windows are `None` (session) and
`TEMPORAL_WINDOWS_MIN` (1, 5, 15, 30, 60).

Known ceiling: `MotionAnalyzer` keeps the last 200 movements and 100
repositions, so a windowed count cannot exceed those. Fine for the supported
windows.

## Indices (`processing/indices.py`, new)

### Definition (plain dicts, so they go straight into preset JSON)

```json
{
  "name": "Sustained load",
  "layer": "map",
  "threshold": 1.0,
  "near_fraction": 0.8,
  "terms": [
    {"signal": "exposure", "window_min": 15, "reference": 300, "weight": 1.0, "inverted": false},
    {"signal": "since_relief", "window_min": null, "reference": 7200, "weight": 1.0, "inverted": false}
  ]
}
```

A summary term has two extra optional keys:

```json
{"source": "Sustained load", "reducer": "peak", "region": "mat", "reference": 1.0, "weight": 2.0, "inverted": false}
```

- `source` names a map index; alternatively `signal` names a cell signal (with
  `reducer` and `region`) or a mat signal (no reducer).
- `reducer`: `"peak"`, `"mean"`, or `"fraction_above"` (share of valid cells
  above `reducer_value`, 0-1).
- `region`: `"mat"` or `"roi"` (the ROI currently selected in the main window).

### Evaluation

- Normalised term value: `value / reference`. Inverted: `max(0, 1 - value / reference)`.
  Not capped at 1, so a signal far past its reference keeps raising the index.
- Index value: weighted average of its normalised terms,
  `sum(weight * n) / sum(weight)`. A value of 1.0 therefore means "every term
  is at its reference", which is why the default threshold is 1.0 and the
  default near margin is 0.8.
- Map index: per cell. A cell is NaN if any of its terms is NaN there.
- Reducers ignore NaN cells. A reducer over no valid cells is unknown.
- A summary index is unknown if any term is unknown. A `region: "roi"` term
  with no ROI selected is unknown; it does not fall back to the whole mat.
- With no pressure frame (calibration incomplete, no source, stale data) every
  index is unknown.

`evaluate_indices(definitions, context)` returns, per index name, the value
(grid or float or `None`) in definition order, evaluating map indices first so
summary terms can read them.

### Warning state

Per index: `"inactive"`, `"ok"`, `"near"`, `"over"`.

- The compared value is the index value for a summary index, and the peak
  finite cell for a map index.
- `over` when value >= `threshold`; `near` when value >= `near_fraction * threshold`;
  else `ok`.
- A change of state must hold for `INDEX_WARNING_HOLD_S` (new config constant,
  default 5.0) before it takes effect, in either direction, so a value sitting
  on the line does not flicker. Same pattern as `processing/occupancy.py`.
- `inactive` whenever the value is unknown or the patient indicator
  (`OccupancyDetector.occupied`) is not `True`. An empty mat or missing data
  never shows near/over. Leaving `inactive` takes the raw state immediately.
- Map indices also expose the boolean mask of cells at or above `threshold`
  for the heatmap outline.

`IndexMonitor` holds the definitions and the per-index state, and exposes
`update(context, timestamp, occupied)` returning the list of state changes
`(name, old_state, new_state)`, plus `values`, `states` and `reset()`.

## Settings and replay (`processing/settings.py`)

- New top-level key `"indices"` (list of definitions) in the settings dict
  produced by `capture_settings` and consumed by `apply_settings`,
  `validate_settings`, `save_preset`, `load_preset`. A preset without the key
  loads as "no change to indices" so existing preset files keep working.
- Validation: names unique and non-empty; `layer` is `map` or `summary`; at
  least one term; every `signal` exists and matches the layer; `source` names
  an existing map index; `reference` > 0 and finite; `weight` >= 0 with a
  positive sum; `window_min` only on windowed signals and only an allowed
  value; `reducer`/`region` valid; `threshold` > 0; 0 < `near_fraction` <= 1.
  An invalid set is rejected as a whole with a message naming the index.
- Recordings already store settings and `algorithm_settings_changed` events;
  indices ride along in the same payloads. On playback the existing replay
  choice applies: "Reproduce recording" uses the recorded definitions,
  "Re-analyze with current settings" uses the current ones.
- Built-in presets include two example indices:
  - **Sustained load** (map): `exposure` over 15 min + `since_relief`, equal weights.
  - **Mat overview** (summary): peak of Sustained load over the mat (weight 2)
    + `repositions` over 60 min, inverted (weight 1).

## GUI

### Engineering window (`gui/engineering_window.py`)

New "Indices" tab: a list of indices (add, duplicate, delete, rename), and for
the selected index its layer, threshold, near margin, and a term table with one
row per term (signal or source, window, reducer, region, reference, weight,
inverted) and add/remove row buttons. Choosing a signal pre-fills its default
reference. "Apply" validates and applies through the same
`apply_engineering_settings` path as the other tabs; preset save/load covers
indices automatically.

### Indices window (`gui/indices_window.py`, new; "Indices..." button in the main window)

- A one-line statement that these are user-defined engineering indices, not
  validated scores.
- A table of indices: name, layer, current value, state.
- A heatmap of the selected map index, colour scale 0 to max(threshold, peak),
  with a contour at the threshold.
- A trend line of the selected summary index against time, with the threshold
  and near lines drawn. History is kept per summary index, bounded by
  `HISTORY_MAX_FRAMES`.

### Main window (`gui/desktop.py`)

- One muted chip per index next to the patient indicator in the status bar:
  grey (ok/inactive), amber (near), red (over), text = index name.
- When a map index is over threshold, its over-threshold cells are outlined on
  the 2D heatmap (same contour mechanism as hotspots, distinct colour).
- State changes are added to the timeline, so they are saved in recordings:
  `index_near_threshold`, `index_over_threshold`, `index_cleared`, with the
  index name and value in the payload. Transitions to or from `inactive` are
  not logged.
- Indices are evaluated at most once per second, not per frame: the signals
  move slowly and the cost then does not grow with frame rate.
- `IndexMonitor.reset()` is called wherever the other trackers are reset
  (connect, disconnect, grid-size change, playback loop).

## Testing

`tests/test_indices.py`, `unittest`, matching the existing convention:

- Registry: every signal returns the declared shape; windowed counts respect
  the window.
- Evaluation: weighted average; inverted terms; values above reference are not
  capped; NaN cells propagate in maps and are ignored by reducers; each
  reducer; ROI term without an ROI is unknown; summary reading a map index.
- Warning state: ok/near/over boundaries; hold time in both directions;
  inactive when unoccupied or unknown; map index compares its peak cell.
- Settings: each validation rule rejects with a message; a preset without
  `indices` leaves them unchanged; save/load round trip.
- GUI smoke test (skipped without a display): with the built-in indices and a
  loaded simulated frame, a chip exists per index and forcing an index over
  threshold adds an `index_over_threshold` timeline event.
