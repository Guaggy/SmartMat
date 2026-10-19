import Constants from "expo-constants";
import { useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";

import { ApiError, createApi, normalizeUrl } from "../../api";
import { PinDialog } from "../../components/PinDialog";
import { alertErrorKey } from "../../errors";
import { platform, registerForPush, timeZone, type PushOutcome } from "../../push";
import { parseTime } from "../../quietHours";
import { useApp } from "../../state";
import type { Lang } from "../../strings";
import { colors } from "../../theme";

type Result = { ok: boolean; text: string } | null;

export default function Settings() {
  const { settings, update, t } = useApp();
  const [url, setUrl] = useState(settings.serverUrl);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>(null);
  const [from, setFrom] = useState(settings.quiet.from);
  const [to, setTo] = useState(settings.quiet.to);
  const [quietError, setQuietError] = useState(false);
  const { api } = useApp();
  const [pinOpen, setPinOpen] = useState(false);
  const [pinBusy, setPinBusy] = useState(false);
  const [pinProblem, setPinProblem] = useState<string | null>(null);
  const [pushMessage, setPushMessage] = useState<string | null>(null);
  const tokenRef = useRef<string | null>(null); // asked for once, so a mistyped PIN does not repeat the permission prompt

  useEffect(() => setUrl(settings.serverUrl), [settings.serverUrl]);

  // Save a quiet-hours time only when it is a valid HH:MM
  async function commitTime(field: "from" | "to", value: string) {
    if (parseTime(value) === null) return setQuietError(true);
    setQuietError(false);
    await update({ quiet: { ...settings.quiet, [field]: value.trim() } });
  }

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

  const failure = (reason: Extract<PushOutcome, { ok: false }>["reason"]) =>
    t(({ denied: "pushDenied", noProject: "pushNoProject", unsupported: "pushUnsupported", error: "pushError" } as const)[reason]);

  async function enablePush(pin: string) {
    if (!api) return;
    setPinBusy(true);
    setPinProblem(null);
    if (!tokenRef.current) {
      const outcome = await registerForPush();
      if (!outcome.ok) {
        setPinBusy(false);
        setPinOpen(false);
        setPushMessage(failure(outcome.reason));
        return;
      }
      tokenRef.current = outcome.token;
    }
    try {
      await api.registerDevice(tokenRef.current, platform(), pin, {
        name: Constants.deviceName ?? undefined,
        lang: settings.lang,
        tz: timeZone(),
        quiet_from: settings.quiet.enabled ? settings.quiet.from : null,
        quiet_to: settings.quiet.enabled ? settings.quiet.to : null,
      });
      await update({ push: { enabled: true, token: tokenRef.current } });
      setPinOpen(false);
      setPushMessage(t("pushActive"));
    } catch (e) {
      setPinProblem(t(alertErrorKey(e)));
    }
    setPinBusy(false);
  }

  async function disablePush() {
    const token = settings.push.token;
    if (api && token) {
      try {
        await api.unregisterDevice(token);
      } catch (e) {
        // 404: the server no longer knew this phone, which is what we wanted. No contact: stay on, so alerts keep coming.
        if (!(e instanceof ApiError && e.status === 404)) return setPushMessage(t("netErr"));
      }
    }
    tokenRef.current = null;
    await update({ push: { enabled: false, token: null } });
    setPushMessage(t("pushInactive"));
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

      <Text style={styles.label}>{t("pushTitle")}</Text>
      <View style={styles.switchRow}>
        <Text style={styles.switchLabel}>{t("pushOn")}</Text>
        <Switch
          value={settings.push.enabled}
          disabled={!api}
          onValueChange={(on) => (on ? (setPinProblem(null), setPinOpen(true)) : disablePush())}
          trackColor={{ true: colors.accent, false: colors.line }}
        />
      </View>
      {pushMessage ? <Text style={styles.hint}>{pushMessage}</Text> : null}
      {settings.push.token ? (
        <Text style={styles.hint} selectable>
          {t("pushToken")}: {settings.push.token}
        </Text>
      ) : null}
      <Text style={styles.hint}>{t("pushHint")}</Text>
      <PinDialog
        visible={pinOpen}
        title={t("pushDialogTitle")}
        confirmLabel={t("pushEnable")}
        error={pinProblem}
        busy={pinBusy}
        onCancel={() => setPinOpen(false)}
        onSubmit={enablePush}
      />

      <Text style={styles.label}>{t("quietHours")}</Text>
      <View style={styles.switchRow}>
        <Text style={styles.switchLabel}>{t("quietOn")}</Text>
        <Switch
          value={settings.quiet.enabled}
          onValueChange={(enabled) => update({ quiet: { ...settings.quiet, enabled } })}
          trackColor={{ true: colors.accent, false: colors.line }}
        />
      </View>
      <View style={styles.buttons}>
        <View style={styles.timeField}>
          <Text style={styles.hint}>{t("quietFrom")}</Text>
          <TextInput style={styles.input} value={from} onChangeText={setFrom} onEndEditing={() => commitTime("from", from)} placeholder="22:00" placeholderTextColor={colors.muted} keyboardType="numbers-and-punctuation" maxLength={5} />
        </View>
        <View style={styles.timeField}>
          <Text style={styles.hint}>{t("quietTo")}</Text>
          <TextInput style={styles.input} value={to} onChangeText={setTo} onEndEditing={() => commitTime("to", to)} placeholder="07:00" placeholderTextColor={colors.muted} keyboardType="numbers-and-punctuation" maxLength={5} />
        </View>
      </View>
      {quietError ? <Text style={[styles.result, { color: colors.bad }]}>{t("quietInvalid")}</Text> : null}
      <Text style={styles.hint}>{t("quietHint")}</Text>

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
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  switchLabel: { color: colors.ink, fontSize: 15 },
  timeField: { flex: 1 },
});
