import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { bannerAlert } from "../alertWatch";
import { useAlertsFeed } from "../alertsFeed";
import { alertErrorKey } from "../errors";
import { useApp } from "../state";
import { colors } from "../theme";
import type { AlertAction } from "../types";
import { PinDialog } from "./PinDialog";

/** Red strip at the top of every screen while an alert is open: mat, what happened, Acknowledge / Ignore (PIN) / Later.
 *  "Later" only hides it in this session; the alert stays open on the server and in the Alerts tab. */
export function AlertBanner() {
  const { api, t } = useApp();
  const { alerts, hidden, hide, refresh } = useAlertsFeed();
  const insets = useSafeAreaInsets();
  const [action, setAction] = useState<AlertAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const { alert, more } = bannerAlert(alerts ?? [], hidden);
  if (!alert) return null;
  const name = alert.name ?? alert.chip_id;
  const place = alert.room ? ` · ${alert.room}` : "";

  async function submit(pin: string) {
    if (!api || !alert || !action) return;
    setBusy(true);
    setProblem(null);
    try {
      await api.handleAlert(alert.id, action, pin);
      setAction(null);
      refresh();
    } catch (e) {
      setProblem(t(alertErrorKey(e)));
    }
    setBusy(false);
  }

  return (
    <View style={[styles.wrap, { paddingTop: insets.top + 8 }]} accessibilityRole="alert" testID="alert-banner">
      <Text style={styles.title}>
        {name}
        {place}
      </Text>
      <Text style={styles.text}>
        {t(alert.kind === "offline" ? "kind_offline" : "kind_high_risk")}
        {more > 0 ? ` · ${t("bannerMore", { n: more })}` : ""}
      </Text>
      <View style={styles.buttons}>
        <Pressable style={[styles.button, styles.primary]} onPress={() => { setProblem(null); setAction("ack"); }}>
          <Text style={styles.primaryText}>{t("ack")}</Text>
        </Pressable>
        <Pressable style={styles.button} onPress={() => { setProblem(null); setAction("ignore"); }}>
          <Text style={styles.buttonText}>{t("ignore")}</Text>
        </Pressable>
        <Pressable style={styles.button} onPress={() => hide(alert.id)}>
          <Text style={styles.buttonText}>{t("later")}</Text>
        </Pressable>
      </View>
      <PinDialog
        visible={action !== null}
        title={action ? t(action === "ack" ? "dlgAck" : "dlgIgnore", { name }) : ""}
        confirmLabel={action ? t(action) : ""}
        error={problem}
        busy={busy}
        onCancel={() => setAction(null)}
        onSubmit={submit}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: "#7A1F1A", paddingHorizontal: 16, paddingBottom: 10 },
  title: { color: "#FFFFFF", fontSize: 17, fontWeight: "700" },
  text: { color: "#FFE3E0", fontSize: 14, marginTop: 2 },
  buttons: { flexDirection: "row", gap: 8, marginTop: 10 },
  button: { flex: 1, borderRadius: 8, borderWidth: 1, borderColor: "#FFB4AB", paddingVertical: 9, alignItems: "center" },
  buttonText: { color: "#FFFFFF", fontSize: 14, fontWeight: "600" },
  primary: { backgroundColor: "#FFFFFF", borderColor: "#FFFFFF" },
  primaryText: { color: "#7A1F1A", fontSize: 14, fontWeight: "700" },
});
