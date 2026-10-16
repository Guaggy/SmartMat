/** "22:30" -> minutes after midnight, or null when it is not a valid HH:MM */
export function parseTime(text: string): number | null {
  const m = /^([01]?\d|2[0-3]):([0-5]\d)$/.exec(text.trim());
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

/** True when `date` falls in the quiet window [from, to). The window may wrap past midnight (22:00 to 07:00). */
export function isQuiet(date: Date, from: string, to: string): boolean {
  const a = parseTime(from);
  const b = parseTime(to);
  if (a === null || b === null || a === b) return false;
  const now = date.getHours() * 60 + date.getMinutes();
  return a < b ? now >= a && now < b : now >= a || now < b;
}
