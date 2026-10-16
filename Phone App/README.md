# SmartMat phone app

Android and iOS app (Expo / React Native, TypeScript) that shows mat status and receives alerts from the SmartMat
server. SmartMat is an engineering / teaching tool, not a validated medical device; the app says "risk level
(indicative)" and never claims a diagnosis.

Status: Setup/Settings and Overview screens work against the mock server. Mat detail, Alerts and push come next.

## Run it

```bash
cd "Phone App"
npm install
npx expo start
```

- **Android emulator (Android Studio):** create a Pixel device with a *Google Play* system image, start it, then press
  `a` in the Expo terminal. The emulator reaches your PC at `http://10.0.2.2:<port>`.
- **iPhone (no Apple membership needed):** install *Expo Go* from the App Store, put the phone on the same Wi-Fi as
  the PC and scan the QR code. This is for checking the UI. Remote push to iOS needs a paid Apple Developer account.
- **Mock server (no hardware or real server needed):** in a second terminal run `npm run mock` (port 8000, PIN `1234`).
  In the app's Settings enter `10.0.2.2:8000` on the Android emulator, or `<PC LAN IP>:8000` on a phone. It has five
  mats (offline, high, medium, low, no user) and two open alerts. `POST /__mock/reset` restores them and
  `POST /__mock/raise {"chip_id":"sm-102","kind":"high"}` raises a new one.
- **Checks:** `npm run typecheck`, `npm test`, `npx expo-doctor`.

## Build with EAS (later steps add `eas.json`)

```bash
npm i -g eas-cli
eas login
eas build --platform android --profile preview   # APK for internal testing
```

iOS builds and TestFlight need an Apple Developer Program membership (99 USD/yr); not set up yet.

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

Only what Expo Router needs plus: `expo-secure-store` (server address and language), `jest` + `jest-expo` (tests, dev only), `expo-build-properties` (allow cleartext HTTP on Android), `expo-splash-screen`
(branded splash). `react-dom` is a peer dependency of Expo Router that npm needs resolved to the SDK's version.
