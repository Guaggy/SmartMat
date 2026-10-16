import { Stack, useLocalSearchParams } from "expo-router";
import { ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";

import { Heatmap } from "../../components/Heatmap";
import { RiskPill } from "../../components/RiskPill";
import { Timeline } from "../../components/Timeline";
import { peakValue } from "../../heatmap";
import { useApp } from "../../state";
import { formatDuration } from "../../strings";
import { colors } from "../../theme";
import { usePoll } from "../../usePoll";
import { useStops } from "../../useStops";

export default function MatDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { api, settings, t } = useApp();
  const { width } = useWindowDimensions();
  const stops = useStops(api);
  const { data, error } = usePoll(api && id ? () => api.mat(id) : null, `${settings.serverUrl}/${id}`, 3000);
  const mapWidth = Math.min(width - 32, 420);
  const dur = (s: number | null) => (s === null ? "–" : formatDuration(s, settings.lang));

  const snap = data?.snapshot;
  const offline = snap ? !snap.online : false;
  const relative = snap?.unit === "relative";
  const peak = snap ? peakValue(snap) : null;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Stack.Screen
        options={{
          headerShown: true,
          title: data?.name ?? "",
          headerStyle: { backgroundColor: colors.panel },
          headerTintColor: colors.ink,
        }}
      />
      {error ? <Text style={styles.banner}>{error.message === "unknown mat" ? t("noMats") : t("lostServer")}</Text> : null}
      {!data ? (
        <Text style={styles.muted}>{error ? "" : t("loading")}</Text>
      ) : (
        <>
          <View style={styles.header}>
            <Text style={styles.muted}>{[data.room, data.seat, data.unit].filter(Boolean).join(" · ")}</Text>
            <RiskPill risk={snap!.online ? snap!.risk : "offline"} />
          </View>
          <Text style={styles.note}>{t("riskNote")}</Text>

          {offline ? <Text style={styles.warn}>{t("offlineMat")}</Text> : null}
          {snap!.occupied === false ? <Text style={styles.muted}>{t("unoccupied")}</Text> : null}
          {relative ? <Text style={styles.warn}>{t("uncal")}</Text> : null}
          {snap!.saturated_cells > 0 ? <Text style={styles.warn}>{t("saturation", { n: snap!.saturated_cells })}</Text> : null}

          <Text style={styles.section}>{t("pressureMap")}</Text>
          {snap!.grid ? (
            <>
              <Heatmap grid={snap!.grid} scaleMax={snap!.scale_max ?? 50} stops={stops} hotspots={snap!.hotspots} dimmed={offline} width={mapWidth} />
              <Text style={styles.note}>{relative ? t("mapScaleRel") : t("mapScale", { n: snap!.scale_max ?? 50 })}</Text>
            </>
          ) : (
            <Text style={styles.muted}>{t("noGrid")}</Text>
          )}

          <View style={styles.numbers}>
            <Stat label={relative ? t("highestRelative") : t("highestPressure")} value={peak === null ? "–" : relative ? peak.toFixed(1) : `${peak.toFixed(0)} kPa`} />
            <Stat label={t("timeInPosLabel")} value={dur(snap!.time_in_position_s)} />
            <Stat label={t("sinceRelief")} value={dur(snap!.since_relief_s)} />
            <Stat label={t("hotspots")} value={String(snap!.hotspots?.length ?? 0)} />
          </View>

          {snap!.indices?.length ? (
            <>
              <Text style={styles.section}>{t("indices")}</Text>
              {snap!.indices.map((index) => (
                <View key={index.name} style={styles.indexRow}>
                  <Text style={styles.indexName}>{index.name}</Text>
                  <Text style={[styles.indexState, index.state === "over" && { color: colors.bad }, index.state === "near" && { color: colors.warn }]}>
                    {index.value === null ? "–" : index.value} · {t(`idx_${index.state}`)}
                  </Text>
                </View>
              ))}
            </>
          ) : null}

          <View style={styles.timeline}>
            <Timeline segments={data.timeline} now={Date.now() / 1000} width={mapWidth} />
          </View>
          <Text style={styles.disclaimer}>{t("disclaimer")}</Text>
        </>
      )}
    </ScrollView>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: 16, paddingBottom: 40 },
  banner: { backgroundColor: colors.warn, color: colors.onAccent, padding: 10, fontSize: 14, fontWeight: "600", marginBottom: 12 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  muted: { color: colors.muted, fontSize: 14, marginTop: 2 },
  note: { color: colors.muted, fontSize: 12, marginTop: 6 },
  warn: { color: colors.warn, fontSize: 14, marginTop: 8 },
  section: { color: colors.ink, fontSize: 16, fontWeight: "700", marginTop: 20, marginBottom: 8 },
  numbers: { flexDirection: "row", flexWrap: "wrap", marginTop: 16, gap: 10 },
  stat: { backgroundColor: colors.panel, borderRadius: 8, padding: 12, minWidth: "46%", flexGrow: 1 },
  statValue: { color: colors.ink, fontSize: 20, fontWeight: "700" },
  statLabel: { color: colors.muted, fontSize: 12, marginTop: 2 },
  indexRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.line },
  indexName: { color: colors.ink, fontSize: 14, flex: 1, marginRight: 8 },
  indexState: { color: colors.muted, fontSize: 14 },
  timeline: { marginTop: 20 },
  disclaimer: { color: colors.muted, fontSize: 12, textAlign: "center", marginTop: 24 },
});
