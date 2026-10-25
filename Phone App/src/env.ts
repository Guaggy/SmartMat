import Constants from "expo-constants";

/** True when the app runs inside the Expo Go app (executionEnvironment "storeClient"), not in a development or release
 *  build. Expo Go cannot receive remote push (no Expo push token), so remote push is never touched there. */
export function isExpoGoEnv(executionEnvironment: unknown, appOwnership?: unknown): boolean {
  return executionEnvironment === "storeClient" || appOwnership === "expo";
}

export function isExpoGo(): boolean {
  try {
    return isExpoGoEnv(Constants.executionEnvironment, Constants.appOwnership);
  } catch {
    return false;
  }
}
