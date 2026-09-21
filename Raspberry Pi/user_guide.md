# SmartMat User Guide

SmartMat is an engineering dashboard for viewing, calibrating, recording, and analysing a 16 × 15 pressure-sensor mat. It can identify pressure concentration, insufficient relief, movement, and possible repositioning, but it does not diagnose bedsores or calculate a clinically validated bedsore-risk probability.

For more implementation detail, see [README.md](README.md). The application also contains a built-in **Help** window.

## Quick setup

Open a terminal in the `Raspberry Pi` folder and run:

```powershell
python -m pip install -r requirements.txt
python main.py
```

If `config.py` does not exist, create it from the example:

```powershell
Copy-Item config.example.py config.py
```

Edit `config.py` to configure:

- Grid dimensions and serial baud rate.
- MQTT address, username, password, and topic.
- Physical cell width and height, required for force and physical area.
- Pressure and contact thresholds.
- Default calibration or a saved calibration file.
- Hotspot, relief, movement, and diagnostic settings.

### First test without hardware

1. Select **Simulated**.
2. Choose a scenario and press **Connect**.
3. Confirm that the heatmap changes.
4. Open **Diagnostics** and inspect the incoming data.
5. Try the Analysis, Temporal, Hotspot, and Movement tools.

### Starting a real measurement

1. Connect using **Serial** or **MQTT**.
2. Allow the sensors to settle.
3. Check **Diagnostics** for sensor or communication problems.
4. Completely unload the mat and press **Tare**.
5. Perform a measured pressure calibration.
6. Select **Calibrated pressure**.
7. Set suitable contact, noise, and hotspot thresholds.
8. Press **Record** if the session should be saved.

The startup calibration is only a convenient linear default. Accurate kPa measurements require calibration against known loads.

## Main controls

### Source and recording

- **Source** selects Serial, MQTT, or Simulated data.
- **Device** selects the serial port, simulation, configured broker, or saved recording.
- **Connect / Disconnect** starts or stops the selected data source.
- **Playback speed** plays recordings at 0.25× to 5× without changing their physical exposure timing.
- **Reproduce recording** uses calibration and settings stored with the recording.
- **Re-analyze with current settings** processes raw recorded data using the current thresholds.
- **Record** stores raw frames, timestamps, calibration, tare, settings, and events in `recordings/`.

### Display controls

- **2D Heatmap** is the main viewing mode. Cells progress from white through green to red.
- **3D Surface** displays increasing pressure as a downward depression.
- **Live mode** applies no additional Raspberry Pi filtering.
- **Average** calculates a rolling average over the selected number of frames.
- **Exponential average** smooths changes using the selected smoothing factor.
- **Auto-scale** adjusts colours to the current data. Turn it off when comparing sessions.
- **Show numbers** displays each cell's value.
- **Pause** freezes the display. An active recording may continue in the background.
- **Show CoP** displays the weighted centre of the selected map.

### Data modes

- **Raw / received** is exactly what the Raspberry Pi receives. The ESP32 may already have filtered it.
- **Processed** is raw data after the selected averaging mode.
- **Baseline subtracted** is processed data minus the captured tare.
- **Calibrated pressure** converts sensor values to kPa and corrects them for tare.

Use baseline-subtracted data to check relative sensor response. Use calibrated pressure for physical measurements, temporal analysis, and hotspot detection.

### Thresholds

- **Contact > kPa** sets the pressure required for a calibrated cell to count as contact. It affects contact area, mean contact pressure, pressure CoP, movement, and related statistics.
- **Ignore signal ≤** hides low raw, processed, and baseline-subtracted values and excludes them from relative CoP. It does not alter recordings or calibration input.

Raise the signal cutoff until unloaded flicker disappears, but not so far that genuine light contact vanishes.

### Tare and pressure calibration

- **Tare** captures the unloaded sensor values as zero.
- **View tare** displays the captured baseline.
- **Reset** clears tare and auto-scaling but does not erase pressure calibration.
- **Pressure calibration** opens the calibration editor.
  - **Individual cell** tunes one sensor at a time.
  - **Whole grid** captures every cell's zero or a uniform applied pressure simultaneously.
  - **Linear** fits one sensitivity through the offset.
  - **Piecewise** interpolates between several measured calibration points.
  - **Save/Load calibration** stores or restores calibration as JSON.

For best results, calibrate at several loads spanning the expected operating range. Individual-cell calibration is preferable because FSR response can vary between cells.

## Main measurements

| Metric | Meaning |
| --- | --- |
| Peak pressure | Highest current calibrated cell pressure. |
| Mean contact pressure | Mean of cells above the contact threshold. |
| Contact cells/area | Number or physical area of cells above the contact threshold. |
| Force | Sum of pressure × cell area. Requires configured cell dimensions. |
| CoP | Pressure- or signal-weighted centre of the load. It is not necessarily the highest-pressure cell. |
| P90/P95/P99 | Pressure at or below which 90%, 95%, or 99% of contacted cells fall. |
| Load balance | Percentage of total measured load in the left/right, upper/lower, or quadrant regions. |
| Imbalance | Signed difference between two sides. Positive means left or upper. |
| FPS | Current data arrival or display update rate. |

The grid does not automatically know anatomical locations. Confirm which rows represent the head, sacrum, heels, left, and right for the installed mat orientation.

## Analysis tools

### Plot options

Plot options provide:

- Nearest or linear visual interpolation.
- Pressure contours.
- A contact boundary.
- A captured reference map.
- A current-minus-reference difference display.

Interpolation only smooths the picture. It does not create additional sensors and is not treated as extra measurement resolution.

### Analysis

- **ROI** selects a rectangular region using two heatmap corners.
- **ROI statistics** reports mean, peak, minimum, standard deviation, force, area, and weighted centre.
- **Distribution** shows a histogram and pressure percentiles for contacted cells.
- **Pressure-area curve** shows how much area remains above increasing pressure thresholds.
- **Load and symmetry** reports left/right, upper/lower, quadrant load, and imbalance.

A useful workflow is to define ROIs around areas such as the sacrum or heels, then compare peak pressure, mean pressure, exposure, and relief between positions or support surfaces.

### Temporal analysis

Temporal analysis tracks pressure over time:

- **Exposure** is pressure integrated over time in `kPa·min`.
- **Above-threshold exposure** integrates only pressure above a configured threshold.
- **Burden** is an experimental value that rises under load and decays during unloading.
- **Relief state** is Loaded, Partial relief, Full relief, or Unknown.
- **Relief percentage** is the percentage of valid observed time spent in full relief.
- **Time since relief** is the time since a cell last achieved full relief.

Relief is calculated relative to that cell's highest observed session pressure. It is not proof that the underlying tissue has been completely offloaded.

### Hotspots

Hotspots are connected regions of elevated calibrated pressure:

- Orange indicates a newly detected hotspot.
- Red indicates that the region has exceeded the persistence duration.
- Separate activation and deactivation thresholds prevent flickering near one threshold.
- The tool reports pressure, size, duration, exposure, burden, and relief.
- Regions are tracked as they move, merge, split, disappear, or resume.

A hotspot is an algorithmic pressure region, not a diagnosed skin injury.

### Movement and repositioning

Movement detection uses the largest of:

- Overall pressure-map change.
- CoP travel.
- Contact-area change.

The result is classified as stable, small, significant, or major movement. A reposition is reported only when significant movement is followed by a sustained difference between the before and after pressure distributions.

Use **Show after − before** to see where pressure increased and decreased following a detected reposition.

### Diagnostics

Diagnostics can identify:

- **Noisy** — excessive variation while unloaded.
- **Drifting** — unloaded level has changed from its earlier reference.
- **Saturated** — reading repeatedly approaches the configured maximum.
- **Possible stuck** — cell remains nearly constant at an extreme while neighbours vary.
- **Missing** — missing or non-finite readings.
- **Invalid** — readings outside the configured range.
- **Uncalibrated** — no usable pressure calibration curve.

Diagnostics also reports received, valid, malformed, and dropped frames. Do not trust analysis results while significant sensor warnings or data gaps are present.

### Engineering tools

The Engineering window contains:

- Contact, hotspot, movement, reposition, exposure, burden, and relief thresholds.
- Default, Sensitive, Conservative, and Experimental presets.
- Manual annotations for known repositions and hotspots.
- Automatic-versus-manual reposition validation.
- Session readiness and data-quality warnings.
- Experiment metadata and JSON summary export.
- Algorithm debug information.

Tune settings using labelled recordings and manual observations rather than choosing thresholds from one visually appealing heatmap.

### Web UI

- **Web UI** starts the local web server.
- **Share live data** allows its `/data` endpoint to return the live grid.
- The About panel shows the Raspberry Pi's LAN address and configured web port.

Only expose the web endpoint to trusted networks unless suitable authentication and network security have been added.

## Relating SmartMat to bedsore risk

SmartMat should be interpreted as a collection of engineering risk indicators:

- **Intensity:** peak and mean contact pressure.
- **Extent:** hotspot or high-pressure area.
- **Duration:** exposure and hotspot persistence.
- **Recovery:** relief percentage and time since relief.
- **Behaviour:** movement and confirmed pressure redistribution.
- **Confidence:** calibration, sensor health, and packet quality.

For example, a persistent hotspot with rising exposure, little recorded relief, and no sustained reposition is more concerning than a brief peak followed by clear unloading. However, SmartMat currently has no validated formula that converts these measurements into a probability of developing a bedsore.

A pressure mat cannot measure several major clinical factors, including skin condition, moisture, nutrition, perfusion, sensory loss, friction, and shear. Validated tools such as the Braden Scale include many of these factors and should be combined with clinical judgement rather than replaced by mat data. See the [AHRQ pressure-injury risk assessment guidance](https://www.ahrq.gov/patient-safety/settings/hospital/resource/pressureulcer/tool/pu3.html).

Current international guidance states that movement sensors may assist with evaluating repositioning needs, but should complement rather than replace skin assessment, clinical judgement, suitable support surfaces, and normal prevention protocols. See the [International Guideline on repositioning](https://www.internationalguideline.com/repositioning-2), [skin and tissue assessment](https://www.internationalguideline.com/assessment), and [support surfaces](https://www.internationalguideline.com/surfaces).

Do not label the experimental burden value as a bedsore-risk percentage. If a combined indicator is developed, use a name such as **SmartMat pressure-loading indicator**, keep its component measurements visible, and validate it against clinician-labelled outcomes before clinical use.

## Practical tips

- Tare only when the mat is completely unloaded.
- Keep the same bedding layers and mat orientation used during calibration.
- Allow sensors to warm up and settle before tare or calibration.
- Use fixed colour scales when comparing patients, positions, or mattresses.
- Record raw sessions so improved algorithms can be tested later.
- Use annotations to mark actual turns, bed exits, and applied test loads.
- Avoid excessive smoothing because it can hide short peaks and delay movement detection.
- Use targeted ROIs for areas such as the heels, sacrum, hips, and device contacts.
- Treat long packet gaps as unknown data, not pressure relief.
- Compare pressure before and after repositioning instead of relying only on movement detection.
- Confirm mat orientation before interpreting left/right or upper/lower load.
- Review calibration and Diagnostics whenever results appear implausible.
- Pressure-redistributing support surfaces, skin inspection, and appropriate repositioning remain essential. SmartMat is a monitoring and engineering aid.

