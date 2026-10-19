# SmartMat - setup, install and test guide

Read this top to bottom before a hardware session. Engineering aid, not a medical device.

Status key used below: **[verified]** = done and checked on this PC (build, unit tests, exe self-test),
**[not on hardware yet]** = compiled/simulated only, **[unverified]** = standard commands I have not run on your Pi.

## 1. What is what

| Device | What it is | How it reaches the app |
|---|---|---|
| **Maxrays MC266** mat, 20 x 20 | Fabric pressure mat, CH340 USB-serial, 921600 baud, about 60 frames/s, 5 V / 200 mA | **Directly** on a PC or Pi via USB-C to USB-A, or **wirelessly** through the ESP32-S3 bridge |
| **ESP32-S3 DevKitC-1** (`ESP32_China/`) | USB host: reads the MC266, averages 60 fps to 10 fps, publishes over MQTT | Wi-Fi -> MQTT broker on the Pi |
| **Resistive mat**, 16 x 15 (`ESP32_Resistive/`) | Home-built FSR matrix, classic ESP32, two multiplexers | Wi-Fi -> MQTT, or USB serial at 115200 |
| **Raspberry Pi** | Mosquitto broker + the SmartMat desktop app and web dashboard (port 8000) | - |
| **PC** (Windows) | Same app as `SmartMat.exe` or `python main.py` | USB serial or MQTT |

```
Maxrays mat --USB-C/A--> PC or Pi (Serial source, "Maxrays 20x20")           (test A)
Maxrays mat --USB--> ESP32-S3 --Wi-Fi/MQTT--> broker (Pi) --> app            (test E, F)
Resistive mat --USB serial 115200--> PC (Serial source, "ESP32 text")        (test B)
Resistive mat --Wi-Fi/MQTT--> broker (Pi) --> app                            (test C)
```

MQTT contract (all firmware and the app follow it):

| Topic | Payload |
|---|---|
| `smartmat/<chip_id>/meta` (retained) | `<id>,<rows>,<cols>` (resistive), or `<id>,20,20,255,MC266,343,358` (S3: rows, cols, value_max, model, width_mm, height_mm) |
| `smartmat/<chip_id>/frame` (**not** retained) | comma-separated ints, row-major; resistive 0-1000, S3 0-255 |
| `smartmat/<chip_id>/status` (retained, S3 only) | `online` / `offline` (last will); the app does not read it yet |

The app scales every mat to its internal 0-1000 range once, at ingest, using `value_max`.

## 2. What to install

### Windows PC
- **Python 3.11+** (3.13 used here), add to PATH. Only needed to run from source, build the exe, or flash.
- **CH340 driver**, if the mat's port does not appear in Device Manager as `USB-SERIAL CH340 (COMx)`
  (Windows Update normally supplies it).
- **VS Code + PlatformIO** (or the PlatformIO CLI) to build/flash the ESP32s. [verified]
- Optional: **mosquitto clients** (`mosquitto_sub` / `mosquitto_pub`) to inspect the broker from the PC.

### Raspberry Pi [unverified on your Pi]
```bash
sudo apt update
sudo apt install -y mosquitto mosquitto-clients python3-venv python3-tk git
```

## 3. Install the app

### PC, from the exe [verified]
Two builds, same program:

| Build | File | Start | Use it for |
|---|---|---|---|
| Folder (zip) | `Raspberry Pi\dist\SmartMat.zip` -> unzip anywhere -> `SmartMat.exe` | about 2 s | The school/pilot PC, locked-down or antivirus-scanned machines |
| One file | `Raspberry Pi\dist\onefile\SmartMat.exe` (single file, about 41 MB) | about 6-8 s (unpacks to `%TEMP%` on every launch) | Quick tests, sending to a friend; may trip antivirus |

Your data (`config.py`, `settings.json`, `mats.json`, `recordings\`, `profiles\`, raw captures, `selftest.txt`) lives in
**`%LOCALAPPDATA%\SmartMat`**, not next to the exe. To keep it next to the exe instead (USB stick), create an empty
file named `portable.txt` beside `SmartMat.exe`; installs that already have data next to the exe keep using it.
The broker is set **inside the app**: Engineering > Connection (host, port, user, password, Test, Save); the
default is `localhost:1883` without a login. The password is stored as plain text in `settings.json`.
Headless check: `SmartMat.exe --selftest` writes `selftest.txt` (app folder and mode, exit code 0 = OK).

#### Sending the exe to a friend
Send the one-file `SmartMat.exe` (or the zip). Tell them: Windows SmartScreen will say "unknown publisher"
(the exe is unsigned): **More info > Run anyway**; they need Windows 10/11 64-bit, no Python; Source
**Simulated** works without any hardware; with the mat they need the CH340 driver and must close the vendor
client. MQTT needs your broker address and login, so USB or Simulated is the path for a friend.

### PC, from source [verified]
```powershell
cd "Raspberry Pi"
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
Copy-Item config.example.py config.py        # first time only, then edit
.venv\Scripts\python main.py
```
Use a venv: a global `paho-mqtt` 1.x (pinned by some other tools) breaks MQTT; the app needs 2.x.

### Rebuild the exe [verified]
```powershell
cd "Raspberry Pi"
.venv\Scripts\pip install pyinstaller        # once
.\build_exe.bat                              # folder build -> dist\SmartMat\SmartMat.exe and dist\SmartMat.zip
.\build_exe_onefile.bat                      # one file    -> dist\onefile\SmartMat.exe
```
(`build_exe_onefile.bat` uses `SmartMat-onefile.spec`; keep its Analysis section in sync with `SmartMat.spec`.
Run both from PowerShell as `cmd /c ".\build_exe.bat"` if a plain call does not start.)

### Raspberry Pi [unverified]
```bash
git clone https://github.com/Guaggy/SmartMat
cd "SmartMat/Raspberry Pi"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.py config.py && nano config.py
sudo usermod -aG dialout $USER               # serial access for /dev/ttyUSB0; log out and in again
.venv/bin/python main.py                     # the desktop app: needs a desktop session (VNC / Raspberry Pi Connect screen share)
```

For a Pi nobody sits at, run the headless server instead of the desktop app (section 4b).

## 4b. Headless server on the Pi (always on) [unverified on your Pi]

The server (`python -m server`, no screen or tkinter) reads every mat on the broker, raises alerts, pushes them to
registered phones and serves the dashboard and REST API on port 8000. Do section 3 (clone, venv, `config.py`) and
section 4 (Mosquitto) first; put the broker login in `config.py` (`mqtt_username`, `mqtt_password`; `broker_host`
stays `localhost` when the broker runs on the same Pi).

```bash
cd "SmartMat/Raspberry Pi"
.venv/bin/python -m server --demo 2          # try it first: two demo mats, open http://<pi>:8000, Ctrl+C
# then as a service that starts at boot and restarts itself:
nano deploy/smartmat-server.service          # User, and the project path in WorkingDirectory/ExecStart if not /home/pi/...
sudo cp deploy/smartmat-server.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now smartmat-server
systemctl status smartmat-server             # active (running)
journalctl -u smartmat-server -f             # its output; "SmartMat server on http://0.0.0.0:8000"
curl http://localhost:8000/api/health        # {"ok": true, ...}
```

- Data (database, per-mat profiles, mat names) is kept in `/var/lib/smartmat`, not in the git checkout: `git pull`
  never touches it. Back that folder up; it holds the users' PIN hashes and the alert log.
- First visit: the dashboard asks for the first administrator (name + PIN). Viewing needs no login; every change asks for a PIN.
- Configuration is in the dashboard (**Innstillinger** / Settings button): name, room, seat and unit of each mat, removing a
  retired mat, alert delays, push on/off, risk sensitivity, storage time, and users. Only an administrator's PIN saves
  changes; they apply at once and are written to the log with the name. `config.py` holds the defaults; "Reset" on a
  setting goes back to the `config.py` value.
- Per mat: the settings page lists every mat with **Analyse**. A mat can have its own alert delays, risk sensitivity,
  stale limit, posture values and the engineering values of the desktop app (contact, time analysis, hotspots, movement);
  what it does not set follows the site's values ("Standard for hele stedet"), which follow the factory values. Every change
  is a numbered version with name, time and an optional reason, any version can be restored, and every alert shows which
  settings version raised it.
- Several mats show up on their own as the broker announces them (a mat that is switched off stays listed as offline).
- Power cuts: the database runs in WAL mode, so a cut at worst loses the last second or two. Set the Pi's
  time zone (`sudo raspi-config`) and keep NTP on; right after a boot without network the clock may jump once,
  which the server tolerates (it does not raise alerts from the jump).
- Update: `git pull && sudo systemctl restart smartmat-server`. Open alerts survive the restart and are not pushed twice.
- Network: the dashboard is plain HTTP and the PIN travels with each change, so keep it on the clinic LAN. For access
  from outside use Tailscale (section 11), never a router port-forward.
- A USB mat plugged into the Pi: add it to `SERVER_SERIAL_PORTS` in `config.py`, `sudo usermod -aG dialout pi`, restart.

## 4. Mosquitto broker on the Pi [unverified on your Pi]

Mosquitto 2.x refuses remote clients unless you configure a listener and users.

```bash
ls /etc/mosquitto/conf.d/                                         # must hold only smartmat.conf (see note below)
sudo mosquitto_passwd -c /etc/mosquitto/passwd smartmat          # asks for a password
sudo chown mosquitto:mosquitto /etc/mosquitto/passwd             # the broker runs as user mosquitto
sudo chmod 640 /etc/mosquitto/passwd
sudo tee /etc/mosquitto/conf.d/smartmat.conf <<'EOF'
listener 1883
allow_anonymous false
password_file /etc/mosquitto/passwd
EOF
sudo systemctl restart mosquitto
hostname -I                                                       # the Pi's address for the configs below
```

If `ls` shows another file with a `listener` line (for example `listener.conf` with `listener 1883 0.0.0.0` and
`allow_anonymous true`, left by an earlier setup), Mosquitto exits with status 13 and no useful message. Move it away
(`sudo mv /etc/mosquitto/conf.d/listener.conf ~/`), then `sudo systemctl reset-failed mosquitto` and restart.
`sudo journalctl -u mosquitto -n 20 --no-pager` shows which files were loaded; `sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v`
prints the real error in the foreground.

The same host/username/password go into three places:
the app (**Engineering > Connection**, saved in `settings.json`; or `Raspberry Pi/config.py`
`broker_host`/`mqtt_username`/`mqtt_password` when running from source),
`ESP32_Resistive/src/secrets.h` and `ESP32_China/src/secrets.h` (copy each from `secrets.h.example`;
`secrets.h` is gitignored, never commit it). Precedence in the app: `settings.json` > `config.py` > `localhost`.

Use a fixed address: a DHCP reservation on the router, or note `hostname -I` and re-flash if it changes.
The firmware takes an IP string, not a hostname.

Watch the traffic (from the Pi or any machine with mosquitto-clients):
```bash
mosquitto_sub -h <pi> -u smartmat -P '<password>' -t 'smartmat/#' -v
mosquitto_sub -h <pi> -u smartmat -P '<password>' -t 'smartmat/+/meta' -v -W 3     # known mats
mosquitto_sub -h <pi> -u smartmat -P '<password>' -t 'smartmat/+/status' -v        # online/offline
```
Clear a stale retained message (old pre-multi-mat topic, or a mat you retired):
```bash
mosquitto_pub -h <pi> -u smartmat -P '<password>' -t smartmat/frame -r -n
mosquitto_pub -h <pi> -u smartmat -P '<password>' -t smartmat/<old_chip_id>/meta -r -n
```

## 5. Flash the firmware

### Resistive (classic ESP32) [compiled; not flashed since the last change]
```powershell
cd ESP32_Resistive
Copy-Item src\secrets.h.example src\secrets.h          # then edit Wi-Fi + MQTT values
%USERPROFILE%\.platformio\penv\Scripts\python.exe -m platformio run -t upload
%USERPROFILE%\.platformio\penv\Scripts\python.exe -m platformio device monitor -b 115200
```
Test-mode settings are already set in `src/main.cpp`: `send_frame_serial = true`, `serial_debug = false`,
serial copy limited to 5 fps (the 115200 link cannot carry 10 fps of 240 values), MQTT 10 fps.

### ESP32-S3 bridge [compiles; not on hardware yet]
Plain `pio` is too old and pioarduino must not touch your global PlatformIO core, so use a separate core dir
(already downloaded to `%USERPROFILE%\.pio-core-s3`; a fresh one takes about 20 minutes on first build).
```powershell
cd ESP32_China
Copy-Item src\secrets.h.example src\secrets.h          # then edit
$env:PLATFORMIO_CORE_DIR = "$env:USERPROFILE\.pio-core-s3"
& "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" -m platformio run                      # both envs
& "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" -m platformio run -e esp32-s3-simulate -t upload --upload-port COMx
& "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" -m platformio device monitor -b 115200 --port COMx
```
Flash with the S3's **UART** USB port (the one marked UART/COM), not the native USB port.
Envs: `esp32-s3-simulate` (moving blob, no mat needed) and `esp32-s3-devkitc-1` (real USB host).

## 6. S3 wiring and power

| USB-A **female** breakout | ESP32-S3 DevKitC-1 |
|---|---|
| D+ | GPIO20 |
| D- | GPIO19 |
| GND | GND |
| VBUS | 5V pin |

The mat plugs into the breakout with its own USB-C to USB-A cable. Power the S3 from its UART port (power
bank or 1 A charger), not from the mat. Budget: S3 with Wi-Fi about 0.3 A plus mat 0.2 A = about 0.5 A, so a
weak laptop port is borderline. Do **not** use a bare USB-C breakout (no CC pull-up, the mat may not power up).
Measure the mat's real draw with the inline USB-C meter. If you have not wired it yet, test E (simulate) needs
no breakout and no mat.

## 7. Tests, in this order

Each test: do the steps, compare with "Expect". Note anything that differs.

### Test A - Maxrays mat directly on the PC [first priority]
1. Close the vendor "FLX Sensor Client" (only one program can hold the COM port).
2. Plug the mat in. Device Manager shows `USB-SERIAL CH340 (COMx)`.
3. Start `SmartMat.exe`. Source **Serial**, Protocol **Maxrays 20x20 (921600)**, Device the CH340 port,
   **Connect**. Switch the view to **Advanced** for the tools below.
4. Expect: a 20 x 20 heatmap and "Mat: Maxrays MC266" in the About panel, no error text. Unloaded, nothing lights.
5. **Tare** with nothing on the mat. Press with a hand, then sit/put a weight on it.
6. **Diagnostics...**: about 60 frames/s "in", about 10 frames/s "out", discarded bytes flat (not climbing),
   malformed/invalid close to 0.
7. **Capture raw (5 s)**: once unloaded, once loaded. Files land in `recordings\raw_maxrays_<timestamp>.bin`
   (in `%LOCALAPPDATA%\SmartMat\recordings\`, or next to the exe in portable mode). Keep both; copy one to `Raspberry Pi\tests\fixtures\maxrays_capture.bin`.
8. Write down: does pressure make values go **up** or **down**? Do loaded cells **saturate at 255**? Is the
   picture **mirrored/rotated** (fix with Rotate/Mirror, then re-tare)? Idle noise in counts? Frame rate?
9. **Mat size...**: the preset is 343 x 358 mm (measured from the datasheet drawing, about +/-5 %). Measure
   the real sensing area with a ruler and enter it; "Estimated load" then shows a kg value (marked
   "default curve, not calibrated" until you calibrate; the vendor says the mat is not suitable for weighing).
10. **Record** 30 s, stop, play it back (Source Simulated, pick the recording). **Export snapshot...** writes
    a CSV and PNG; Engineering > Session & export > "Recording to CSV...".

### Test B - Resistive mat over USB on the PC
1. Flash as in section 5, plug it in, wait for boot (three boot lines, then about 5 lines/s of 240 numbers).
2. App: Source **Serial**, Protocol **ESP32 text (115200)**, its COM port, **Connect**. Open the app after the
   board has booted (the three boot lines are counted once as malformed).
3. Expect a 16 x 15 grid; Tare; press; values 0-1000.
4. Note frame rate and whether mux settling looks right (ghosting / crosstalk between neighbouring cells).

### Test C - Resistive mat over MQTT
1. Broker running (section 4), `secrets.h` filled in, board flashed and on Wi-Fi.
2. `mosquitto_sub ... -t 'smartmat/+/meta' -v -W 3` shows `<id>,16,15`.
3. App: Source **MQTT**; the mat appears in the device list (use **Rename...** to give it a nickname);
   Connect. Expect 16 x 15 and about 10 fps. Frames are not retained: nothing shows while the board is off.

### Test D - switch between mats
Connect Maxrays (20 x 20), then resistive (16 x 15), then back. The grid size changes each time, nothing
crashes, and each mat's tare/calibration/orientation comes back from `profiles\<mat id>.json`.

### Test E - S3 bridge, simulate build (no mat, no breakout)
1. Flash `esp32-s3-simulate` (section 5). UART log once a second shows stats.
2. `mosquitto_sub -t 'smartmat/+/status' -v` shows `online`; unplug the S3 and `offline` appears after the
   keep-alive (about 15 s).
3. App MQTT source: a 20 x 20 mat appears ("Mat: MC266") with a moving blob, about 10 fps, default size 343 x 358.

### Test F - S3 bridge with the real mat [first hardware run]
1. Multimeter: S3 powered from the UART port, VBUS on the breakout is about 5 V and not shorted to GND.
2. Inline meter on the mat: note idle and pressed current.
3. Flash `esp32-s3-devkitc-1`, mat in the breakout. UART log: mat up, about 60 frames/s decoded, discarded and
   invalid flat, `net stack free` above about 1 KB (if it is lower, raise `network_stack_bytes`).
4. App sees the mat via MQTT; compare frame by frame with test A (same orientation, same range).
5. Pull/replug the mat and the Wi-Fi: recovers without reset, status back to `online`.
6. Stop the broker for 30 s: decoded frames/s stays about 60 and discarded/invalid do not grow, only
   `net dropped` does.

### Test G - web dashboard
Desktop app: enable **Web UI**; open the two links in the About panel (hostname.local:8000 and the IP) from a phone
or another PC on the same network. Only the mat currently open in the desktop app is live there. The headless
server (test H) shows every mat.

### Test H - headless server on the Pi (hardware needed)
Needs section 4b done, the Pi on the LAN and at least one real mat (or `tools/publish_demo_mat.py` from a PC).
1. `systemctl status smartmat-server` is active; `curl http://<pi>:8000/api/health` from the PC answers.
2. Reboot the Pi (`sudo reboot`) with nobody logged in: after about a minute the dashboard is back by itself.
3. `http://<hostname>.local:8000` opens from a phone and a PC (Avahi/mDNS; if not, use the IP and note it).
4. Power on two mats (or the demo mat plus a real one): both appear within seconds, each with a live pressure map.
5. Unplug one mat: its row turns offline within `STALE_AFTER_S`, and an offline alert opens after `ALERT_OFFLINE_S`.
   Plug it back: the alert clears.
6. Stop Mosquitto for a minute (`sudo systemctl stop mosquitto`) and start it again: the mats come back without
   restarting the server.
7. With an alert open (e.g. the offline one), `sudo systemctl restart smartmat-server`: the alert is still open after
   the restart, and a registered phone does not get a second push.
8. Pull the Pi's power cable while it runs, plug it back: the server starts again, the users and mat names are still there.
9. Phone on mobile data, Tailscale on: the dashboard opens at `http://<pi-tailnet-name>:8000`.

### Test I - everything on one Windows PC (no hardware, no Pi)
From `Raspberry Pi\` in PowerShell. Steps 1-3 are automatic; 4-6 are a click-through. Write down anything that fails
(the exact text of the error or what you saw).
1. Setup, once:
   ```powershell
   py -m venv .venv
   .venv\Scripts\pip install -r requirements.txt pytest amqtt psutil
   if (-not (Test-Path config.py)) { Copy-Item config.example.py config.py }
   ```
2. Unit tests, including the desktop (tkinter) ones that could not run in the cloud: `.venv\Scripts\python -m pytest -q`.
   Expect no failures (one skipped test is normal).
3. The whole server pipeline over a real MQTT broker (starts its own broker, server and demo mats in a temp folder,
   needs port 1883 free and about 6 minutes; allow Python through the Windows Firewall if it asks):
   `.venv\Scripts\python tools\e2e_check.py` (add `--quick` to skip the one-minute memory watch). Expect `0 failed`.
   On Windows the "server stops cleanly" check becomes a hard stop, which doubles as a crash/restart test.
4. Server and dashboard by hand: `.venv\Scripts\python -m server --demo 5`, open `http://localhost:8000`.
   - First visit asks for the first admin (name + PIN). Then: expand a row (chevron), see the posture timeline and the
     map ("Foran" on top), search, filter, sort, switch language (EN/NO) and light/dark, press F12 and use the device
     toolbar to check phone and tablet widths.
   - Gear button (Innstillinger): change "Tid frakoblet før varsel" to 10, wrong PIN is refused, right PIN saves and says
     who; Reset puts it back; Users section opens the users dialog; add a nurse and acknowledge something with that PIN.
   - Settings are admin-only: a nurse PIN on Save must be refused.
   - Stop the server with Ctrl+C and start it again: users, settings and mat names are still there.
5. Desktop app: `.venv\Scripts\python main.py`. Use **Load demo recording**, then go through the tabs (Live, Analysis,
   Timeline, Hotspots, Movement, Indices, Diagnostics, Calibration, ROI, Engineering, Help), Simple/Advanced view, light/dark,
   Tools > Expression, record + export CSV, export snapshot (CSV + PNG), Pop out a tab. Then Engineering > Connection >
   SmartMat server: URL `http://localhost:8000` (server from step 4 running; the desktop's own Web UI toggle uses the same
   port, so leave it off), **Test**, **Send calibration to server** (admin PIN), **Get from server**, **Server log**.
6. Packaging (optional): `.\build_exe.bat`, then `dist\SmartMat\SmartMat.exe --selftest` and open the exe.
Not covered without hardware: the real Maxrays/ESP32 mats, the Pi, mDNS (`.local`), push to a real phone. The phone app's own
tests: `cd "..\Phone App"; npm ci; npm test; npm run typecheck`.

### Test the MQTT path without hardware
`Raspberry Pi/tools/publish_demo_mat.py` replays the bundled seat recording to the broker as a fake S3 mat with
chip id `demo-take1` (retained meta and `online` status, last will `offline`, frames at the recording's own pace,
looping). On the PC, from `Raspberry Pi/` (venv active):
```powershell
python tools\publish_demo_mat.py                  # broker host/login from the app's settings (Engineering > Connection)
python tools\publish_demo_mat.py --once --speed 2 --host <pi> --user smartmat --password '<password>'   # overrides
```
Then open the app, Source **MQTT**, and pick **demo-take1 (demo)**. Stop the tool with Ctrl+C. Ids starting with
`demo-` (`DEMO_PREFIX` in `config.py`) are marked "(demo)"; clear the leftover retained mat with
`mosquitto_pub ... -t smartmat/demo-take1/meta -r -n`. For playback without a broker, use **Load demo recording**.

## 8. What to bring back

| Item | Why |
|---|---|
| Both raw `.bin` captures (unloaded, loaded) | Decode the 2 trailer bytes (checksum?), real frame rate, noise, saturation; becomes the test fixture |
| Polarity, saturation, orientation, idle noise in counts | Health-threshold retune for the 8-bit mat; orientation default |
| Measured mat sensing size | Replace the +/-5 % preset estimate |
| Inline-meter currents (idle / pressed) | Confirms the 5V pin can feed the mat |
| S3 UART log lines during the outage test | Confirms the two-core fix |
| Anything odd in Diagnostics (malformed/dropped) | Source-quality problems |

## 9. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| No CH340 port | Wrong cable (charge-only), missing driver, vendor client holding the port |
| Maxrays: connects, no frames | Wrong protocol in the dropdown (text vs Maxrays), baud must be 921600; capture raw and check for `A5 5A` |
| "discarded bytes" keeps climbing | Stream differs from the spec (filler/other packet): send the raw capture |
| Picture mirrored/rotated | Rotate/Mirror controls; re-tare afterwards (changing them resets that mat's tare) |
| Mat missing from MQTT list | Broker address/user/password wrong in `secrets.h`; Wi-Fi 5 GHz (ESP32 is 2.4 GHz only); check `mosquitto_sub` |
| MQTT: "Cannot reach MQTT broker" / "refused" | Set host, port and login under **Engineering > Connection** and press **Test connection**; from source also check `config.py`; paho 1.x installed (use the venv) |
| Old mats stay in the device list | Retained `meta`: clear with `mosquitto_pub ... -t smartmat/<id>/meta -r -n` |
| S3: nothing from the mat, status online | Breakout wiring (D+/D- swapped), VBUS missing, mat draws too much, wrong cable |
| S3 resets when Wi-Fi starts | Weak supply: use a power bank or 1 A charger |
| App says "Estimated load: set mat size" | Use "Mat size..." (now also reachable in Simple view) |
| `pio` errors about platform | Use the explicit penv python and `PLATFORMIO_CORE_DIR` from section 5 |

## 10. Command cheat sheet

```powershell
# app tests (from "Raspberry Pi")
.venv\Scripts\python -m unittest discover -s tests -v
# firmware host tests (g++ on PATH, S3 core dir set)
& "$env:USERPROFILE\.platformio\penv\Scripts\python.exe" -m platformio test -e native
# raw capture without the GUI (921600 baud, 5 s)
.venv\Scripts\python tools\capture_raw.py --port COM5 --seconds 5
# exe
.\build_exe.bat ; dist\SmartMat\SmartMat.exe --selftest
```

## 11. Parked / after the test

- Decode the raw capture: trailer/checksum, then decide whether to validate frames; retune the health
  thresholds for 8-bit counts; guided known-weight calibration (the vendor says the mat is for trends, about
  +/-10 % at best, so the kg readout stays "indicative").
- Ask the vendor (amy@maxrays.cn) for the protocol document and what "Send to Serial Port" does.
- Product work for the S3: Wi-Fi provisioning (captive portal instead of `secrets.h`), OTA updates.
- Contact email shown in the app is `contact@verdianmedical.com` (confirmed), set in
  `Raspberry Pi/branding.py` together with `VERSION` (shown in About, the window title and `selftest.txt`).
- **Remote access to the Pi** (Trinity network), after the test [unverified commands]:
  Raspberry Pi Connect for desktop/shell access (`sudo apt install rpi-connect`, then `rpi-connect on` and
  `rpi-connect signin`; see the Raspberry Pi docs), and Tailscale for the tailnet:
  `curl -fsSL https://tailscale.com/install.sh | sh` then `sudo tailscale up --ssh`;
  reach the dashboard at `http://<pi-tailnet-name>:8000` and Mosquitto on the Pi's `100.x` tailnet address.
  Check that the broker and the dashboard listen on the Tailscale interface before relying on it.
- A headless Pi (no screen) runs the server as a service (section 4b); the desktop app still needs a display.
