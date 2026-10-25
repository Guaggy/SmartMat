import type {
  Alert, AlertAction, AlertResult, DeviceSettings, Health, LogEvent, MatDetail, MatTimeline, Overview, Theme,
} from "./types";

/** Why a request failed, for a message that helps: "timeout" (no answer in time), "network" (could not connect at all:
 *  wrong address or port, server off, VPN off, or iOS blocking plain http), "http" (the server answered with an error),
 *  "notSmartMat" (something answered but it is not a SmartMat server, e.g. the wrong port). */
export type ApiErrorKind = "timeout" | "network" | "http" | "notSmartMat";

export class ApiError extends Error {
  // status 0 = no answer from the server (offline, wrong address, timeout)
  constructor(public status: number, message: string, public kind: ApiErrorKind = status === 0 ? "network" : "http") {
    super(message);
  }
}

export const DEFAULT_PORT = 8000;

/** What people type for the server -> "http://host:8000". Accepts a Tailscale 100.x address, a MagicDNS name
 *  ("smartmat-pi", "pi.tail1234.ts.net"), a LAN address or a full URL. A bare host gets the server's port 8000; a path or
 *  query after the host is dropped. "" when there is nothing usable. */
export function normalizeUrl(input: string): string {
  const trimmed = input.trim();
  if (!trimmed || /\s/.test(trimmed)) return "";
  const m = /^(?:(https?):\/\/)?([^/?#\s]+)/i.exec(trimmed);
  if (!m) return "";
  const scheme = (m[1] ?? "http").toLowerCase();
  let host = m[2];
  if (!/:\d+$/.test(host) && !m[1]) host = `${host}:${DEFAULT_PORT}`; // a bare host: the SmartMat server's own port
  return `${scheme}://${host}`;
}

export function createApi(baseUrl: string, timeoutMs = 8000, fetchImpl: typeof fetch = fetch) {
  async function request<T>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let response: Response;
    try {
      response = await fetchImpl(`${baseUrl}${path}`, {
        method,
        headers: body === undefined ? undefined : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (e) {
      const aborted = (e as { name?: string } | null)?.name === "AbortError";
      throw new ApiError(0, aborted ? "timeout" : "no contact with the server", aborted ? "timeout" : "network");
    } finally {
      clearTimeout(timer);
    }
    let data: unknown = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }
    if (!response.ok) {
      const message = (data as { error?: string } | null)?.error ?? `HTTP ${response.status}`;
      throw new ApiError(response.status, message);
    }
    return data as T;
  }

  const mat = (id: string) => `/api/mats/${encodeURIComponent(id)}`;
  return {
    health: async () => {
      const health = await request<Health | null>("GET", "/api/health");
      if (!health || health.ok !== true || typeof health.version !== "string") throw new ApiError(200, "not a SmartMat server", "notSmartMat");
      return health;
    },
    overview: () => request<Overview>("GET", "/api/overview"),
    mat: (id: string) => request<MatDetail>("GET", mat(id)),
    timeline: (id: string, hours = 1) => request<MatTimeline>("GET", `${mat(id)}/timeline?hours=${hours}`),
    log: (id: string) => request<{ id: string; events: LogEvent[] }>("GET", `${mat(id)}/log`),
    alerts: () => request<{ alerts: Alert[] }>("GET", "/api/alerts"),
    theme: () => request<Theme>("GET", "/api/theme"),
    // The PIN goes in the body and is used once; it is never stored by the app.
    handleAlert: (id: string, action: AlertAction, pin: string) =>
      request<AlertResult>("POST", `/api/alerts/${encodeURIComponent(id)}/${action}`, { pin }),
    // Push registration. The PIN proves a staff member allows this phone to get alerts; it is not stored.
    registerDevice: (token: string, platform: "android" | "ios", pin: string, settings: DeviceSettings) =>
      request<{ ok: boolean; user: string }>("POST", "/api/devices", { expo_push_token: token, platform, pin, ...settings }),
    updateDevice: (token: string, settings: DeviceSettings) =>
      request<{ ok: boolean }>("PUT", `/api/devices/${encodeURIComponent(token)}`, settings),
    unregisterDevice: (token: string) => request<{ ok: boolean }>("DELETE", `/api/devices/${encodeURIComponent(token)}`),
  };
}

export type Api = ReturnType<typeof createApi>;
