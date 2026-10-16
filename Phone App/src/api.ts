import type {
  Alert, AlertAction, AlertResult, Health, LogEvent, MatDetail, MatTimeline, Overview, Theme,
} from "./types";

export class ApiError extends Error {
  // status 0 = no answer from the server (offline, wrong address, timeout)
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** "192.168.1.50:8000/" -> "http://192.168.1.50:8000" */
export function normalizeUrl(input: string): string {
  const trimmed = input.trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  return /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;
}

export function createApi(baseUrl: string, timeoutMs = 8000, fetchImpl: typeof fetch = fetch) {
  async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
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
    } catch {
      throw new ApiError(0, "no contact with the server");
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
    health: () => request<Health>("GET", "/api/health"),
    overview: () => request<Overview>("GET", "/api/overview"),
    mat: (id: string) => request<MatDetail>("GET", mat(id)),
    timeline: (id: string, hours = 1) => request<MatTimeline>("GET", `${mat(id)}/timeline?hours=${hours}`),
    log: (id: string) => request<{ id: string; events: LogEvent[] }>("GET", `${mat(id)}/log`),
    alerts: () => request<{ alerts: Alert[] }>("GET", "/api/alerts"),
    theme: () => request<Theme>("GET", "/api/theme"),
    // The PIN goes in the body and is used once; it is never stored by the app.
    handleAlert: (id: string, action: AlertAction, pin: string) =>
      request<AlertResult>("POST", `/api/alerts/${encodeURIComponent(id)}/${action}`, { pin }),
  };
}

export type Api = ReturnType<typeof createApi>;
