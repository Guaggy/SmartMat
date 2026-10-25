import "./quietLogs"; // first: hides the Expo Go warning that expo-notifications prints while loading
import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { AppState, Platform, Vibration } from "react-native";

import { isExpoGo } from "./env";

export const CHANNEL = "alerts";

export type PushOutcome =
  | { ok: true; token: string }
  | { ok: false; reason: "denied" | "noProject" | "unsupported" | "expoGo" | "error" };

// Show notifications that arrive while the app is open. Exception: a local alert notification while the app is in the
// foreground is not shown a second time, because the in-app banner (with sound/vibration) already says it.
Notifications.setNotificationHandler({
  handleNotification: async (notification) => {
    const local = (notification.request.content.data as { local?: boolean } | null)?.local === true;
    const hide = local && AppState.currentState === "active";
    return { shouldPlaySound: !hide, shouldSetBadge: false, shouldShowBanner: !hide, shouldShowList: !hide };
  },
});

async function ensureChannel() {
  if (Platform.OS !== "android") return;
  // The channel must exist before the permission prompt (Android 13+) and before a token is requested
  await Notifications.setNotificationChannelAsync(CHANNEL, {
    name: "Varsler / Alerts",
    importance: Notifications.AndroidImportance.HIGH,
    vibrationPattern: [0, 250, 250, 250],
  });
}

/** Asks for notification permission (once; iOS remembers the answer). True when local notifications can be shown. */
export async function ensureLocalPermission(): Promise<boolean> {
  try {
    await ensureChannel();
    const existing = await Notifications.getPermissionsAsync();
    if (existing.status === "granted") return true;
    return (await Notifications.requestPermissionsAsync()).status === "granted";
  } catch {
    return false;
  }
}

/** A local notification now. Works in Expo Go. Never throws. */
export async function showLocalNotification(title: string, body: string, data: Record<string, unknown> = {}) {
  try {
    await Notifications.scheduleNotificationAsync({
      content: { title, body, sound: true, data: { ...data, local: true } },
      trigger: null,
    });
  } catch {
    // no permission or no notification support: the in-app banner still shows
  }
}

/** Three short pulses (no extra dependency: React Native's own Vibration; iOS ignores the pattern and buzzes once) */
export function buzz() {
  try {
    Vibration.vibrate([0, 300, 150, 300]);
  } catch {
    // no vibration motor
  }
}

/** Asks for permission and returns this phone's Expo push token. Needs a development or release build: Expo Go cannot
 *  receive remote push (Android since SDK 53, iOS too since SDK 53+ per the Expo docs), so Expo Go never gets here. */
export async function registerForPush(): Promise<PushOutcome> {
  if (isExpoGo()) return { ok: false, reason: "expoGo" };
  if (Platform.OS !== "android" && Platform.OS !== "ios") return { ok: false, reason: "unsupported" };
  try {
    if (!(await ensureLocalPermission())) return { ok: false, reason: "denied" };
    const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
    if (!projectId) return { ok: false, reason: "noProject" }; // run `eas init` once, see README
    const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
    return { ok: true, token };
  } catch {
    return { ok: false, reason: "error" };
  }
}

export const platform = (): "android" | "ios" => (Platform.OS === "ios" ? "ios" : "android");

/** IANA time zone of the phone, for the server's quiet-hours check */
export function timeZone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
  } catch {
    return undefined;
  }
}
