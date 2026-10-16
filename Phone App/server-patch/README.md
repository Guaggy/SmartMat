# Server patch for the phone app (push notifications)

`0001-push-devices-and-notifications.patch` adds, to `Raspberry Pi/server/`:

- a `devices` table in `store.py` (Expo push token, platform, language, time zone, quiet window, who registered it),
- `POST /api/devices` (needs a PIN in the body), `PUT /api/devices/<token>` and `DELETE /api/devices/<token>` (no PIN: the
  push token is the secret of the phone), in `app.py`,
- `server/push.py`: builds the push text (Norwegian or English, mat name + room only), skips phones in their quiet hours,
  sends to the Expo push service in a background thread and removes phones Expo reports as `DeviceNotRegistered`,
- a call in `Server.tick` (`__main__.py`): one push per alert that is *raised*, none when it clears,
- `PUSH_ENABLED` / `PUSH_ACCESS_TOKEN` in `config.example.py`, `tzdata` for Windows in `requirements.txt`,
- `tests/test_server_push.py` (18 tests).

Made against `main` at `af4f8c4`. It touches nothing outside `Raspberry Pi/`.

## Apply (from the repository root, on `main` or a branch off it)

```bash
git apply --check "Phone App/server-patch/0001-push-devices-and-notifications.patch"
git apply "Phone App/server-patch/0001-push-devices-and-notifications.patch"
cd "Raspberry Pi"
pip install -r requirements.txt       # Windows only: adds tzdata
python -m pytest tests/test_server_push.py
```

Then restart the server. Add the new lines from `config.example.py` to your own `config.py` if you want to change them (the
defaults work: push enabled, no access token). The server must be able to reach `https://exp.host`.

If `main` has moved and `git apply --check` fails, merge `main` into your branch first, or ask for the patch to be regenerated.

## What was checked

- The new tests pass, and so do the 33 existing server tests (`test_server_app`, `test_server_engine`, `test_server_runner`).
  The other test files cannot be collected where `tkinter` is missing, which has nothing to do with this patch.
- The patch applies cleanly to a fresh checkout of `main` and the tests pass there.
- End to end: the real `Server.tick` with a real alert, the real Flask app for registering two phones, and the real HTTP request
  to a local fake Expo endpoint. One request, correct text, the unregistered phone removed. A real push to a real phone has
  **not** been tried (it needs your Expo and Firebase accounts).

## Security notes

- Registering needs a valid PIN (otherwise anyone on the network could subscribe to the alerts). Wrong PINs count towards the
  server's existing lock-out.
- The push token is never written to the event log; the log says only who registered a device.
- Anyone who learns a phone's push token could send it fake pushes through Expo unless you set `PUSH_ACCESS_TOKEN`
  (Expo "enhanced push security") in `config.py` and in the Expo dashboard.
- Alerts are held in memory: after a server restart an open alert is raised again with a new id and pushed again.
