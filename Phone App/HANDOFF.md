# SmartMat mobile app — handoff

You are helping Even build a small iOS + Android app that is a **notification and status client** for the SmartMat pressure-sensing mat. Build it in this folder (`Phone App/`) of the SmartMat repo, on branch `phone-app`. Make the decisions below yourself unless marked OPEN; ask Even only about OPEN items.

## Working in this repo
- Work ONLY inside `Phone App/` on branch `phone-app`. Another agent keeps changing the rest of the repo on `main` (server, firmware, desktop app); never edit those folders from this branch.
- The server code is in `Raspberry Pi/server/` (read it for exact JSON shapes: `app.py`, `alerts.py`, `store.py`, `static/`). Server changes the app needs go in `Phone App/server-patch/` as patch files or documented diffs, and Even or the other agent applies them on `main`.
- `main` moves: run `git fetch origin && git merge origin/main` at the start of each session so you read the current server. Resolve conflicts (there should be none outside `Phone App/`).
- Commit small, push to `phone-app`. Do not push to or open PRs against `main` unless Even asks.
- Never commit secrets (push tokens, PINs, EAS credentials); keep `.env*` ignored.

## What SmartMat is
A pressure-sensing mat (seat cushion / bed mat) that shows pressure as a heatmap for care staff or teaching. Hardware: an ESP32 reads the mat and publishes frames over MQTT to a broker. A Python server (on a Raspberry Pi or a PC) subscribes, computes pressure-time exposure, hotspots, movement and custom risk indices, and raises alerts. It already has a REST API and a web dashboard. Even is a student and works alone with a small team; he cannot test with real hardware in every session.

**Framing rule (hard constraint):** SmartMat is an engineering / teaching tool, not a clinically validated medical device. In the UI and copy use "pressure", "pressure-time exposure", "risk level (indicative)". Never write "ulcer probability", "diagnosis", or any validated-risk claim.

## Decision: how the app gets data
**Do not use MQTT in the phone app.** Reasons: iOS suspends background sockets, so an MQTT subscription cannot deliver alerts when the app is closed; the broker would have to be exposed to the internet; the phone would need raw frames it does not need.

**Use the existing server's REST API for state, and OS push notifications for alerts.**
- Server already decides when to alert (`server/alerts.py`: a mat is "high risk" or "offline" for 30 s, which opens an alert that stays open until the condition clears; alerts can be acknowledged or ignored).
- The app polls the REST API while open (every 5 s) and receives push notifications while closed.
- Push: **Expo Push Service** (one API for APNs and FCM), via React Native + Expo. The server sends a push when an alert is raised.

## Stack
- **React Native + Expo (TypeScript)**, one codebase for iOS and Android, Expo Router, `expo-notifications`, `expo-secure-store`.
- Build/distribute with **EAS Build** (cloud builds, no Mac needed). Android: APK/internal track. iOS: TestFlight needs an Apple Developer account (99 USD/yr) — OPEN whether Even has one; until then target Android + Expo Go on iOS (Expo Go cannot receive remote push on recent SDKs, so say so in the README).
- No state library: React state + one `api.ts` fetch wrapper. No UI kit beyond React Native's own components.

## Server API (already exists; this is the contract the app must use)
Base URL is user-configurable in the app (e.g. `http://192.168.1.50:8000` or a tunnel / Tailscale address).

| Method + path | Returns |
|---|---|
| `GET /api/health` | `{ok, time, mats, version, needs_admin}` — use as connection test |
| `GET /api/overview` | `{mats: [row...], open_alerts: n, server_time}` — rows sorted worst-first |
| `GET /api/mats/<chip_id>` | row fields + `snapshot` (detail, may be null before first frame) + `age_s` + `stale` |
| `GET /api/mats/<chip_id>/timeline?hours=1` | `{segments, markers}` — risk over time, max 24 h-ish |
| `GET /api/mats/<chip_id>/log` | `{id, events}` |
| `GET /api/alerts` | `{alerts: [{id, chip_id, kind: "high_risk"\|"offline", state, t_raised, t_cleared?, name, room}]}` |
| `POST /api/alerts/<alert_id>/<action>` | acknowledge / ignore; **PIN in JSON body** (`{name, pin, ...}`) |
| `GET/POST /api/users` | staff list / add user (first user must be admin) |

Read the exact JSON shapes from `Raspberry Pi/server/app.py` and the web dashboard's mock API in `Raspberry Pi/server/static/`; keep TypeScript types from the table above and keep them in one `types.ts` so they are cheap to fix. **Build against a local mock server first** (a 40-line Node/Express or a JSON fixture with `msw`) so the app runs without the real server or any hardware.

### Server changes needed (small, do these as patch files in `Phone App/server-patch/`; the server folder is owned by the other agent on `main`)
1. `POST /api/devices` body `{expo_push_token, platform, name}` -> store in the SQLite store (`store.py`).
2. In the server tick, when `AlertManager.update()` returns `("raised", alert)`, send one Expo push (`https://exp.host/--/api/v2/push/send`) to all registered devices: title = mat name/room, body = "High pressure risk (indicative)" or "Mat offline". Include `alert_id` in `data` so tapping opens the alert.
3. `DELETE /api/devices/<token>` on logout.
Write these as a patch that can be applied cleanly on `main`.

## Screens (keep it small)
1. **Setup** — server URL, test with `/api/health`, staff name + PIN stored in SecureStore. Request notification permission here, register push token.
2. **Overview** — list of mats worst-first: name/room, risk colour + text (not colour only), online/offline, age of last data, open-alert badge. Pull to refresh.
3. **Mat detail** — current risk, small heatmap (16x15 or 20x20 grid drawn with `react-native-svg`, colour ramp from `/api/theme`), key numbers (peak, contact area, time since last movement if present in snapshot), 1-hour risk timeline.
4. **Alerts** — open alerts first, then recent history; Acknowledge / Ignore with PIN confirmation.
5. **Settings** — server URL, user, notification toggle, quiet hours (local only), about/version, framing disclaimer.

**Out of scope for now:** raw MQTT, recordings, calibration, custom-index editing, ROI tools, user admin (use the web dashboard). Add only if Even asks.

## Notifications behaviour
- One push per raised alert, none for "cleared" (optionally a silent update).
- Android: notification channel `alerts` with high importance. iOS: time-sensitive interruption level is OPEN (needs entitlement).
- Tapping a push opens that alert / mat.
- Do not put patient identifiers in the push text; use mat name/room only.

## Security
- Alert actions need the PIN the server already checks. Never log or persist the PIN outside SecureStore.
- Server speaks plain HTTP on a LAN today. For off-LAN use it needs HTTPS (Cloudflare named tunnel) or Tailscale — OPEN, Even has not chosen. The app must allow `http://` for LAN use (Android cleartext + iOS ATS exception, document both).

## Deliverables, in order
1. Skeleton in `Phone App/`: Expo TS app, `README.md` (how to run, how to build with EAS), `CLAUDE.md` (short: stack, framing rule, API contract pointer), `.gitignore`.
2. Mock server + app screens 1-2 working end to end against it.
3. Screens 3-5.
4. Push: client registration + `server-patch/` for the server side + a test script that sends a push to a token.
5. EAS config (`eas.json`) for Android internal build.
Commit after each step with a clear message. Keep dependencies minimal and justify any addition in the README.

## OPEN items for Even
- Apple Developer account? (iOS push + TestFlight)
- How will the phone reach the server outside the LAN: Tailscale, Cloudflare tunnel, or LAN only?
- Product/company name shown in the app: "SmartMat" by Verdian Medical, or SM Solutions (unresolved in the main project).
- Language: Norwegian, English, or both (default: English strings in one `strings.ts` so Norwegian is easy to add).
