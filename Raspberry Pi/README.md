# SmartMat Raspberry Pi Application

Desktop app that turns a live pressure-sensor mat into heatmaps, calibrated kPa readings, and pressure-injury-relevant metrics - multiple mats, custom risk indices, ROI analysis, patient detection, and a small read-only web dashboard.

```
ESP32 --MQTT/Serial--> sources/ --> processing/ (calibration, analysis, detection) --> gui/ (desktop app + web dashboard)
```

See [STATUS.md](STATUS.md) (architecture map, Claude-oriented) and [notes.md](notes.md) (bugs, limitations, backlog) for the current state in detail.

## Setup

```powershell
python -m pip install -r requirements.txt
Copy-Item config.example.py config.py   # first time only
python main.py
```

Use the **Simulated** source to try it without hardware.

## First run

Pick a source and device, **Connect**, **Tare** with the mat unloaded, then open **Pressure calibration**. Switch **Data** to **Calibrated pressure** once calibrated, and **Record** to save a session. The in-app **Help** button has a short walkthrough; `notes.md` has the full feature list.

## Not a medical device

SmartMat is an engineering/research aid. Its metrics support investigating sustained loading - not a diagnosis or a validated bedsore-risk score, and custom indices are user-defined and unvalidated. Use alongside normal clinical assessment, not instead of it.

## Tests

```powershell
python -m unittest discover -s tests -v
```
