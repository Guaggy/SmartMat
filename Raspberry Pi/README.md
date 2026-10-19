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

## Running the server

The server is the always-on, headless part (Pi or Windows PC, no GUI): it analyses every mat on the broker, keeps
a posture/risk timeline, raises alerts and serves the web dashboard and a REST API on one port (`SERVER_PORT`,
default 8000 - the same as the desktop's legacy Web UI, which is off by default; if it is turned on while the server runs,
the desktop says the port is in use and stays off).

```powershell
python -m server              # or: python main.py --server
python -m server --demo       # plus 5 demo mats (demo-1..demo-5) replaying samples/seat_take1.json, no hardware needed
python -m server --port 8080 --data-dir D:\SmartMatData
```

Open `http://<server>:8000` (`/api/overview` lists every mat, worst risk first). Broker settings are the same as the
desktop's (`settings.json`, else `config.py`). USB mats listed in `SERVER_SERIAL_PORTS` are read by the server and
republished to MQTT as `usb<port>` (e.g. `usbCOM3`), so desktop apps see them as MQTT mats; a port has one owner, so
do not also open it in the desktop app. The data folder holds `smartmat.db` (users, mat names/rooms, event log,
timeline; kept `RETENTION_DAYS`), `profiles\` and `mats.json` (nicknames, imported once as mat names).

Users: viewing needs no login. Every change (acknowledge an alert, edit a mat, push a calibration) sends the acting
user's PIN and is logged with their name. On first start the web page asks for the first user (admin); the REST
call is `POST /api/users {"name": "...", "role": "admin", "new_pin": "1234"}`. Afterwards only an admin adds users,
disables them or resets PINs (the "Users" button in the page, `"pin"` = the admin's PIN, role `admin` or `user` = nurse). `PIN_LOCKOUT_ATTEMPTS` (0 = off) locks a client out for `PIN_LOCKOUT_S` after that
many wrong PINs in a row.

Start at boot: Raspberry Pi - `deploy/smartmat-server.service` (systemd, steps in the file); Windows -
`deploy\install_windows_server.ps1` (scheduled task at startup, source with pythonw or `-Exe` for a build of
`SmartMatServer.spec`: `pyinstaller SmartMatServer.spec` -> `dist\SmartMatServer\SmartMatServer.exe`, no console).

Posture (left/right/forward/centred from the centre of pressure) and risk (from the summary index) are heuristics for
testing the pipeline, not a clinical assessment.

## Not a medical device

SmartMat is an engineering/research aid. Its metrics support investigating sustained loading - not a diagnosis or a validated bedsore-risk score, and custom indices are user-defined and unvalidated. Use alongside normal clinical assessment, not instead of it.

## Tests

```powershell
python -m unittest discover -s tests -v
```
