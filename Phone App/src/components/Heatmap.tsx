import { StyleSheet, Text, View } from "react-native";
import Svg, { Rect } from "react-native-svg";

import { cellColor, type Stops } from "../heatmap";
import { useApp } from "../state";
import { colors } from "../theme";
import type { Hotspot } from "../types";

const MAP_BACKGROUND = "#0A101D"; // hm_bg of the dark palette

interface Props {
  grid: (number | null)[][];
  scaleMax: number;
  stops: Stops;
  hotspots?: Hotspot[];
  dimmed?: boolean; // stale or offline: draw the old picture faded
  width: number;
}

// Row 0 is the back of the seat, the last row the front (labelled below the map).
export function Heatmap({ grid, scaleMax, stops, hotspots = [], dimmed, width }: Props) {
  const { t } = useApp();
  const rows = grid.length;
  const cols = grid[0]?.length ?? 0;
  if (!rows || !cols) return null;
  const cell = width / cols;
  return (
    <View>
      <Svg width={width} height={cell * rows} opacity={dimmed ? 0.35 : 1}>
        <Rect x={0} y={0} width={width} height={cell * rows} fill={MAP_BACKGROUND} />
        {grid.map((row, r) =>
          row.map((value, c) => (
            <Rect
              key={`${r}-${c}`}
              x={c * cell}
              y={r * cell}
              width={cell + 0.5}
              height={cell + 0.5}
              fill={cellColor(value, scaleMax, stops, MAP_BACKGROUND)}
            />
          )),
        )}
        <Rect x={0.5} y={0.5} width={width - 1} height={cell * rows - 1} fill="none" stroke={colors.line} strokeWidth={1} />
        {hotspots.map((h) => {
          const rs = h.cells.map((p) => p[0]);
          const cs = h.cells.map((p) => p[1]);
          const [r0, r1, c0, c1] = [Math.min(...rs), Math.max(...rs), Math.min(...cs), Math.max(...cs)];
          return (
            <Rect
              key={h.id}
              x={c0 * cell}
              y={r0 * cell}
              width={(c1 - c0 + 1) * cell}
              height={(r1 - r0 + 1) * cell}
              fill="none"
              stroke="#FFFFFF"
              strokeWidth={h.persistent ? 3 : 1.5}
              strokeDasharray="5,4"
            />
          );
        })}
      </Svg>
      <Text style={styles.front}>{t("front")}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  front: { color: colors.muted, fontSize: 12, textAlign: "center", marginTop: 4 },
});
