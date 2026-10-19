import { Tabs, useRouter } from "expo-router";
import { useEffect, useRef } from "react";

import { useApp } from "../../state";
import { colors } from "../../theme";

export default function TabsLayout() {
  const { ready, settings, t } = useApp();
  const router = useRouter();
  const sent = useRef(false);
  // First run: send the user to Settings once. (A <Redirect> rendered while pathname !== "/settings" looped with
  // "Maximum update depth exceeded" on Expo SDK 57.)
  useEffect(() => {
    if (!ready || settings.serverUrl || sent.current) return;
    sent.current = true;
    router.replace("/settings");
  }, [ready, settings.serverUrl, router]);
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
