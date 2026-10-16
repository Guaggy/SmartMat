import { Stack } from "expo-router";
import { Platform } from "react-native";
import { StatusBar } from "expo-status-bar";

import { NotificationRouter } from "../NotificationRouter";
import "../push"; // installs the notification handler
import { AppProvider } from "../state";
import { colors } from "../theme";

export default function RootLayout() {
  return (
    <AppProvider>
      <StatusBar style="light" />
      {Platform.OS !== "web" ? <NotificationRouter /> : null /* the hook is native-only */}
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }} />
    </AppProvider>
  );
}
