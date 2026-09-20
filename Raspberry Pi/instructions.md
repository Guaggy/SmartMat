# SMARTMAT Codex Instructions

## Purpose

This repository contains the SMARTMAT pressure-mat software.

Your task is to **extend the existing program**, not replace or rewrite it from scratch.

The current Raspberry Pi dashboard already works reasonably well and its existing coding style, UI style, folder structure, naming conventions, and program flow should be treated as the default reference.

Before changing anything:

1. Inspect the existing code.
2. Understand how data flows through the current program.
3. Identify the smallest reasonable change that adds the requested functionality.
4. Reuse existing patterns and components where practical.
5. Avoid large architectural rewrites unless they are clearly necessary.

---

# Scope

## Primary working area

Make changes inside the:

`Raspberry Pi/`

folder unless there is a strong technical reason to change something elsewhere.

The Raspberry Pi application is responsible for:

- GUI/dashboard
- Serial connection
- MQTT connection
- Playback
- Recording
- Calibration tools
- Pressure visualization
- Analytics
- Sensor diagnostics
- Pressure-time analysis
- Higher-level algorithms

## ESP32 folder

Do **not** modify the ESP32 code unless a requested feature genuinely requires a firmware-side change.

If an ESP32 change appears necessary:

- First determine whether the feature can reasonably be implemented on the Raspberry Pi instead.
- Keep firmware changes minimal.
- Do not restructure the ESP32 project unnecessarily.
- Preserve the existing ESP32 coding style.
- Clearly separate required firmware changes from optional improvements.

The current intended ESP32 responsibilities are approximately:

`sample sensors -> remove obvious spikes -> average -> simple low-pass filtering -> transmit data`

The Raspberry Pi should remain responsible for most advanced analysis.

---

# General Development Philosophy

Prefer code that is:

- simple
- explicit
- readable
- easy to debug
- easy to modify manually
- easy for another engineering student to understand

Do not introduce unnecessary abstractions.

Avoid turning simple functionality into complex frameworks.

Prefer straightforward Python over clever Python.

Prefer a few readable lines over a compressed one-liner.

Prefer normal functions and small classes over deep inheritance or complicated design patterns.

Do not add dependencies unless they provide clear value.

Do not create a new abstraction layer simply because it is theoretically cleaner.

The goal is not to produce the most sophisticated software architecture possible.

The goal is to create a **robust engineering tool that humans can understand and maintain**.

---

# Preserve Existing Style

Before implementing a new feature, inspect nearby existing files and follow their style.

Match the existing project conventions for:

- naming
- imports
- class structure
- function structure
- GUI layout
- configuration handling
- logging
- error handling
- plotting
- file paths
- data structures
- comments

Do not apply broad formatting or style changes to unrelated files.

Do not rename existing public functions, classes, configuration keys, topics, folders, or files unless required.

Do not change working behavior unless the requested feature requires it.

When several implementations are possible, prefer the implementation that fits the current project best.

---

# Incremental Changes

Extend the application gradually.

Do not replace the current dashboard with a new dashboard.

Do not replace working plotting, connection, recording, or configuration systems unless they are fundamentally blocking the requested feature.

New functionality should normally be added through:

- an additional button
- a dropdown
- a checkbox
- a settings panel
- a new tab/view
- an additional plot mode
- an optional analysis panel
- a small supporting module

Keep the existing clean dashboard appearance.

Avoid filling the main screen with controls that are only used occasionally.

Use dropdowns, dialogs, tabs, collapsible sections, or secondary configuration windows when appropriate.

---

# GUI Design

The dashboard should remain clean and engineering-focused.

Prioritize:

1. current pressure visualization
2. connection status
3. recording status
4. important live statistics
5. access to analysis tools

Advanced or rarely used functions should not dominate the main screen.

Good examples:

- plot-mode dropdown
- data-mode dropdown
- calibration button
- recording controls
- analysis/settings dialogs
- sensor diagnostics tab
- playback controls shown only during playback

Avoid unnecessary visual effects.

Avoid overly dense layouts.

Avoid excessive colors.

Use colors mainly where they convey meaningful information, such as:

- pressure
- hotspot severity
- sensor health
- connection state
- warnings

---

# Comments and Documentation

Use short comments only where they provide useful context.

Comments should normally be **one line maximum**.

Good examples:

```python
# MQTT update rate in Hz
MQTT_RATE = 20

# Minimum pressure used for contact detection
CONTACT_THRESHOLD = 2.0

# Convert calibrated force to pressure
def calculate_pressure(...):
```

Avoid comments that simply restate the code.

Do not add large explanatory comment blocks inside normal source files.

Use descriptive variable and function names instead.

Important configuration values should have a short one-line comment when their purpose is not obvious.

Important algorithms may have a short comment explaining the intention.

---

# Configuration

Keep tunable values easy to find and change.

Examples include:

- MQTT broker settings
- Serial port
- sampling rate
- filter parameters
- hotspot thresholds
- interpolation settings
- burden-model parameters
- contact threshold
- movement threshold
- calibration paths
- recording paths
- sensor dimensions
- physical cell dimensions

Do not scatter important constants throughout the code.

Where the existing project already has a config system, extend it.

If configuration is currently centralized in a small number of files, preserve that pattern.

When practical, expose commonly adjusted analysis parameters through the GUI.

---

# Data Integrity

Always distinguish between:

- raw sensor data
- filtered sensor data
- calibrated values
- baseline-subtracted values
- interpolated display values
- calculated analytics

Do not silently overwrite raw data.

Raw measurements should remain available wherever practical for:

- recording
- debugging
- calibration
- algorithm development

Interpolation must not be treated as additional real sensor resolution.

Use interpolated data primarily for visualization and contours unless a specific algorithm explicitly requires otherwise.

Core statistics and risk-related calculations should normally be based on real calibrated sensor cells.

---

# Measurement Units

Prefer:

- `kPa` for pressure
- `N` for force
- seconds/minutes for time

Allow `mmHg` as an optional pressure display unit if useful.

Avoid using MPa as the normal dashboard pressure unit unless specifically required.

Clearly label plots and statistics with their units.

---

# Recommended Data Pipeline

Where practical, preserve a logical pipeline similar to:

```text
Data source
    |
    v
Raw frame
    |
    v
Validation / missing-data handling
    |
    v
Calibration
    |
    v
Baseline subtraction
    |
    v
Optional temporal filtering
    |
    v
Feature extraction
    |
    v
Temporal analytics
    |
    +--> Main statistics
    +--> Hotspots
    +--> Center of pressure
    +--> Movement detection
    +--> Exposure / burden
    +--> Sensor diagnostics
    |
    v
Visualization
```

Serial, MQTT, and playback should ideally feed the same downstream processing pipeline.

Avoid creating separate analysis implementations for live data and recorded data.

---

# Data Sources

The application should support the existing connection methods and should be extendable around:

- Serial
- MQTT
- Playback / recorded files

The selected source should feed a common internal frame format where practical.

Connection-specific logic should not be unnecessarily mixed with plotting or analysis logic.

Track useful communication statistics when available:

- FPS
- message rate
- packet loss
- dropped frames
- latency
- connection status
- reconnect attempts

---

# Recording

Recording should preserve enough information to reproduce an experiment later.

Where practical, recordings should contain or reference:

- timestamps
- sensor frames
- raw values when available
- calibration version
- sensor layout
- units
- relevant filter settings
- relevant algorithm settings
- data-source information
- event markers
- software version or configuration version

Do not permanently bake display interpolation into the only stored data representation.

Playback should reuse the normal processing and visualization pipeline as much as possible.

Support useful playback controls such as:

- pause
- resume
- frame step
- slower playback
- real-time playback
- faster playback
- jump / seek when supported

---

# Calibration

Calibration is important because SMARTMAT uses force-sensitive resistors.

Do not assume every sensor has identical behavior.

Support per-sensor calibration where practical.

The design should allow calibration models such as:

- linear
- polynomial
- piecewise linear
- lookup/interpolation table
- power-law

Do not force a more complex model when a simple model works adequately.

Calibration tools should make it possible to inspect calibration quality.

Useful calibration outputs may include:

- offset
- sensitivity
- fit error
- RMSE
- R²
- valid range
- saturation range
- calibration curve

Keep calibration data separate from normal live measurements.

---

# Baseline / Tare

Support a clear distinction between:

- sensor calibration
- zeroing / tare
- long-term drift compensation

Do not allow automatic baseline tracking to accidentally learn away real applied pressure.

Any automatic baseline update must be conservative and understandable.

Where possible, baseline behavior should be visible and configurable.

---

# Heatmaps

Support a clean 2D heatmap as the primary pressure view.

Useful heatmap modes may include:

- raw
- calibrated
- baseline-subtracted
- pressure
- exposure
- time since relief
- sensor health
- noise
- drift
- calibration quality

Allow fixed and automatic plot scaling where useful.

Fixed scales are important when comparing recordings or experiments.

---

# 3D Pressure Plot

A 3D pressure surface may be provided as an additional visualization.

Keep it optional because the 2D heatmap should remain the primary engineering view.

Pressure may be plotted using negative Z values if that matches the current project convention.

Do not let the 3D visualization complicate or slow down the main dashboard unnecessarily.

---

# Interpolation and Contours

Interpolation can be used to create a smoother visual pressure field.

Suitable uses include:

- smoother heatmaps
- contour lines
- 3D surfaces
- presentation/demo views

Do not describe interpolation as increased physical sensor resolution.

Maintain access to the original sensor-cell grid.

Contour extraction may be used for:

- contact boundaries
- hotspot boundaries
- pressure regions

---

# Occupancy / Contact Mask

Implement or preserve an occupancy/contact mask.

This represents which cells are meaningfully loaded.

It can support:

- contact area
- center of pressure
- body-position classification
- baseline protection
- movement detection
- hotspot detection
- symmetry analysis
- anatomical regions

Keep the contact threshold configurable.

---

# General Statistics

Useful live statistics include:

- peak pressure
- mean contact pressure
- contact area
- total measured force
- estimated supported mass when meaningful
- left/right load
- upper/lower load
- heel load
- center of pressure

Do not present estimated body mass as a precision scale measurement unless it has been validated.

---

# Center of Pressure

Calculate the pressure-weighted center of pressure using real calibrated cells.

Allow the center of pressure to be displayed over the heatmap.

Support trajectory/history recording.

Useful trajectory windows may include:

- recent seconds
- recent minutes
- full recording

---

# ROI Analysis

Allow analysis of:

- one selected cell
- manually selected rectangular region
- manually selected region of interest
- predefined anatomical regions

Useful ROI outputs may include:

- current pressure
- mean
- peak
- minimum
- standard deviation
- exposure
- time above threshold
- relief time
- pressure history

Keep ROI selection intuitive.

---

# Pressure History

Allow users to inspect pressure versus time for a selected cell or region.

Where useful, allow comparison between:

- raw
- filtered
- calibrated
- averaged
- exposure

Avoid displaying too many traces by default.

---

# Averaging

Support temporal averaging separately from spatial smoothing.

Possible temporal modes include:

- no averaging
- normal moving average
- exponential moving average

Keep parameters configurable.

Clearly distinguish temporal averaging from spatial interpolation.

Do not apply strong smoothing automatically to clinical/risk-related analytics unless explicitly intended.

---

# Hotspot Detection

Hotspots should ideally be detected as regions, not only individual high-value cells.

Useful hotspot properties include:

- peak pressure
- mean pressure
- area
- position
- duration
- exposure
- time since relief

Where practical, use cluster-based detection.

Use activation/deactivation hysteresis to avoid hotspots repeatedly toggling around a threshold.

Example concept:

```text
activate above high threshold
deactivate below lower threshold
```

Keep thresholds tunable.

---

# Pressure-Time Exposure

Support a direct pressure-time measure such as:

`pressure x time`

This should remain understandable and inspectable.

Use meaningful units such as:

`kPa * min`

A cumulative exposure map should show where sustained loading has occurred over time.

---

# Pressure-Time Burden Model

A second model may accumulate pressure-related burden while allowing recovery during relief.

Its parameters must be configurable.

Do not present an experimental burden model as a medically validated injury probability.

Keep the mathematical model transparent.

Allow burden to be inspected independently from instantaneous pressure.

---

# Relief Detection

Track meaningful pressure relief.

Possible outputs include:

- full relief
- partial relief
- time since relief
- total relief duration
- relief percentage
- relief heatmap

Definitions and thresholds should remain configurable.

---

# Movement and Reposition Detection

Movement detection may use multiple simple metrics such as:

- frame-to-frame change
- center-of-pressure displacement
- contact-area change
- left/right load change
- pressure-distribution change

Prefer transparent signal-processing logic before adding machine learning.

Possible event types may include:

- micro movement
- movement
- major reposition
- bed exit

Keep classifications conservative until validated.

---

# Reposition Effectiveness

When a major reposition is detected, support comparison of a time window before and after the event.

Useful comparisons include:

- peak pressure
- mean pressure
- hotspot area
- hotspot burden
- contact area
- load symmetry
- pressure distribution

Keep the calculation explainable.

---

# Pressure Distribution Analytics

Useful plots may include:

## Histogram

`x = pressure`

`y = number of cells or contact area`

## Cumulative pressure distribution

Examples:

- 90% of contact area below X kPa
- 95% of contact area below X kPa

## Pressure-area curve

Plot:

`threshold pressure -> area above threshold`

These tools are useful for comparing materials and support surfaces.

---

# Load Distribution

Support simple distribution metrics such as:

- left vs right
- upper vs lower
- quadrants
- heels
- central region

Prefer percentage-based outputs when comparing regions.

Remember that anatomical regions may move when the person changes position.

Do not assume a permanently fixed heel/sacrum location unless the current test setup guarantees it.

---

# Symmetry

Support simple, transparent symmetry metrics.

Examples include:

- left/right imbalance
- upper/lower imbalance
- quadrant distribution

Symmetry metrics may support:

- posture classification
- movement detection
- reposition analysis

---

# Body Position Classification

Body-position classification may be added after the core measurement and analysis pipeline is reliable.

Initial implementations should favor simple, explainable features such as:

- center of pressure
- left/right distribution
- occupied area
- symmetry
- pressure distribution shape

Possible states may include:

- empty
- supine
- left side
- right side
- sitting
- moving
- unknown

Record posture changes on a timeline.

Avoid introducing machine learning until a simpler approach has been evaluated.

---

# Sensor Health

Sensor-health tools are important for SMARTMAT development.

Useful per-sensor diagnostics include:

- variance
- noise
- drift
- offset
- saturation
- dead sensor
- stuck sensor
- intermittent sensor
- unrealistic jumps
- missing data
- calibration validity

Useful engineering tests include:

- hysteresis
- creep
- recovery
- crosstalk

Provide a sensor-health heatmap where useful.

Do not mix sensor-health values with pressure values.

---

# Hysteresis Testing

Provide tools for comparing loading and unloading sensor response.

Keep hysteresis analysis separate from hotspot-detection hysteresis.

The GUI should make that distinction obvious.

---

# Creep and Recovery

Support long-duration sensor tests.

Useful outputs include:

- initial response
- response after a selected duration
- drift under constant load
- recovery after unloading
- residual offset
- recovery time

These tools are primarily engineering diagnostics.

---

# Crosstalk

Allow tests where one cell or local region is loaded while neighboring sensors are monitored.

Useful values include:

- target-cell response
- neighboring response
- crosstalk ratio
- spatial crosstalk map

Keep this as an engineering/test feature rather than part of the normal live dashboard.

---

# Pressure Concentration

Consider simple spatial concentration metrics such as:

- peak / mean ratio
- fraction of load carried by highest-pressure cells
- local pressure gradients

Keep these metrics clearly named and mathematically transparent.

Do not imply clinical meaning without validation.

---

# Risk Index

A combined risk index may eventually use inputs such as:

- pressure exposure
- hotspot persistence
- time since relief
- pressure concentration
- movement
- position duration

Do not make a combined risk score the primary output before its weighting has been validated.

Prefer displaying the individual risk components first.

Any combined score must be clearly labeled as experimental unless clinically validated.

Do not output a claimed pressure-ulcer probability from an unvalidated model.

---

# Event Timeline

Support event markers where useful.

Examples:

- recording start/stop
- calibration
- reposition
- movement
- bed exit
- hotspot started
- hotspot relieved
- connection lost
- connection restored
- user annotation

A timeline is useful during playback and experiment review.

---

# Comparison Mode

Where practical, allow comparison between two recordings or two time windows.

Useful comparison views include:

- heatmap A
- heatmap B
- difference heatmap
- peak pressure
- contact area
- exposure
- histogram
- ROI statistics

This is especially useful when comparing sensor configurations, foams, calibration approaches, or algorithms.

---

# Performance

Keep the GUI responsive.

Do not perform long blocking calculations directly in the GUI update path.

However, do not introduce complex concurrency unless it is actually required.

Use the simplest reliable approach.

Avoid recalculating expensive historical analytics every GUI frame when the result can be updated incrementally.

Keep plotting rates independent from sensor acquisition rates where useful.

---

# Error Handling

Errors should be understandable.

Prefer messages such as:

`MQTT connection lost`

over:

`Unhandled exception in callback`

Handle expected failures gracefully, especially:

- MQTT disconnect
- Serial disconnect
- invalid recording
- missing calibration file
- malformed packet
- unavailable sensor
- invalid user input

Do not silently ignore errors that affect data quality.

---

# Refactoring Rules

Small refactors are allowed when they make a requested feature easier to implement or significantly improve maintainability.

Large refactors require a clear reason.

When moving code:

- preserve behavior
- update imports carefully
- keep changes focused
- avoid moving unrelated files

New files or folders may be created when they improve organization.

Do not create many tiny modules without a practical reason.

A file should generally represent a meaningful responsibility.

---

# Folder Structure

Follow the existing folder structure first.

Only introduce new directories when they clearly improve organization.

Potential categories, if the existing structure supports them, may include:

```text
Raspberry Pi/
    gui/
    data/
    analysis/
    calibration/
    recording/
    connections/
    plots/
    config/
```

This is only a conceptual suggestion.

Do **not** force this structure onto the existing project if the current layout already works well.

Prefer evolving the existing structure.

---

# Testing Changes

After implementing a feature:

1. Run the relevant existing application or tests.
2. Confirm existing functionality still works.
3. Check the new feature with simple inputs.
4. Test obvious edge cases.
5. Verify GUI controls do not break the normal dashboard.
6. Verify live and playback modes where relevant.
7. Verify units and labels.
8. Check that raw data is not accidentally altered.

When fixing bugs, prefer solving the underlying problem rather than hiding the symptom.

---

# Do Not Overengineer

Avoid introducing technologies or patterns such as these unless the existing project already uses them or they are clearly justified:

- dependency injection frameworks
- complex plugin architectures
- excessive inheritance
- deeply nested class hierarchies
- elaborate event buses
- unnecessary async code
- unnecessary multiprocessing
- unnecessary databases
- unnecessary web frameworks
- large state-management systems
- excessive configuration frameworks

A normal Python function is often the correct solution.

A simple dictionary is often better than a complex object model.

A readable `if` statement is often better than an abstract strategy system.

---

# When Implementing a Requested Feature

Use this process:

1. Inspect the relevant existing files.
2. Identify how the current implementation works.
3. Reuse the closest existing pattern.
4. Make the smallest coherent implementation.
5. Keep configuration values obvious.
6. Add short comments only where helpful.
7. Preserve backward compatibility where practical.
8. Test the existing behavior.
9. Test the new behavior.
10. Briefly summarize what changed.

If a larger rewrite appears necessary, explain why before performing it when interactive approval is possible.

---

# Current SMARTMAT Feature Direction

The Raspberry Pi dashboard is expected to evolve toward supporting the following areas.

## Main GUI

- clean 2D heatmap
- optional 3D heatmap
- Serial / MQTT / playback selection
- connection configuration
- recording controls
- playback speed
- plot/data-mode selection
- live general statistics

## Data Modes

- raw
- calibrated
- baseline-subtracted
- pressure
- filtered
- exposure
- sensor health

## Analysis

- normal moving average
- exponential moving average
- pressure-time exposure
- burden with recovery
- hotspots
- hotspot duration
- hotspot relief
- cumulative exposure
- center of pressure
- center-of-pressure trajectory
- movement detection
- reposition detection
- reposition effectiveness
- selected-cell analytics
- selected-ROI analytics
- anatomical-region analytics
- body-position classification
- posture timeline
- relief detection
- pressure histogram
- cumulative pressure distribution
- pressure-area curve
- symmetry
- load distribution
- experimental risk components

## Engineering / Sensor Diagnostics

- sensor health
- variance
- noise
- offset
- drift
- saturation
- dead/stuck sensor detection
- calibration quality
- hysteresis
- creep
- recovery
- crosstalk
- connection latency
- FPS
- missing/dropped frames

---

# Priority Order

When deciding what to work on first, prefer approximately this order:

1. stable shared data pipeline
2. Serial / MQTT / playback reliability
3. recording and replay
4. calibration
5. raw/calibrated/baseline-subtracted views
6. core 2D heatmap
7. general statistics
8. ROI and pressure history
9. sensor-health diagnostics
10. center of pressure
11. interpolation / contours / optional 3D view
12. hotspot detection and tracking
13. pressure-time exposure
14. relief analysis
15. movement and reposition detection
16. reposition effectiveness
17. posture classification
18. combined experimental risk metrics

Do not delay a simple requested feature merely because an earlier item on this list is incomplete.

This priority order is guidance, not a strict development schedule.

---

# Final Principle

SMARTMAT should remain understandable without Codex.

A human developer should be able to:

- find important configuration values
- understand the data flow
- modify thresholds
- add a statistic
- change a plot
- debug a sensor
- adjust calibration
- inspect a recording

without needing an AI agent to explain the codebase.

Whenever choosing between a clever implementation and a clear implementation, choose the clear implementation.
