// Drives the mock server from a script, to test alerts on the phone without hardware.
//   node scripts/mock-alert.mjs raise sm-102 [high|offline]   a new open alert (the app should buzz / notify within 5 s)
//   node scripts/mock-alert.mjs clear sm-102                  the condition goes away, open alerts of that mat vanish
//   node scripts/mock-alert.mjs reset                         back to the start state
// Server: MOCK_URL (default http://localhost:8000).
const base = (process.env.MOCK_URL || "http://localhost:8000").replace(/\/+$/, "");
const [command, chip, kind] = process.argv.slice(2);

const bodies = {
  raise: { chip_id: chip, kind: kind === "offline" ? "offline" : "high" },
  clear: { chip_id: chip },
  reset: {},
};
if (!bodies[command] || (command !== "reset" && !chip)) {
  console.error("usage: node scripts/mock-alert.mjs raise <chip_id> [high|offline] | clear <chip_id> | reset");
  process.exit(2);
}
try {
  const response = await fetch(`${base}/__mock/${command}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bodies[command]),
  });
  console.log(response.status, await response.text());
  process.exit(response.ok ? 0 : 1);
} catch (error) {
  console.error(`No contact with ${base}: ${error.message}`);
  process.exit(1);
}
