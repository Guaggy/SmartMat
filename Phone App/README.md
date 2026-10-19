# SmartMat phone app

Android and iOS app (Expo / React Native, TypeScript) that shows mat status and receives alerts from the SmartMat
server. SmartMat is an engineering / teaching tool, not a validated medical device; the app says "risk level
(indicative)" and never claims a diagnosis.

Status: all five screens work against the mock server and the real server's JSON shapes. Push: the app side and the server patch are written and tested against fake endpoints; a real push to a phone still needs the one-time setup below. Android builds are configured in `eas.json` (untested without an Expo login).

## Run it

```bash
cd "Phone App"
npm ci
npx expo start
```

- **Android emulator (Android Studio):** create a Pixel device with a *Google Play* system image, start it, then press
  `a` in the Expo terminal. The emulator reaches your PC at `http://10.0.2.2:<port>`.
- **iPhone (no Apple membership needed):** install *Expo Go* from the App Store, put the phone on the same Wi-Fi as
  the PC and scan the QR code. The project is on **Expo SDK 54** on purpose: the App Store's Expo Go stops at SDK 54, and a newer project
  gives "Project is incompatible with this version of Expo Go" (https://docs.expo.dev/troubleshooting/expo-go-version-mismatch/). This is for checking the UI. Remote push to iOS needs a paid Apple Developer account.
- **Mock server (no hardware or real server needed):** in a second terminal run `npm run mock` (port 8000, PIN `1234`).
  In the app's Settings enter `10.0.2.2:8000` on the Android emulator, or `<PC LAN IP>:8000` on a phone. It has six
  mats (never sent a frame, offline with an old picture, high, medium, low, no user), two open alerts and one handled one. `POST /__mock/reset` restores them and
  `POST /__mock/raise {"chip_id":"sm-102","kind":"high"}` raises a new one.
- **Checks:** `npm run typecheck`, `npm test`, `npx expo-doctor`.

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

**Needs a development or release build.** The Expo docs say push is unavailable in Expo Go on Android since SDK 53. They
do not say that about iOS, but I have not tested Expo Go on iOS, and an iOS build with push needs a paid Apple
Developer account. Local notifications are not used.

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

Server-side settings are in `config.py`: `PUSH_ENABLED`, `PUSH_ACCESS_TOKEN` (optional Expo access token so only your server
can push to your phones).

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

Only what Expo Router needs plus: `expo-secure-store` (server address, language, quiet hours), `react-native-svg` (heatmap and timeline), `jest` + `jest-expo` (tests, dev only), `expo-build-properties` (allow cleartext HTTP on Android), `expo-splash-screen`
(branded splash), `expo-notifications` (push), `expo-dev-client` (development builds, which push needs on Android), `expo-system-ui` (makes the dark style apply on Android). `react-dom` is a peer dependency of Expo Router that npm needs resolved to the SDK's version.
