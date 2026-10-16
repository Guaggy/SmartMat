import { Redirect, Tabs, usePathname } from "expo-router";

import { useApp } from "../../state";
import { colors } from "../../theme";

export default function TabsLayout() {
  const { ready, settings, t } = useApp();
  const pathname = usePathname();
  // First run: send the user to Settings once (not again while already there, or it would loop)
  if (ready && !settings.serverUrl && pathname !== "/settings") return <Redirect href="/settings" />;
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.panel },
        headerTintColor: colors.ink,
        tabBarStyle: { backgroundColor: colors.panel, borderTopColor: colors.line },
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.muted,
        tabBarIcon: () => null,
        tabBarLabelStyle: { fontSize: 15, fontWeight: "600" },
        tabBarIconStyle: { display: "none" },
      }}
    >
      <Tabs.Screen name="index" options={{ title: t("overview") }} />
      <Tabs.Screen name="alerts" options={{ title: t("alerts") }} />
      <Tabs.Screen name="settings" options={{ title: t("settings") }} />
    </Tabs>
  );
}
