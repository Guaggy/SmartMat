import { StyleSheet, Text, View } from "react-native";
import Svg, { Line, Rect } from "react-native-svg";

import { useApp } from "../state";
import { colors, riskColor } from "../theme";
import { layoutTimeline, markerX } from "../timeline";
import type { MatTimeline } from "../types";

const HEIGHT = 28;

export function Timeline({ data, now, hours = 1, width }: { data: MatTimeline; now: number; hours?: number; width: number }) {
  const { t } = useApp();
  const bars = layoutTimeline(data.segments, now, hours, width);
  return (
    <View>
      <Text style={styles.title}>{t("tlTitle")}</Text>
      <Svg width={width} height={HEIGHT}>
        <Rect x={0} y={0} width={width} height={HEIGHT} rx={4} fill={colors.panel} stroke={colors.line} />
        {bars.map((b, i) => (
          <Rect key={i} x={b.x} y={2} width={b.w} height={HEIGHT - 4} fill={riskColor[b.risk]} />
        ))}
        {data.markers.map((m, i) => {
          const x = markerX(m.t, now, hours, width);
          return x === null ? null : <Line key={`m${i}`} x1={x} x2={x} y1={0} y2={HEIGHT} stroke="#FFFFFF" strokeWidth={3} />;
        })}
      </Svg>
      <View style={styles.legend}>
        {(["high", "medium", "low", "none"] as const).map((risk) => (
          <View key={risk} style={styles.legendItem}>
            <View style={[styles.swatch, { backgroundColor: riskColor[risk] }]} />
            <Text style={styles.legendText}>{t(`risk_${risk}`)}</Text>
          </View>
        ))}
        <View style={styles.legendItem}>
          <View style={[styles.swatch, styles.noData]} />
          <Text style={styles.legendText}>{t("lgNoData")}</Text>
        </View>
        <View style={styles.legendItem}>
          <View style={[styles.swatch, styles.handled]} />
          <Text style={styles.legendText}>{t("lgHandled")}</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  title: { color: colors.ink, fontSize: 15, fontWeight: "600", marginBottom: 6 },
  legend: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 6 },
  legendItem: { flexDirection: "row", alignItems: "center" },
  swatch: { width: 10, height: 10, marginRight: 4, borderRadius: 2 },
  noData: { borderWidth: 1, borderColor: colors.muted },
  handled: { width: 3, height: 12, backgroundColor: "#FFFFFF", borderRadius: 0 },
  legendText: { color: colors.muted, fontSize: 12 },
});
