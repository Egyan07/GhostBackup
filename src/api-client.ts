/**
 * api-client.ts — GhostBackup API Client
 *
 * Thin wrapper around fetch that adds the X-API-Key header to every request.
 * The token is fetched once from Electron IPC on the first call and cached
 * for the lifetime of the session.
 */

import type {
  DashboardData,
  HealthData,
  RunStatus,
  RunSummary,
  LogEntry,
  BackupConfig,
  RestoreResult,
  AlertData,
  WatcherStatus,
  SsdStorage,
  DrillStatus,
  VerifyResult,
} from "./types";

const DEFAULT_BASE_URL = "http://127.0.0.1:8765";

let _cachedToken: string | null = null;
let _cachedBaseUrl: string | null = null;

type HttpMethod = "GET" | "POST" | "PATCH" | "DELETE";

async function _getBaseUrl(): Promise<string> {
  if (_cachedBaseUrl !== null) return _cachedBaseUrl;

  if (window.ghostbackup?.apiUrl) {
    try {
      _cachedBaseUrl = await window.ghostbackup.apiUrl();
    } catch {
      _cachedBaseUrl = DEFAULT_BASE_URL;
    }
  } else {
    _cachedBaseUrl = DEFAULT_BASE_URL;
  }

  return _cachedBaseUrl;
}

async function _getToken(): Promise<string> {
  if (_cachedToken !== null) return _cachedToken;

  if (window.ghostbackup?.getApiToken) {
    try {
      _cachedToken = await window.ghostbackup.getApiToken();
    } catch {
      _cachedToken = "";
    }
  } else {
    // Browser dev mode without Electron — token not required
    _cachedToken = "";
  }
  return _cachedToken;
}

/** Reset cached Electron-derived values (used in tests or after re-authentication). */
export function clearTokenCache(): void {
  _cachedToken = null;
  _cachedBaseUrl = null;
}

export class ApiError extends Error {
  status: number;
  code: string | null;
  fix: string | null;

  constructor(
    status: number,
    message: string,
    code: string | null = null,
    fix: string | null = null
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fix = fix;
  }
}

/**
 * Core request wrapper.
 */
export async function request(
  method: HttpMethod,
  path: string,
  body?: unknown,
  params?: Record<string, unknown>
): Promise<unknown> {
  const [token, baseUrl] = await Promise.all([_getToken(), _getBaseUrl()]);

  let url = baseUrl + path;
  if (params) {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v != null)
        .map(([k, v]) => [k, String(v)])
    );
    if (qs.toString()) url += "?" + qs.toString();
  }

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["X-API-Key"] = token;

  const res = await fetch(url, {
    method,
    headers,
    body: body != null ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;
    let code: string | null = null;
    let fix: string | null = null;
    try {
      const j = await res.json();
      detail = j.detail?.message || j.detail || j.message || detail;
      code = j.detail?.code ?? null;
      fix = j.detail?.fix ?? null;
    } catch {
      // Response body was not JSON — use statusText as-is
    }
    throw new ApiError(res.status, detail, code, fix);
  }

  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return null;
  }
  return res.json();
}

export const api = {
  // Low-level HTTP verbs
  get: (path: string, params?: Record<string, unknown>) => request("GET", path, null, params),
  post: (path: string, body?: unknown) => request("POST", path, body),
  patch: (path: string, body?: unknown) => request("PATCH", path, body),
  delete: (path: string) => request("DELETE", path),

  // ── Named API methods ──────────────────────────────────────────────────────
  health: () => request("GET", "/health") as Promise<HealthData>,
  dashboard: () => request("GET", "/dashboard") as Promise<DashboardData>,

  // Run control
  runStatus: () => request("GET", "/run/status") as Promise<RunStatus>,
  startRun: (body: { full?: boolean }) => request("POST", "/run/start", body),
  stopRun: () => request("POST", "/run/stop"),

  // Run history
  getRuns: (limit?: number) =>
    request("GET", "/runs", null, limit ? { limit } : undefined) as Promise<RunSummary[]>,
  exportRunsCsv: async (): Promise<void> => {
    const [token, baseUrl] = await Promise.all([_getToken(), _getBaseUrl()]);
    const res = await fetch(baseUrl + "/runs/export?limit=10000", {
      headers: { "X-API-Key": token },
    });
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    const text = await res.text();
    const blob = new Blob([text], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ghostbackup_runs.csv";
    a.click();
    URL.revokeObjectURL(url);
  },
  getRun: (id: number) => request("GET", `/runs/${id}`) as Promise<RunSummary>,
  getRunLogs: (id: number, level?: string) =>
    request("GET", `/runs/${id}/logs`, null, level ? { level } : undefined) as Promise<LogEntry[]>,

  // Restore
  restore: (body: { run_id: number; library: string; destination: string; dry_run: boolean }) =>
    request("POST", "/restore", body) as Promise<RestoreResult>,

  // Config
  getConfig: () => request("GET", "/config") as Promise<BackupConfig>,
  verifyBackups: () => request("POST", "/verify") as Promise<VerifyResult>,
  resetConfig: () => request("POST", "/config/reset"),
  updateConfig: (body: unknown) => request("PATCH", "/config", body),
  addSite: (body: { label: string; path: string; enabled: boolean }) =>
    request("POST", "/config/sites", body) as Promise<{ config: BackupConfig }>,
  updateSite: (name: string, body: { enabled: boolean }) =>
    request("PATCH", `/config/sites/${encodeURIComponent(name)}`, body) as Promise<{
      source: import("./types").SourceFolder;
    }>,
  removeSite: (name: string) =>
    request("DELETE", `/config/sites/${encodeURIComponent(name)}`) as Promise<{
      config: BackupConfig;
    }>,

  // Settings
  updateSmtp: (body: unknown) => request("PATCH", "/settings/smtp", body),
  testSmtp: () => request("POST", "/settings/smtp/test"),
  updateRetention: (body: unknown) => request("PATCH", "/settings/retention", body),
  runPrune: () => request("POST", "/settings/prune"),

  // SSD
  ssdStatus: () => request("GET", "/ssd/status") as Promise<SsdStorage>,

  // Alerts
  getAlerts: () => request("GET", "/alerts") as Promise<AlertData>,
  dismissAlert: (id: number) => request("POST", `/alerts/${id}/dismiss`),
  dismissAllAlerts: () => request("POST", "/alerts/dismiss-all"),

  // Watcher
  watcherStatus: () => request("GET", "/watcher/status") as Promise<WatcherStatus>,
  watcherStart: () => request("POST", "/watcher/start") as Promise<WatcherStatus>,
  watcherStop: () => request("POST", "/watcher/stop") as Promise<WatcherStatus>,

  // Restore drills
  drillStatus: () => request("GET", "/settings/drill-status") as Promise<DrillStatus>,

  // Encryption
  generateEncryptionKey: () =>
    request("POST", "/settings/encryption/generate-key") as Promise<{ key: string }>,
};

export default api;
