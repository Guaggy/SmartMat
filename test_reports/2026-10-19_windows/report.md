# SmartMat test pass - Windows PC, 2026-10-19

Run from `Raspberry Pi\`, following "Test I" in SETUP_AND_TEST.md. Nothing was fixed or refactored. Logs are in ``.

## 1. Environment

| | |
|---|---|
| Commit at start | `66c71aae47d79582c3f62543c082ea604893fa3f` (main, "e2e_check: always use its own broker ...") |
| Git tree at start | **clean**. `git pull` said "Already up to date". |
| HEAD at the end | `3ab8f2a` - see section 6: three commits appeared while I was working, none made by me |
| Windows | Microsoft Windows 11 Home 10.0.26300 |
| Python | 3.13.2 (`py --version`; the venv python is also 3.13.2) |
| Port 1883 / 8000 at start | both free (`netstat` showed nothing). No Mosquitto running. |
| Port 1883 / 8000 at end | both free, nothing LISTENING |
| venv | existed; `pip install -r requirements.txt pytest amqtt psutil` found everything already satisfied (nothing installed) |
| config.py | existed, **older than config.example.py**. Left as it is. Full `fc.exe` output: `config_diff.txt` |

### config.py vs config.example.py (summary of `fc`)
`config.py` (last written 2026-10-08) lacks these things that `config.example.py` has:
- `MAT_WIDTH_MM`, `MAT_HEIGHT_MM`; `HOTSPOT_ACTIVATE_FRACTION`, `HOTSPOT_DEACTIVATE_FRACTION`, `HOTSPOT_RELIEF_GRACE_S`; `SERIAL_TARGET_FPS`
- `START_IN_SIMPLE_MODE`, `SATURATION_WARN_CELLS`, `DEMO_PREFIX`
- the whole server block (`SERVER_PORT`, `SERVER_SERIAL_PORTS`, `POSTURE_*`, `ALERT_*`, `RISK_*`, `PUSH_*`, `RETENTION_DAYS`, `PIN_LOCKOUT_*`)

Different values:

| Setting | config.py | config.example.py |
|---|---|---|
| `broker_host` | `192.168.1.50` | `localhost` |
| `CONTACT_THRESHOLD_KPA` | 2.0 | 1.0 |
| `HOTSPOT_MIN_CELLS` | 2 | 4 |
| `HOTSPOT_END_RELIEF_S` | 3.0 | 10.0 |
| `HEALTH_SATURATION_FRAMES` | 5 | 10 |
| `HEALTH_STUCK_NEIGHBOR_STD` | 15 | 60 |

Consequence: any tool that uses the saved broker address would try `192.168.1.50`. `settings.json` has no broker saved. See "Changes" for how I got around it.

## 2. Summary

| Step | Result | One line |
|---|---|---|
| A. Unit tests | **FAIL (flaky)** | Run 1: 544 passed, 3 skipped, 0 failed. Run 2: **1 failed**, 544 passed, 2 skipped. The failure does not reproduce in isolation (6/6 pass). |
| B. e2e_check (full, 6 min) | PASS | 105 passed, 0 failed, exit 0, 4m36s |
| C. Server by hand (`--demo 5`) | PASS | All checks as expected (one wrong check in my own script, redone; see 3C) |
| D. Passport without hardware | PASS, with one note | All expected results, but only after a server restart; the order in the task gives a 502 on the first write (see 3D) |
| E. Imports | PASS (partial) | `import gui.desktop` ok. `main.py --help` is not supported: it starts the GUI. |
| Desktop (5), 6 desktop part, 7 | NOT RUN | needs a human |

## 3. Per step

### A. Unit tests
Command: `.venv\Scripts\python -m pytest -q`

**Run 1** (PowerShell, 21:05:26 - 21:08:51, pytest says 202.49s): `544 passed, 3 skipped, 86 subtests passed`. A stray block of stderr text appeared in the middle; PowerShell swallowed most of it, see run 2. Log: `pytest.txt`.

**Run 2** (same command, plus `-rs`, via bash so stderr is kept; about 21:09 - 21:12, 199.43s): `1 failed, 544 passed, 2 skipped, 86 subtests passed`. Log: `pytest_rerun_rs.txt`.

The failure, verbatim:
```
=================================== FAILURES ===================================
___ PassportApiTests.test_adopting_a_slot_sets_the_calibration_and_logs_it ____

self = <test_server_passport.PassportApiTests testMethod=test_adopting_a_slot_sets_the_calibration_and_logs_it>

    def test_adopting_a_slot_sets_the_calibration_and_logs_it(self):
        self.give(custom=blob_of())
        self.assertEqual(self.post("/api/mats/m1/passport/adopt", slot="custom").status_code, 401)
        self.assertEqual(self.post("/api/mats/m1/passport/adopt", slot="custom", pin=NURSE).status_code, 403)     # admin only
        self.assertEqual(self.post("/api/mats/m1/passport/adopt", slot="x", pin=ADMIN).status_code, 400)
        reply = self.post("/api/mats/m1/passport/adopt", slot="custom", pin=ADMIN)
        self.assertEqual(reply.status_code, 200, reply.get_json())
        self.assertEqual(self.engines["m1"].profile_version, 1)
>       self.assertTrue(same_calibration(self.engines["m1"].profile, demo_profile(20, 20)))
E       AssertionError: False is not true

tests\test_server_passport.py:67: AssertionError
```
The traceback is only this one frame, so there are no further lines.

Re-runs: `pytest -q tests/test_server_passport.py` six times in a row: `11 passed` every time (3-4 s each).

Also in run 2, before the failure, a traceback was printed on stderr by a test HTTP server thread (not a failure by itself):
```
Traceback (most recent call last):
  File ".../Python313/Lib/socketserver.py", line 697, in process_request_thread
    self.finish_request(request, client_address)
  ...
  File "...\tests\test_server_client.py", line 49, in do_GET
    self.reply(200, b"{}")
  File "...\tests\test_server_client.py", line 38, in reply
    self.wfile.write(body)
  File ".../Lib/socketserver.py", line 845, in write
    self._sock.sendall(b)
ConnectionAbortedError: [WinError 10053] An established connection was aborted by the software in your host machine
```
(full text in `pytest_rerun_rs.txt`, lines 6-28).

Skips: run 2 skipped `tests\test_indices.py:347` ("Tk display unavailable") and `tests\test_maxrays.py:82` (`tests/fixtures/maxrays_capture.bin` not present). Run 1 skipped 3, I did not capture which. Running `tests/test_indices.py tests/test_maxrays.py` alone gave 3 skips (two "Tk display unavailable", at lines 431 and 442, and the maxrays one).

Guess (not verified): the failing test depends on state or timing shared with earlier tests in the same process (it passes alone). That the test is also order-dependent on machine state would fit the Tk skips changing between runs. The comparison `same_calibration(engine.profile, demo_profile(20, 20))` being False suggests the adopted profile differs from the demo profile, maybe because of a leaked global setting (for example `config` values or `calibration.PROFILES_DIR`) set by another test. The `ConnectionAbortedError` traceback is probably a test client closing the connection early (guess).

### B. End to end
Command: `.venv\Scripts\python tools\e2e_check.py` (full, no `--quick`). Start 21:13:33, end 21:18:09 (4m36s). Result: `105 passed, 0 failed`, exit code 0. Includes the passport sections and "no traceback anywhere in the server log". Log: `e2e.txt`. The server.log it printed (`...\Temp\smartmat_e2e_re_dvdgb\server.log`) was already deleted when I looked, so it is not attached; there were no FAIL lines. Note that `e2e.txt` is tracked in git in an older shape, see section 6.

### C. Server by hand
Command: `.venv\Scripts\python -m server --demo 5 --data-dir <temp folder>` (see "Changes": I used a temp data dir). Logs: `server_c_run1.log`, `server_c_run2.log`, `step_c_phase1.txt`, `step_c_phase1b.txt`, `step_c_phase2.txt`.

| Check | Result |
|---|---|
| GET /api/health | 200, `mats: 5` |
| GET /api/overview | 200, 5 mats |
| POST /api/users `{role: admin, new_pin: 1234}` | 201 |
| second POST /api/users with no PIN | 401 "PIN required" (refused) |
| PUT /api/settings wrong PIN | 403 "Wrong PIN" |
| PUT /api/settings admin PIN (1234) | 200, `alert_offline_s` 30 -> 10, history entry version 1 |
| PUT /api/settings user ("nurse") PIN | 403 "Only an admin can do this" |
| GET /api/mats/demo-1/config | 200 |
| GET /api/config/history | 200 |
| Stop server, start again, same data dir | users `Admin`, `Nurse1` still there, `alert_offline_s` is still 10 (source `site`), history still has version 1 |

Mistake of mine, for the record: in the first pass of my script I created the second user with role `nurse`; the API only accepts `admin` or `user` (400 "Role must be one of admin, user"). The first "nurse PIN refused" line was therefore meaningless (the PIN did not exist). I redid it with role `user`: the result is the 403 above. Server logs contain no traceback. No Playwright was installed, I used plain HTTP.

### D. Passport without hardware
Started in the background, logs in `d1..d4*.log`: `e2e_check.py --broker`, `publish_demo_mat.py --chip-id demo-take1`, `python -m server --data-dir <temp folder>`, `fake_passport_device.py --chip-id demo-take1 --serial SM-0001 --service-key sesame --custom 20x20`. Times about 21:20 - 21:23. All four with `SMARTMAT_MQTT_HOST=127.0.0.1` etc. set in the shell (see "Changes").

| Check | Result |
|---|---|
| `passport_tool.py show demo-take1` | `serial SM-0001`, `factory: empty`, `custom: custom v1 by fake device ... [342 bytes, crc 03ac2399]` |
| GET /api/mats/demo-take1/passport | 200 |
| create admin | 201 |
| POST .../passport/write `{"pin":"1234","note":"test"}` (first try) | **502 `{"error":"This mat has no calibration yet, so there is nothing to save"}`** |
| same POST after restarting the server | 200, `version: 2`, 353 bytes; `show` then lists `custom v2 by Admin ... (test)` |
| `passport_tool.py fetch demo-take1 custom backup.smp` | wrote 342 bytes (moved to `backup.smp`) |
| `factory ... --service-key wrong` | refused, exit 1: `error: the mat refused it: this needs the service key (or this slot is protected)` |
| `factory ... --service-key sesame` | `factory written`, exit 0; `show` lists `factory v1 by passport_tool` |
| GET /api/mats/demo-take1/log | `passport written` (Admin, custom v2) and `passport adopted` (by system, slot custom) |

About the 502: with the order in the task, the demo mat has already announced itself before the fake passport device is up. The server logged "mat connected" but no "passport adopted", and `GET .../profile` returned `profile: null, version: 0`, so the write had no calibration to save. This matches the zero-touch step of the test plan (restart the server with no profile for the mat; the log then shows "passport adopted"). I did exactly that: stopped the server, started it again on the same data dir, and got `passport adopted` and a `profiles\demo-take1.json` in the temp data dir. After that the write worked. So whether the 502 is a bug or just the expected state of a mat with a passport but no calibration is for you to judge. The plan's step 6 hides this because the desktop app has already sent a calibration for that mat by then (guess).

`factory` was given the profile `demo-take1.json` from the temp data dir, because the repo's `profiles\` folder is empty.

After the run I stopped all four tools plus both server instances; `netstat` shows nothing LISTENING on 1883 or 8000. No traceback in any D log.

### E. Imports
- `.venv\Scripts\python -c "import gui.desktop"`: `import ok`, exit 0.
- `.venv\Scripts\python main.py --help`: **no output, no exit within 60 s**. `main.py` only knows `--selftest` and `--server`; `--help` starts the Tk app. My `timeout 60` ended it. I checked afterwards: no leftover main.py process. Log: `step_e.txt`.

## 4. Changes I made

None of these touch files tracked by git or your data.

1. **Nothing installed.** pip reported every requirement already satisfied.
2. **`config.py` not touched** (it is older than the example, see section 1).
3. **`--data-dir` in steps C and D.** Instead of the default data dir (the `Raspberry Pi\` folder, which holds your real `smartmat.db`, `settings.json`), I started the server with `--data-dir` in my scratchpad: `C:\Users\evenm\AppData\Local\Temp\claude\c--Users-evenm-Projects-Hardware-SmartMat\86dd1f0c-dbb7-4c9d-8b33-dc36ecb76c06\scratchpad\datadir_c` and `...\datadir_d`. Reason: the test creates an admin with PIN 1234 and a nurse; I did not want them in your real database. This differs from the literal commands in the task. The folders are still there.
4. **MQTT environment variables in step D** (shell only, nothing saved): `SMARTMAT_MQTT_HOST=127.0.0.1`, `SMARTMAT_MQTT_PORT=1883`, `SMARTMAT_MQTT_USER=`, `SMARTMAT_MQTT_PASSWORD=`. Reason: `config.py` says `broker_host = 192.168.1.50`, so the server and the tools would not have found the throw-away broker on localhost. These are the same variables `e2e_check.py` uses itself.
5. **Files written outside the run's own logs:** the scratch scripts `stepc.py`, `stepc_b.py`, `srv.pid` in the scratchpad folder; `Raspberry Pi\backup.smp` (output of `fetch`), which I moved to `backup.smp`. (``, `report.md` are also new files in the repo root.)
6. **Processes I killed:** only my own: the e2e broker, `publish_demo_mat.py`, `fake_passport_device.py`, the server (twice restarted), and the `main.py` I started for `--help` (killed by `timeout`). One PowerShell filter of mine also matched and killed two of my own `bash.exe` wrapper shells; nothing else.
7. `git pull`: nothing to pull at the time.
8. No git commit, no push, no edit of any tracked file by me.

## 5. Not run - needs a human
- Step 5 (desktop app): everything except the import check: Load demo recording, all tabs, Simple/Advanced, light/dark, Tools > Expression, record + CSV, snapshot export, pop-out, Engineering > Connection > SmartMat server (Test, Send calibration, Get from server, Server log), Compare, Preview on a recording, Send analysis settings, Get analysis settings, Save/Load preset.
- Step 6, desktop part: Engineering > Connection > Passport on the mat (Show, Save current to mat, Use custom), and the Web part (gear > Analyse > passport section, Lagre dagens oppsett, Bruk). I did the command-line part and the REST part only.
- Step 4 click-through in a browser (dashboard, language/theme, device toolbar, settings dialog, users dialog, nurse acknowledge). Only the REST side was checked (step C).
- Step 7: packaging (`build_exe.bat`, `dist\SmartMat\SmartMat.exe --selftest`).
- Phone app tests (`npm ci; npm test; npm run typecheck`) and everything with hardware (Maxrays/ESP32, Pi, mDNS, real push).
- The 3 tests skipped for "Tk display unavailable" (run 2 had one, the isolated file run had two) are in effect desktop tests that did not run.

## 6. Anything odd

- **Someone committed during my run.** `git log` at the end shows, on top of `66c71aa`: `83014cb` "Add system_info.md ..." (Claude, 13:14 UTC; docs only, apparently pulled in by something other than my `git pull`, which said up to date at 21:0x), and two commits `ab6fc55` (21:15:44) and `3ab8f2a` (21:16:52), both "test" by "even eple". Those two commits **contain my `` files** (`config_diff.txt`, `e2e.txt`, `e2e_start.txt`, `pytest.txt`, `pytest_rerun_rs.txt`). I did not create them. As a result `*` is tracked, and `e2e.txt` now shows as modified (`M`) because I finished writing it after the commit. Whoever does this (you, another session, a hook) is running git in the same working tree at the same time as the test pass. Nothing was pushed by me; I don't know if those were.
- **Flaky unit test** (section 3A), and the Tk skip count varies between runs (3, 2, 3) on a normal desktop session.
- **A traceback printed to stderr during pytest** (`ConnectionAbortedError` in `tests\test_server_client.py` test HTTP handler) in run 2; the run still counted it as nothing. A similar stderr block was in run 1.
- **`main.py --help` opens the app** instead of printing help (no argparse).
- **`recordings\` folder mtime changed** at 21:10:18 (during the second pytest run) although `test_1789113735.json` there is unchanged (dated 2026-09-11). So a test writes and removes something there (guess). `settings.json` (18:03) and `smartmat.db*` (21:01, before my first test) were not changed by the runs; `profiles\` untouched.
- The e2e `server.log` is deleted by the tool after the run, so I could not attach it. 
- The stale `config.py` makes any tool that is not told otherwise look for a broker at 192.168.1.50.
- A PowerShell quirk: `fc` is an alias for `Format-Custom`, so the plan's `fc config.py config.example.py` fails in PowerShell. Use `fc.exe`.
- Unrelated Python processes were running all the time (VoiceForge: `voiceforge.py serve` x2, `voiceforge.py read ...`, `audiobook.py`). They are not mine and I left them alone. They use neither port 1883 nor 8000.
- Windows Firewall: no prompt appeared or at least none was visible to me.
