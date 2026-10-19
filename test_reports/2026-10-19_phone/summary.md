# Phone app test - 2026-10-19 (Windows PC + iPhone XR, Expo Go)

## Environment
| | |
|---|---|
| Commit at start | `3a59dcc` (clean tree, `git pull`: up to date) |
| Commit after pull | `0882621` (housekeeping: modules regrouped into `client/` and `matlink/`, `dist/` untracked, legacy desktop Web UI removed, `report_logs/` -> `test_reports/2026-10-19_windows/`) |
| Node / npm | v24.19.0 / 11.17.0 |
| Expo | `~54.0.37` at the start, `~57.0.30` now |
| LAN | Wi-Fi (Intel AX200) `192.168.4.112/23`, gateway `192.168.5.254`; Tailscale and Bluetooth adapters ignored. Network `New_Trinity_Residents`, classed Public. The iPhone was at `192.168.7.139` (routed, worked). |
| Firewall | Two inbound Allow rules for `C:\program files\nodejs\node.exe` (Private and Public). Nothing changed. |

## Results
| Step | SDK 54 (as found) | SDK 57 (now) |
|---|---|---|
| `npm ci` | exit 0, 289 s | exit 0 (needs `.npmrc` legacy-peer-deps) |
| `npm run typecheck` | clean | clean |
| `npm test` | 27 / 27 | 27 / 27 |
| `npx expo-doctor` | 18 / 18 | 21 / 21 |
| Mock server on LAN (`/api/overview`) | 6 mats | - |
| Metro on LAN (`/status`) | packager-status:running | packager-status:running |

## What happened
1. SDK 54 dev server started and answered on the LAN, but the phone's Expo Go is **SDK 57** and refused it. The App Store's Expo Go runs exactly one SDK (54 and 58 are both rejected). The repo's SDK 54 downgrade (`00c6029`) was based on a wrong assumption.
2. Tried SDK 57 in a throw-away copy (scratchpad), no repo files touched: typecheck, 27 tests and expo-doctor 21/21 passed (jest-expo 57 needed `@react-native/jest-preset`, installed with legacy-peer-deps).
3. The phone opened the app from the copy, but Expo logged `Maximum update depth exceeded` at `RootLayout`. With the server address pre-set in the copy it opened normally; two connections from the phone to the mock server on port 8000 were seen. The tester reported that the app works.
4. Cause is most likely the first-run `<Redirect href="/settings">` in `src/app/(tabs)/_layout.tsx` (guess, not proven; the headless reproduction needed `@testing-library/react-native`, not installed).
5. Not exercised or not logged: which endpoints the phone called (the mock server logs no requests), the raise/acknowledge/reset alert flow, push (needs a development build, not Expo Go).

## Changes made to the repo (uncommitted)
- `Phone App/package.json`, `package-lock.json`: Expo SDK 57 dependency set (`expo ~57.0.30`, react 19.2.3, react-native 0.86.3, jest-expo ~57.0.6, typescript ~6.0.3, `@react-native/jest-preset` dev dependency).
- `Phone App/.npmrc` (new): `legacy-peer-deps=true`. Without it `npm install` fails (ERESOLVE, optional `react-native-worklets` peer of `expo-modules-core`) and `npm ci` rejects the lock file.
- `Phone App/app.json`: added the `expo-status-bar` plugin (added by `expo install`).
- `Phone App/src/app/(tabs)/_layout.tsx`: the first-run redirect is now a one-time `router.replace("/settings")` in an effect instead of a rendered `<Redirect>`. **Not yet tested on the phone.**
- `Phone App/README.md`, `Phone App/CLAUDE.md`, `README.md`: SDK 54 text changed to SDK 57.
- `.gitignore` (the user's own edit): `.calude/` typo changed to `.claude/`.
- `Phone App/tsconfig.json`: Expo rewrote it on start; restored with `git checkout`.
- `Phone App/node_modules` deleted and reinstalled several times (not tracked).

Nothing was committed or pushed by me. Processes started by me (mock server, Expo SDK 54 and 57) were stopped by process id; ports 8000 and 8081 are free.

## Checks after the pull (commit `0882621` + the changes above)
- Raspberry Pi unit tests: 535 passed, 3 skipped (2 x "Tk display unavailable", 1 missing Maxrays fixture), 0 failed, 2m17s (`pytest_after_pull.txt`).
- Phone App: strict `npm ci` exit 0, typecheck clean, 27 / 27 tests, expo-doctor 21 / 21.
- Logs moved from `Logs/phone_test_logs/` to this folder. `Logs/report_logs/` (yours) still exists and duplicates `test_reports/2026-10-19_windows/`; I left it.

## For tomorrow
- Phone: restart `npm run mock` and `npx expo start --lan` **from `Phone App/`** (the repo now has the fix), reload Expo Go with no server address saved, and check that it lands on Settings once without the red error. Then raise / acknowledge (PIN 1234) / reset an alert.
- Pi and desktop test as planned (see `test_reports/2026-10-19_windows/report.md` for the Windows findings).
