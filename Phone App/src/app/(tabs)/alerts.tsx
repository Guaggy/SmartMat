import { StyleSheet, Text, View } from "react-native";

import { useApp } from "../../state";
import { colors } from "../../theme";

export default function Alerts() {
  const { t } = useApp();
  return (
    <View style={styles.screen}>
      <Text style={styles.text}>{t("placeholder")}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg },
  text: { color: colors.muted, fontSize: 16 },
});
