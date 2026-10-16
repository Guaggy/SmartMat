import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

export const CHANNEL = "alerts";

export type PushOutcome =
  | { ok: true; token: string }
  | { ok: false; reason: "denied" | "noProject" | "unsupported" | "error" };

// Show alerts that arrive while the app is open too. (When the phone is in quiet hours the server sends nothing.)
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

/** Asks for permission and returns this phone's Expo push token. Needs a development or release build on Android:
 *  Expo Go cannot receive remote push on Android since SDK 53. */
export async function registerForPush(): Promise<PushOutcome> {
  if (Platform.OS !== "android" && Platform.OS !== "ios") return { ok: false, reason: "unsupported" };
  try {
    if (Platform.OS === "android") {
      // The channel must exist before the permission prompt (Android 13+) and before the token is requested
      await Notifications.setNotificationChannelAsync(CHANNEL, {
        name: "Varsler / Alerts",
        importance: Notifications.AndroidImportance.HIGH,
        vibrationPattern: [0, 250, 250, 250],
      });
    }
    const existing = await Notifications.getPermissionsAsync();
    const status = existing.status === "granted" ? existing.status : (await Notifications.requestPermissionsAsync()).status;
    if (status !== "granted") return { ok: false, reason: "denied" };
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
