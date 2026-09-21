# SmartMat Raspberry Pi Application

SmartMat is a Python desktop application for viewing and analysing data from a pressure-sensor mat. It can receive live readings from an ESP32 over Serial or MQTT, generate simulated test data, and replay recorded sessions.

The application provides live heatmaps, pressure calibration, recording, sensor diagnostics, and engineering tools for investigating pressure distribution and movement.

## Getting started

Open a terminal in this folder and install the dependencies:

```powershell
python -m pip install -r requirements.txt
```

If `config.py` does not exist, copy the example configuration:

```powershell
Copy-Item config.example.py config.py
```

Edit `config.py` when you need to configure MQTT, grid dimensions, sensor dimensions, calibration defaults, thresholds, or connection settings.

Start the program with:

```powershell
python main.py
```

## Basic workflow

1. Select **Simulated**, **Serial**, or **MQTT** as the source.
2. Select a device or simulation and press **Connect**.
3. Confirm that the heatmap updates and check **Diagnostics**.
4. With the mat unloaded, press **Tare**.
5. Open **Pressure calibration** to load or create a measured calibration.
6. Select **Calibrated pressure** for pressure values in kPa.
7. Adjust the contact and signal-noise thresholds if needed.
8. Press **Record** to save a session for playback or later analysis.

Start with a Simulated source when learning the interface or testing without hardware.

## Main features

- **2D heatmap and 3D surface** for displaying sensor values and calibrated pressure.
- **Raw, processed, baseline-subtracted, and calibrated-pressure modes**.
- **Live, rolling-average, and exponential-average processing**.
- **Individual-cell and whole-grid pressure calibration**.
- **Tare and adjustable noise/contact thresholds**.
- **Centre of pressure**, peak pressure, mean contact pressure, contact area, and force.
- **ROI, pressure distribution, load balance, and symmetry analysis**.
- **Pressure-time exposure, experimental burden, and relief tracking**.
- **Connected hotspot, movement, and reposition detection**.
- **Sensor noise, drift, saturation, missing-data, and communication diagnostics**.
- **Raw session recording, playback, annotations, and analysis export**.
- **Optional local web heatmap and live-data endpoint**.

## Important controls

- **Plot** changes between the 2D heatmap and downward 3D pressure surface.
- **Mode** selects live or smoothed processing.
- **Data** selects which processing stage is displayed.
- **Tare** records the unloaded baseline; **Reset** clears it.
- **Contact >** sets the calibrated pressure required for a cell to count as loaded.
- **Ignore signal ≤** hides low relative sensor values without changing recorded raw data.
- **Show CoP** overlays the weighted centre of the selected data mode.
- **Plot options** provides interpolation, contours, boundaries, and reference differences.
- **Analysis** provides ROI, distribution, and load-balance tools.
- **Temporal** provides exposure, burden, and relief maps.
- **Hotspots** displays persistent connected high-pressure regions.
- **Movement** displays movement and possible reposition events.
- **Engineering** contains thresholds, presets, validation, and session export.

## Project structure

```text
main.py                 Application entry point
config.py               Local configuration and secrets (not committed)
config.example.py       Example configuration
gui/                    Desktop windows and local web interface
processing/             Calibration, analysis, detection, and recording logic
sources/                Serial, MQTT, simulation, and playback sources
recordings/             Saved sessions
tests/                  Automated processing and application tests
```

All data sources use the same general processing flow:

```text
received frame
  -> optional filtering
  -> tare subtraction
  -> pressure calibration
  -> statistics and event detection
  -> visualisation and optional recording
```

Raw received values are kept separate from processed and calibrated values. Display interpolation only smooths the visualisation; it does not create additional sensor measurements.

## Calibration note

A default linear calibration is active at startup so that pressure mode can be demonstrated immediately. It is not a substitute for physical calibration. Reliable kPa, force, exposure, and hotspot results require calibration using known loads over the expected measurement range.

Configure `CELL_WIDTH_MM` and `CELL_HEIGHT_MM` to enable physical contact area and force calculations.

## Pressure-injury use

SmartMat is an engineering and research aid. Pressure, hotspot duration, exposure, relief, and reposition measurements can support investigation of sustained loading, but they are not a diagnosis or a validated bedsore-risk score.

The mat does not measure clinical factors such as skin condition, moisture, nutrition, perfusion, friction, or shear. Its results should complement appropriate clinical assessment, skin inspection, support surfaces, and repositioning practices.

## More information

See [user_guide.md](user_guide.md) for the full operating guide, explanations of every tool and metric, calibration advice, bedsore-risk interpretation, and practical tips.

The application also includes a **Help** button with a short in-program workflow.

Run the automated tests from this folder with:

```powershell
python -m unittest discover -s tests -v
```
