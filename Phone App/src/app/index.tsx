import { Image, StyleSheet, Text, View } from "react-native";

import { brand } from "../brand";
import { t } from "../strings";

export default function Index() {
  return (
    <View style={styles.screen}>
      <Image source={require("../../assets/splash-icon.png")} style={styles.logo} resizeMode="contain" />
      <Text style={styles.title}>{t("appName")}</Text>
      <Text style={styles.body}>{t("placeholder")}</Text>
      <Text style={styles.disclaimer}>{t("disclaimer")}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, backgroundColor: brand.navy },
  logo: { width: 160, height: 160 },
  title: { color: "#FFFFFF", fontSize: 28, fontWeight: "700", marginTop: 8 },
  body: { color: "#C9D3E3", fontSize: 16, marginTop: 8 },
  disclaimer: { color: "#8FA0BA", fontSize: 12, textAlign: "center", marginTop: 32 },
});
