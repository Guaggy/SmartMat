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

The **View: Simple | Advanced** switch (top right) hides everything but connect, tare, record, export, the data dropdown, the heatmap and the key numbers; set `START_IN_SIMPLE_MODE = True` in `config.py` to start that way. Pick a source and device, **Connect**, **Tare** with the mat unloaded, then open **Pressure calibration**. Switch **Data** to **Calibrated pressure** once calibrated, and **Record** to save a session. The in-app **Help** button has a short walkthrough; `notes.md` has the full feature list.

## Build the exe

```powershell
.venv\Scripts\pip install pyinstaller   # once, next to requirements.txt
build_exe.bat
```

Produces `dist\SmartMat\SmartMat.exe` (PyInstaller onedir, windowed) and `dist\SmartMat.zip`; `build_exe_onefile.bat` produces a single file, `dist\onefile\SmartMat.exe` (about 41 MB, starts in 6-8 s because it unpacks to `%TEMP%` on every launch, and antivirus tools dislike one-file builds more than the folder build). The logo in `assets\` is bundled into the exe. Config, `settings.json`, `mats.json`, `recordings\`, profiles and raw captures live in `%LOCALAPPDATA%\SmartMat` (or next to the exe if an empty `portable.txt` sits there, or if data already lives there); on first run `config.py` is copied there from the bundled `config.example.py`. The MQTT broker is set in the app under Engineering > Connection (default `localhost:1883`, no login; stored as plain text in `settings.json`). `SmartMat.exe --selftest` writes `selftest.txt` (app folder, mode, paths, web API answer) without opening the GUI.

## Not a medical device

SmartMat is an engineering/research aid. Its metrics support investigating sustained loading - not a diagnosis or a validated bedsore-risk score, and custom indices are user-defined and unvalidated. Use alongside normal clinical assessment, not instead of it.

## Tests

```powershell
python -m unittest discover -s tests -v
```
