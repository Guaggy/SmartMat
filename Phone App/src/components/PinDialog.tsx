import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { useApp } from "../state";
import { colors } from "../theme";

interface Props {
  visible: boolean;
  title: string;
  confirmLabel: string;
  error: string | null;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (pin: string) => void;
}

// The PIN lives only in this component's state and is cleared whenever the dialog closes.
export function PinDialog({ visible, title, confirmLabel, error, busy, onCancel, onSubmit }: Props) {
  const { t } = useApp();
  const [pin, setPin] = useState("");
  useEffect(() => { if (!visible) setPin(""); }, [visible]);

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <View style={styles.backdrop}>
        <View style={styles.card}>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.hint}>{t("pinHint")}</Text>
          <TextInput
            style={styles.input}
            value={pin}
            onChangeText={(v) => setPin(v.replace(/\D/g, ""))}
            placeholder={t("pin")}
            placeholderTextColor={colors.muted}
            secureTextEntry
            keyboardType="number-pad"
            maxLength={8}
            autoFocus
            autoCorrect={false}
            autoComplete="off"
            textContentType="none"
            importantForAutofill="no"
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <View style={styles.buttons}>
            <Pressable style={[styles.button, styles.cancel]} onPress={onCancel} disabled={busy}>
              <Text style={styles.cancelText}>{t("cancel")}</Text>
            </Pressable>
            <Pressable
              style={[styles.button, styles.confirm, (!pin || busy) && styles.disabled]}
              onPress={() => onSubmit(pin)}
              disabled={!pin || busy}
            >
              {busy ? <ActivityIndicator color={colors.onAccent} /> : <Text style={styles.confirmText}>{confirmLabel}</Text>}
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "center", padding: 24 },
  card: { backgroundColor: colors.panel, borderRadius: 12, padding: 18, borderWidth: 1, borderColor: colors.line },
  title: { color: colors.ink, fontSize: 18, fontWeight: "700" },
  hint: { color: colors.muted, fontSize: 13, marginTop: 4, marginBottom: 12 },
  input: { backgroundColor: colors.bg, color: colors.ink, borderRadius: 8, borderWidth: 1, borderColor: colors.line, padding: 12, fontSize: 20, letterSpacing: 4 },
  error: { color: colors.bad, fontSize: 14, marginTop: 8 },
  buttons: { flexDirection: "row", gap: 10, marginTop: 16 },
  button: { flex: 1, borderRadius: 8, paddingVertical: 12, alignItems: "center", borderWidth: 1 },
  cancel: { borderColor: colors.line },
  cancelText: { color: colors.ink, fontSize: 15, fontWeight: "600" },
  confirm: { backgroundColor: colors.accent, borderColor: colors.accent },
  confirmText: { color: colors.onAccent, fontSize: 15, fontWeight: "700" },
  disabled: { opacity: 0.4 },
});
