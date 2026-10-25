import { StyleSheet, Text, View } from "react-native";

import { useApp } from "../state";
import { formatDuration } from "../strings";
import { asRisk, colors, riskColor } from "../theme";
import type { OverviewRow } from "../types";
import { RiskPill } from "./RiskPill";

export function MatRow({ row }: { row: OverviewRow }) {
  const { t, settings } = useApp();
  const risk = row.online ? asRisk(row.risk) : "offline";
  const place = [row.room && `${row.room}`, row.seat].filter(Boolean).join(" · ");

  let status: string;
  if (!row.online) status = t("offlineNoData");
  else if (row.posture === "none") status = t("statusNone", { t: formatDuration(row.time_in_position_s ?? 0, settings.lang) });
  else status = `${t(`p_${row.posture}` as "p_left")} · ${t("timeInPos", { t: formatDuration(row.time_in_position_s ?? 0, settings.lang) })}`;

  const badge = row.open_alerts === 1 ? t("alertBadge", { n: 1 }) : t("alertBadgePlural", { n: row.open_alerts });
  return (
    <View style={[styles.row, { borderLeftColor: riskColor[risk] }]}>
      <View style={styles.top}>
        <View style={styles.title}>
          <Text style={styles.name}>{row.name}</Text>
          {place ? <Text style={styles.place}>{place}</Text> : null}
        </View>
        <RiskPill risk={risk} />
      </View>
      <Text style={styles.status}>{status}</Text>
      {row.online && typeof row.since_movement_s === "number" ? (
        <Text style={styles.status}>{t("sinceMovementShort", { t: formatDuration(row.since_movement_s, settings.lang) })}</Text>
      ) : null}
      {row.open_alerts > 0 ? <Text style={styles.alert}>● {badge}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { backgroundColor: colors.panel, borderRadius: 10, borderLeftWidth: 6, padding: 14, marginBottom: 10 },
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { flex: 1, marginRight: 8 },
  name: { color: colors.ink, fontSize: 18, fontWeight: "700" },
  place: { color: colors.muted, fontSize: 13, marginTop: 2 },
  status: { color: colors.muted, fontSize: 14, marginTop: 8 },
  alert: { color: colors.bad, fontSize: 14, fontWeight: "600", marginTop: 6 },
});
