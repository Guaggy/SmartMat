# SmartMat phone app

Android and iOS app (Expo / React Native, TypeScript) that shows mat status and receives alerts from the SmartMat
server. SmartMat is an engineering / teaching tool, not a validated medical device; the app says "risk level
(indicative)" and never claims a diagnosis.

Status: all five screens work against the mock server and the real server's JSON shapes. It runs in Expo Go on an iPhone with in-app alerts, plus ntfy for alerts while the app is closed (next section). Expo push: the app side and the server patch are written and tested against fake endpoints; a real push still needs a development build. Android builds are configured in `eas.json` (untested without an Expo login).

## Run it

```bash
cd "Phone App"
npm ci
npx expo start
```

- **Android emulator (Android Studio):** create a Pixel device with a *Google Play* system image, start it, then press
  `a` in the Expo terminal. The emulator reaches your PC at `http://10.0.2.2:<port>`.
- **iPhone (no Apple membership needed):** install *Expo Go* from the App Store, put the phone on the same Wi-Fi as
  the PC and scan the QR code. The project is on **Expo SDK 57** on purpose: the App Store's Expo Go runs exactly one SDK, and on 2026-10-19 that was 57
  (SDK 54 and 58 both gave "Project is incompatible with this version of Expo Go", https://docs.expo.dev/troubleshooting/expo-go-version-mismatch/).
  When the App Store's Expo Go moves on, the project must move with it (`npx expo install expo@sdk-NN --fix`, then `npm run typecheck`, `npm test`, `npm run doctor`). Remote push to iOS needs a paid Apple Developer account and a development build; Expo Go gets alerts through the app itself and ntfy (see "Test on an iPhone in Expo Go").
- **Mock server (no hardware or real server needed):** in a second terminal run `npm run mock` (port 8000, PIN `1234`).
  In the app's Settings enter `10.0.2.2:8000` on the Android emulator, or `<PC LAN IP>:8000` on a phone. It has six
  mats (never sent a frame, offline with an old picture, high, medium, low, no user), two open alerts and one handled one. `POST /__mock/reset` restores them and
  `POST /__mock/raise {"chip_id":"sm-102","kind":"high"}` raises a new one.
- **Checks:** `npm run typecheck`, `npm test`, `npx expo-doctor`.

## Test on an iPhone in Expo Go, over Tailscale (no Apple Developer account)

What you need: the iPhone with the *Expo Go* app (App Store) and *Tailscale*, the SmartMat server (or the mock server) on a
machine that is also on your tailnet, and a PC with Node 22 for the Expo dev server.

1. On the server machine find its Tailscale address: `tailscale ip -4` (a `100.x.y.z`) or its MagicDNS name from the
   Tailscale admin page (e.g. `smartmat-pi` or `smartmat-pi.tail1234.ts.net`). The server listens on port 8000.
2. Start the server (`python -m server` on the Pi) or, to try the app without hardware, `npm run mock` in `Phone App/` on the PC.
3. On the PC: `npm ci` (once), then `npx expo start`. If the phone cannot see the PC on Wi-Fi, use `npx expo start --tunnel` or
   run Tailscale on the PC too and open the `exp://100.x.y.z:8081` address in Expo Go.
4. Scan the QR code with the iPhone camera, open in Expo Go. The app opens on **Settings** once (first run).
5. Server address: type `100.x.y.z` or the MagicDNS name (port 8000 and `http://` are added if you leave them out), tap
   **Test connection**, then **Save**. Plain `http://` is fine: the app allows it. If the test fails the message says
   whether it timed out (server off or Tailscale off on the phone), could not connect (wrong address or port), or
   answered but is not SmartMat (wrong port).
6. Leave *Alerts in the app* on and allow notifications when iOS asks.
7. Try an alert: with the mock, `npm run mock:alert -- raise sm-102` (or `... raise sm-102 offline`). Within 5 s a red banner
   appears at the top with Acknowledge / Ignore / Later, the phone vibrates and a local notification is sent. Acknowledge
   asks for the PIN (`1234` on the mock). `npm run mock:alert -- clear sm-102` makes the condition go away,
   `... reset` restores the start state. The mock prints every request (method, path, status) so you can see what the phone calls.

### What works in Expo Go and what needs a development build

| | Expo Go (free, no Apple account) | Development / release build (Apple Developer Program, 99 USD/yr, for iOS) |
|---|---|---|
| All five screens, heatmap, timeline, PIN confirm, quiet hours, language | yes | yes |
| Alerts while the app is open | yes: red banner, vibration, local notification | yes |
| Alerts for a short while after you put the app away | partly: the app keeps polling only as long as iOS keeps it running (seconds to a few minutes) | partly, same |
| Alerts while the app is closed | **only through ntfy** (below) | Expo push (Settings > Push notifications) and/or ntfy |
| Expo push token, `getExpoPushTokenAsync` | never called in Expo Go (detected through `Constants.executionEnvironment`); the push switch is replaced by an explanation | yes, after the setup in "Push notifications" |
| Time-sensitive / critical alerts, custom sounds | no | later, with the right entitlements |

### Alerts when the app is closed: ntfy (free, works with Expo Go)

[ntfy](https://ntfy.sh) is a small open push service with a free iOS app. The SmartMat server publishes each raised alert to
a topic and the ntfy app on the iPhone shows it as a normal notification, with the app closed or the phone locked.
It carries the same text as the Expo push: the mat name and room and "High pressure risk (indicative)" or "Mat offline".
No patient identifiers, ever.

1. Install **ntfy** from the App Store (free) on the iPhone.
2. Pick an **unguessable topic name**, e.g. `smartmat-` plus 10 or more random characters (`smartmat-k3j9x2q7vb`). On the public
   relay `ntfy.sh` anyone who knows the topic name can read and publish to it: the topic *is* the password. Do not use a
   name like `smartmat` or a room name. Only letters, digits, `_` and `-` are allowed.
3. In ntfy tap **+** and subscribe to the topic on the default server `ntfy.sh` (or on your own server, see below). Allow notifications.
4. In the server's `config.py` set (the lines are in `config.example.py`):
   ```python
   PUSH_ENABLED = True
   NTFY_ENABLED = True
   NTFY_TOPIC = "smartmat-k3j9x2q7vb"
   NTFY_CLICK_URL = "http://100.x.y.z:8000"   # optional: tapping the notification opens the dashboard
   ```
   and restart the server. The Pi needs internet access to `ntfy.sh`. Test without waiting for an alert:
   `curl -d "test from SmartMat" ntfy.sh/smartmat-k3j9x2q7vb`.
5. Optional: your own ntfy server (`NTFY_URL = "http://100.x.y.z:8080"`, and in the iOS app *Use another server*). iOS only wakes the
   ntfy app reliably through Apple's push, which a self-hosted server reaches only with `upstream-base-url: https://ntfy.sh`
   in its config (that relays just a wake-up, not the text). `NTFY_TOKEN` is for a protected topic on your own server.
6. Quiet hours: ntfy has none. Use an iOS Focus mode. Setting `NTFY_ENABLED = False` (or `PUSH_ENABLED = False`, which switches
   all push off) turns the channel off. A `config.py` without the `NTFY_*` lines simply has ntfy off. If ntfy is unreachable the
   server logs one line and carries on; it never delays its tick.

## Build with EAS

```bash
npm i -g eas-cli
eas login
eas init                                          # once: adds extra.eas.projectId to app.json (commit it)
eas build --platform android --profile development   # dev build: use with `npx expo start`, needed for push
eas build --platform android --profile preview       # APK for internal testing, no dev tools
```

`eas.json` profiles (Android only for now):

- `development`: dev client (`expo-dev-client`), internal distribution, APK. Installs on the emulator and on phones.
- `preview`: release-like APK for testers; install by opening the build's link or dragging the APK onto the emulator.
- `production`: store build (AAB), version auto-incremented. Not needed yet.

There are no iOS profiles yet because they need a paid Apple Developer Program membership (99 USD/yr). When you have one, add
`ios` settings per profile and run `eas credentials`; no app code changes are needed.

`eas.json` was written from the EAS docs and checked as JSON, but not run through EAS CLI (that needs your login).

Local alternative to cloud builds (needs the Android SDK, as installed with Android Studio, and a JDK): `npx expo run:android`.

## Push notifications

How it works: the server sends one push per raised alert (not for cleared ones) through the Expo push service. The text
is the mat name and room only. A phone registers with a staff PIN (Settings > Push notifications), which the server
checks but the app never stores. Quiet hours are kept by the **server** (it sends nothing to a phone in its quiet
window), because a push that arrives while the app is closed cannot be held back by the app.

**Needs a development or release build.** Expo Go cannot receive remote push on current SDKs, so in Expo Go the app never asks for a push token and Settings explains why. An iOS build with push also needs a paid Apple Developer account. Local notifications (alerts while the app runs) are separate and do work in Expo Go.

One-time setup (Android):

1. `eas login`, then in `Phone App/` run `eas init`. It adds `extra.eas.projectId` to `app.json`; commit that change.
   Without it the app says "Push is not set up in this build".
2. Firebase: create a project at console.firebase.google.com and add an Android app with package `com.smartmat.mobile`.
   Download `google-services.json` into `Phone App/` (commit it: it only holds public ids) and add
   `"googleServicesFile": "./google-services.json"` under `expo.android` in `app.json`.
3. Firebase > Project settings > Service accounts > *Generate new private key*. Upload it to EAS with `eas credentials`
   (Android > production > Google Service Account > FCM V1). Never commit this file.
4. Build a development build and install it on the emulator or a phone:
   `eas build --profile development --platform android` (or locally `npx expo run:android`), then `npx expo start`.
5. On the server: apply `server-patch/` (see `server-patch/README.md`) and restart it. The server needs internet access to
   `exp.host`.
6. In the app: Settings > turn on *Push-varsler*, enter your PIN. The token is shown under the switch.
7. Send a test: `node scripts/send-test-push.mjs "ExponentPushToken[...]" --receipts`. Or raise a real alert; with the
   mock server there is no Expo service, so use the script.

Tapping a push opens the Alerts tab. Android channel: `alerts` (high importance).

Server-side settings are in `config.py`: `PUSH_ENABLED` (master switch for Expo push and ntfy), `PUSH_ACCESS_TOKEN` (optional Expo access token so only your server
can push to your phones), and the `NTFY_*` block described above.

## Mock server and tests

`npm test` runs the unit tests, including the API client against the mock server. The mock's JSON keys were diffed against the
real server running in demo mode.

## Plain HTTP on the LAN

The server speaks plain HTTP today, so the app allows it:

- **Android:** cleartext traffic is enabled through `expo-build-properties` in `app.json`.
- **iOS:** App Transport Security is relaxed (`NSAllowsArbitraryLoads`) in `app.json`. Tighten this before an App
  Store release.

For use outside the LAN, put the server behind HTTPS (Cloudflare tunnel) or Tailscale.

## Language

Norwegian (nb) is the default; English is available. All text is in `src/strings.ts`.

## Icons

`scripts/make-icons.py` builds the icons from `Raspberry Pi/branding_source/Logo.jpg`. That sheet is only 600 px per
tile, so the 1024 px icon is upscaled and slightly soft; swap in exported brand PNGs when available.

## Dependencies

Only what Expo Router needs plus: `expo-secure-store` (server address, language, quiet hours), `react-native-svg` (heatmap and timeline), `jest` + `jest-expo` + `@testing-library/react-native` (tests, dev only; the latter renders the real tabs layout in a router to guard the first-run redirect against a render loop; v13 because v14 needs a renderer package Expo SDK 57 does not ship), `expo-build-properties` (allow cleartext HTTP on Android), `expo-splash-screen`
(branded splash), `expo-notifications` (push), `expo-dev-client` (development builds, which push needs on Android), `expo-system-ui` (makes the dark style apply on Android). `react-dom` is a peer dependency of Expo Router that npm needs resolved to the SDK's version.

No haptics library: new-alert vibration uses React Native's built-in `Vibration` (iOS buzzes once, Android follows the pattern), which avoids a dependency for a single call. `expo-notifications` also serves the local notifications in Expo Go.
