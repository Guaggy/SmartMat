#!/usr/bin/env node
// Sends one test alert push to a phone through the Expo push service, shaped like the server's real alert push
// (title = mat name, body = room + risk text, channel "alerts", data = alert id). Needs Node 18+.
//
//   node scripts/send-test-push.mjs "ExponentPushToken[xxxx]"
//   node scripts/send-test-push.mjs "ExponentPushToken[xxxx]" --kind offline --lang en --receipts
//   node scripts/send-test-push.mjs "ExponentPushToken[xxxx]" --url http://127.0.0.1:8127/push   (a fake endpoint)
//
// Get the token from the app: Settings > Push notifications, once push is on (shown under the switch).
// On the server it is also in the devices table of smartmat.db.
const args = process.argv.slice(2);
const token = args.find((a) => !a.startsWith("--") && !isValue(a));
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] && !args[i + 1].startsWith("--") ? args[i + 1] : fallback;
};
function isValue(a) {
  const i = args.indexOf(a);
  return i > 0 && args[i - 1].startsWith("--") && !["--receipts"].includes(args[i - 1]);
}

if (!token || !/^Expo(nent)?PushToken\[[A-Za-z0-9_-]{1,200}\]$/.test(token)) {
  console.error('Usage: node scripts/send-test-push.mjs "ExponentPushToken[xxxx]" [--kind high_risk|offline] [--lang nb|en] [--url URL] [--access-token T] [--receipts]');
  process.exit(2);
}

const kind = opt("kind", "high_risk") === "offline" ? "offline" : "high_risk";
const lang = opt("lang", "nb") === "en" ? "en" : "nb";
const url = opt("url", "https://exp.host/--/api/v2/push/send");
const accessToken = opt("access-token", process.env.EXPO_ACCESS_TOKEN ?? "");
const text = {
  nb: { high_risk: "Høy risiko (veiledende)", offline: "Frakoblet", room: "Rom 101" },
  en: { high_risk: "High pressure risk (indicative)", offline: "Mat offline", room: "Room 101" },
}[lang];

const message = {
  to: token,
  title: "Stol 1",
  body: `${text.room}: ${text[kind]}`,
  sound: "default",
  channelId: "alerts",
  priority: "high",
  ttl: 1800,
  data: { alert_id: "test0000test", chip_id: "sm-101", kind },
};

const headers = { "Content-Type": "application/json", Accept: "application/json" };
if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

const response = await fetch(url, { method: "POST", headers, body: JSON.stringify([message]) });
const result = await response.json().catch(() => ({}));
console.log(`HTTP ${response.status}`, JSON.stringify(result, null, 2));

const ticket = result.data?.[0];
if (!response.ok || !ticket || ticket.status !== "ok") {
  console.error("Not accepted:", ticket?.message ?? result.errors?.[0]?.message ?? "see response above");
  process.exit(1);
}
console.log("Accepted by Expo (ticket", ticket.id + "). That is not delivery: check the receipt, or look at the phone.");

if (args.includes("--receipts") && ticket.id) {
  await new Promise((resolve) => setTimeout(resolve, 5000));
  const receiptUrl = url.replace(/\/send$/, "/getReceipts");
  const r = await fetch(receiptUrl, { method: "POST", headers, body: JSON.stringify({ ids: [ticket.id] }) });
  console.log("Receipt:", JSON.stringify(await r.json().catch(() => ({})), null, 2));
}
