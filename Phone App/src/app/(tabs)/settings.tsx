import Constants from "expo-constants";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { createApi, normalizeUrl } from "../../api";
import { useApp } from "../../state";
import type { Lang } from "../../strings";
import { colors } from "../../theme";

type Result = { ok: boolean; text: string } | null;

export default function Settings() {
  const { settings, update, t } = useApp();
  const [url, setUrl] = useState(settings.serverUrl);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>(null);

  useEffect(() => setUrl(settings.serverUrl), [settings.serverUrl]);

  async function test() {
    const address = normalizeUrl(url);
    if (!address) return;
    setBusy(true);
    setResult(null);
    try {
      const health = await createApi(address, 5000).health();
      setResult({ ok: true, text: t("connectedOk", { n: health.mats, v: health.version }) });
    } catch {
      setResult({ ok: false, text: t("connectionFailed") });
    }
    setBusy(false);
  }

  async function save() {
    const address = normalizeUrl(url);
    setUrl(address);
    await update({ serverUrl: address });
    setResult({ ok: true, text: t("saved") });
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      {!settings.serverUrl ? (
        <>
          <Text style={styles.heading}>{t("setupTitle")}</Text>
          <Text style={styles.hint}>{t("setupHint")}</Text>
        </>
      ) : null}

      <Text style={styles.label}>{t("serverUrl")}</Text>
      <TextInput
        style={styles.input}
        value={url}
        onChangeText={setUrl}
        placeholder="192.168.1.50:8000"
        placeholderTextColor={colors.muted}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
      />
      <View style={styles.buttons}>
        <Button label={busy ? t("testing") : t("testConnection")} onPress={test} disabled={busy || !url.trim()} secondary />
        <Button label={t("save")} onPress={save} disabled={!url.trim()} />
      </View>
      {result ? <Text style={[styles.result, { color: result.ok ? colors.ok : colors.bad }]}>{result.text}</Text> : null}

      <Text style={styles.label}>{t("language")}</Text>
      <View style={styles.buttons}>
        {(["nb", "en"] as Lang[]).map((lang) => (
          <Button
            key={lang}
            label={lang === "nb" ? "Norsk" : "English"}
            onPress={() => update({ lang })}
            secondary={settings.lang !== lang}
          />
        ))}
      </View>

      <Text style={styles.label}>{t("about")}</Text>
      <Text style={styles.hint}>
        {t("appName")} · {t("version", { v: Constants.expoConfig?.version ?? "" })}
      </Text>
      <Text style={styles.hint}>{t("disclaimer")}</Text>
    </ScrollView>
  );
}

function Button({ label, onPress, disabled, secondary }: { label: string; onPress: () => void; disabled?: boolean; secondary?: boolean }) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={[styles.button, secondary ? styles.buttonSecondary : styles.buttonPrimary, disabled && styles.disabled]}
    >
      <Text style={[styles.buttonText, secondary && styles.buttonTextSecondary]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: 16 },
  heading: { color: colors.ink, fontSize: 22, fontWeight: "700", marginBottom: 6 },
  hint: { color: colors.muted, fontSize: 14, marginBottom: 8 },
  label: { color: colors.ink, fontSize: 15, fontWeight: "600", marginTop: 18, marginBottom: 6 },
  input: { backgroundColor: colors.panel, color: colors.ink, borderRadius: 8, borderWidth: 1, borderColor: colors.line, padding: 12, fontSize: 16 },
  buttons: { flexDirection: "row", gap: 10, marginTop: 10 },
  button: { flex: 1, borderRadius: 8, paddingVertical: 12, alignItems: "center", borderWidth: 1 },
  buttonPrimary: { backgroundColor: colors.accent, borderColor: colors.accent },
  buttonSecondary: { backgroundColor: "transparent", borderColor: colors.line },
  buttonText: { color: colors.onAccent, fontSize: 15, fontWeight: "700" },
  buttonTextSecondary: { color: colors.ink },
  disabled: { opacity: 0.4 },
  result: { fontSize: 14, marginTop: 10 },
});
