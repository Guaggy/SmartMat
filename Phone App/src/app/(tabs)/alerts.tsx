import { Link } from "expo-router";
import { useState } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { PinDialog } from "../../components/PinDialog";
import { alertErrorKey } from "../../errors";
import { useApp } from "../../state";
import { formatDuration } from "../../strings";
import { colors } from "../../theme";
import type { Alert, AlertAction } from "../../types";
import { useAlertsFeed } from "../../alertsFeed";
import { useServerNow } from "../../useServerNow";

interface Pending {
  alert: Alert;
  action: AlertAction;
}

// Open alerts first, then newest. The server lists alerts still present plus the last 30 handled ones that cleared.
const order = (a: Alert, b: Alert) => Number(b.state === "open") - Number(a.state === "open") || b.t_raised - a.t_raised;

export default function Alerts() {
  const { api, settings, t } = useApp();
  const now = useServerNow(api);
  const { alerts: list, error, refreshing, refresh } = useAlertsFeed();
  const data = list ? { alerts: list } : null;
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const alerts = [...(data?.alerts ?? [])].sort(order);

  async function submit(pin: string) {
    if (!api || !pending) return;
    setBusy(true);
    setProblem(null);
    try {
      await api.handleAlert(pending.alert.id, pending.action, pin);
      setPending(null);
      refresh();
    } catch (e) {
      setProblem(t(alertErrorKey(e)));
    }
    setBusy(false);
  }

  const askPin = (alert: Alert, action: AlertAction) => {
    setProblem(null);
    setPending({ alert, action });
  };
  const name = (alert: Alert) => alert.name ?? alert.chip_id;
  const place = (alert: Alert) => (alert.room ? ` · ${alert.room}` : "");

  return (
    <View style={styles.screen}>
      {error ? <Text style={styles.banner}>{t("lostServer")}</Text> : null}
      <FlatList
        data={alerts}
        keyExtractor={(a) => a.id}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.accent} />}
        ListEmptyComponent={<Text style={styles.empty}>{data ? t("noAlerts") : error ? "" : t("loading")}</Text>}
        renderItem={({ item }) => (
          <View style={[styles.card, item.state === "open" && styles.cardOpen]}>
            <Link href={{ pathname: "/mat/[id]", params: { id: item.chip_id } }} style={styles.name}>
              {name(item)}
              {place(item)}
            </Link>
            <Text style={styles.kind}>{t(item.kind === "offline" ? "kind_offline" : "kind_high_risk")}</Text>
            <Text style={styles.meta}>
              {t("raisedAgo", { t: formatDuration(now() - item.t_raised, settings.lang) })}
              {" · "}
              {t(`st_${item.state}`)}
              {item.by ? ` ${t("byUser", { u: item.by })}` : ""}
            </Text>
            {item.state === "open" ? (
              <View style={styles.buttons}>
                <Pressable style={[styles.button, styles.primary]} onPress={() => askPin(item, "ack")}>
                  <Text style={styles.primaryText}>{t("ack")}</Text>
                </Pressable>
                <Pressable style={[styles.button, styles.secondary]} onPress={() => askPin(item, "ignore")}>
                  <Text style={styles.secondaryText}>{t("ignore")}</Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        )}
        ListFooterComponent={<Text style={styles.disclaimer}>{t("disclaimer")}</Text>}
      />
      <PinDialog
        visible={pending !== null}
        title={pending ? t(pending.action === "ack" ? "dlgAck" : "dlgIgnore", { name: name(pending.alert) }) : ""}
        confirmLabel={pending ? t(pending.action) : ""}
        error={problem}
        busy={busy}
        onCancel={() => setPending(null)}
        onSubmit={submit}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  list: { padding: 16 },
  banner: { backgroundColor: colors.warn, color: colors.onAccent, padding: 10, fontSize: 14, fontWeight: "600" },
  empty: { color: colors.muted, fontSize: 15, textAlign: "center", marginTop: 24 },
  card: { backgroundColor: colors.panel, borderRadius: 10, padding: 14, marginBottom: 10, borderLeftWidth: 6, borderLeftColor: colors.line },
  cardOpen: { borderLeftColor: colors.bad },
  name: { color: colors.ink, fontSize: 18, fontWeight: "700" },
  kind: { color: colors.ink, fontSize: 15, marginTop: 4 },
  meta: { color: colors.muted, fontSize: 13, marginTop: 4 },
  buttons: { flexDirection: "row", gap: 10, marginTop: 12 },
  button: { flex: 1, borderRadius: 8, paddingVertical: 11, alignItems: "center", borderWidth: 1 },
  primary: { backgroundColor: colors.accent, borderColor: colors.accent },
  primaryText: { color: colors.onAccent, fontSize: 15, fontWeight: "700" },
  secondary: { borderColor: colors.line },
  secondaryText: { color: colors.ink, fontSize: 15, fontWeight: "600" },
  disclaimer: { color: colors.muted, fontSize: 12, textAlign: "center", marginTop: 16 },
});
