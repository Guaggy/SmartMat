import { Stack } from "expo-router";
import { Platform, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";

import { AlertsFeedProvider } from "../alertsFeed";
import { AlertBanner } from "../components/AlertBanner";
import { NotificationRouter } from "../NotificationRouter";
import "../push"; // installs the notification handler
import { AppProvider } from "../state";
import { colors } from "../theme";

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <AppProvider>
        <AlertsFeedProvider>
          <StatusBar style="light" />
          {Platform.OS !== "web" ? <NotificationRouter /> : null /* the hook is native-only */}
          <View style={{ flex: 1, backgroundColor: colors.bg }}>
            <AlertBanner />
            <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }} />
          </View>
        </AlertsFeedProvider>
      </AppProvider>
    </SafeAreaProvider>
  );
}
