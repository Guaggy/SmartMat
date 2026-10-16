import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";

import { AppProvider } from "../state";
import { colors } from "../theme";

export default function RootLayout() {
  return (
    <AppProvider>
      <StatusBar style="light" />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }} />
    </AppProvider>
  );
}
