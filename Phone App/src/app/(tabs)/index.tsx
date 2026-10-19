import { Link } from "expo-router";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { MatRow } from "../../components/MatRow";
import { useApp } from "../../state";
import { colors } from "../../theme";
import { usePoll } from "../../usePoll";

export default function Overview() {
  const { api, settings, t } = useApp();
  const { data, error, refreshing, refresh } = usePoll(api ? () => api.overview() : null, settings.serverUrl);

  return (
    <View style={styles.screen}>
      {error ? <Text style={styles.banner}>{t("lostServer")}</Text> : null}
      <FlatList
        data={data?.mats ?? []}
        keyExtractor={(row) => row.id}
        renderItem={({ item }) => (
          <Link href={{ pathname: "/mat/[id]", params: { id: item.id } }} asChild>
            <Pressable>
              <MatRow row={item} />
            </Pressable>
          </Link>
        )}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.accent} />}
        ListEmptyComponent={
          <Text style={styles.empty}>{data ? t("noMats") : error ? "" : t("loading")}</Text>
        }
        ListFooterComponent={<Text style={styles.disclaimer}>{t("disclaimer")}</Text>}
      />
      {!api ? (
        <Link href="/settings" style={styles.empty}>
          {t("goToSettings")}
        </Link>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  list: { padding: 16 },
  banner: { backgroundColor: colors.warn, color: colors.onAccent, padding: 10, fontSize: 14, fontWeight: "600" },
  empty: { color: colors.muted, fontSize: 15, textAlign: "center", marginTop: 24 },
  disclaimer: { color: colors.muted, fontSize: 12, textAlign: "center", marginTop: 16 },
});
