# SmartMat phone app

Notification and status client for the SmartMat pressure mat. Full brief: `HANDOFF.md` (note: the API table there
differs from the real server in places; the real code in `Raspberry Pi/server/` wins).

- **Stack:** React Native + Expo SDK 57 (TypeScript; the App Store's Expo Go runs exactly one SDK and on 2026-10-19 it was 57, so the project must match it for iPhone testing; `.npmrc` sets legacy-peer-deps because of an optional react-native-worklets peer conflict), Expo Router (`src/app/`), `expo-notifications`,
  `expo-secure-store`. Add packages with `npx expo install`, never `npm install <pkg>`.
- **Data:** REST polling of the SmartMat server; alerts reach the phone as in-app banner + local notification (works in Expo Go), Expo push (development build only; never call `getExpoPushTokenAsync` in Expo Go, see `src/env.ts`) and ntfy (server side, `Raspberry Pi/server/push.py`). No MQTT in the app.
- **API contract:** `src/types.ts` mirrors `Raspberry Pi/server/app.py` and `Raspberry Pi/design/api-contract.md` (checked against main at af4f8c4; the mock server must keep the same keys). Fix types there, not in screens.
- **Language:** Norwegian (`nb`) is the default, English second. All text lives in `src/strings.ts`.
- **Framing rule (hard):** SmartMat is an engineering / teaching tool, not a validated medical device. Say
  "pressure", "pressure-time exposure", "risk level (indicative)". Never "ulcer probability", "diagnosis" or a
  validated-risk claim. Push text uses mat name and room only, no patient identifiers.
- **Secrets:** never commit push tokens, PINs, EAS or Firebase credentials. The PIN is asked per action and not stored.
- **Scope:** work only in `Phone App/`. Server changes go in `Phone App/server-patch/` as patches for `main`.
- **Checks before committing:** `npm run typecheck`, `npm test`, `npx expo-doctor`.
