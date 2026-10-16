import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";

import { brand } from "../brand";

export default function RootLayout() {
  return (
    <>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: brand.navy },
          headerTintColor: "#FFFFFF",
          contentStyle: { backgroundColor: brand.navy },
        }}
      />
    </>
  );
}
