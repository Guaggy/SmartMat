import { StyleSheet, Text, View } from "react-native";

import { useApp } from "../state";
import { asRisk, riskColor } from "../theme";

export function RiskPill({ risk }: { risk: string }) {
  const { t } = useApp();
  const value = asRisk(risk);
  const color = riskColor[value];
  return (
    <View style={[styles.pill, { borderColor: color }, value === "offline" && styles.dashed]}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={[styles.text, { color }]}>{t(`risk_${value}`)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: { flexDirection: "row", alignItems: "center", borderWidth: 1.5, borderRadius: 14, paddingHorizontal: 10, paddingVertical: 4 },
  dashed: { borderStyle: "dashed" },
  dot: { width: 8, height: 8, borderRadius: 4, marginRight: 6 },
  text: { fontSize: 13, fontWeight: "600" },
});
