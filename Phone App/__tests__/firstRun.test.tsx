import { renderRouter, screen, waitFor } from "expo-router/testing-library";
import { Text } from "react-native";

import TabsLayout from "../src/app/(tabs)/_layout";
import { AppProvider } from "../src/state";

// SecureStore holds nothing: a first run with no server address saved.
jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(async () => null),
  setItemAsync: jest.fn(async () => undefined),
}));

// Renders the REAL tabs layout inside a router. If the first-run redirect ever re-triggers itself, React throws
// "Maximum update depth exceeded" and this test fails (that was the red error seen in Expo Go on 2026-10-19).
describe("first run redirect", () => {
  it("lands on Settings once, without a render loop", async () => {
    const errors = jest.spyOn(console, "error").mockImplementation(() => undefined);
    renderRouter(
      {
        "(tabs)/_layout": () => (
          <AppProvider>
            <TabsLayout />
          </AppProvider>
        ),
        "(tabs)/index": () => <Text>OVERVIEW SCREEN</Text>,
        "(tabs)/alerts": () => <Text>ALERTS SCREEN</Text>,
        "(tabs)/settings": () => <Text>SETTINGS SCREEN</Text>,
      },
      { initialUrl: "/" },
    );
    await waitFor(() => expect(screen.getByText("SETTINGS SCREEN")).toBeTruthy());
    expect(screen.queryByText("OVERVIEW SCREEN")).toBeNull();
    const depth = errors.mock.calls.filter((call) => String(call[0]).includes("Maximum update depth"));
    expect(depth).toEqual([]);
    errors.mockRestore();
  });
});
