import { LogBox } from "react-native";

import { isExpoGo } from "./env";

// Expo Go on iOS prints a one-line yellow warning when expo-notifications loads ("remote notifications were removed from
// Expo Go"). The app never uses remote push there (see push.ts), so the warning is only noise. Must be imported before
// expo-notifications.
if (isExpoGo()) LogBox.ignoreLogs(["expo-notifications:", "[expo-notifications]"]);
