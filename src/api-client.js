/**
 * api-client.js — GhostBackup API Client
 *
 * Thin wrapper around fetch that adds the X-API-Key header to every request.
 * The token is fetched once from Electron IPC on the first call and cached
 * for the lifetime of the session.
 */

const DEFAULT_BASE_URL = "http://127.0.0.1:8765";

let _cachedToken   = null;
let _cachedBaseUrl = null;

async function _getBaseUrl() {
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

async function _getToken() {
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
export function clearTokenCache() {
  _cachedToken = null;
  _cachedBaseUrl = null;
}

export class ApiError extends Error {
  /**
   * @param {number} status  HTTP status code
   * @param {string} message Human-readable error detail
   * @param {*}      body    Raw response body, if available
   */
  constructor(status, message, body = null) {
    super(message);
    this.name   = "ApiError";
    this.status = status;
    this.body   = body;
  }
}

/**
 * Core request wrapper.
 *
 * @param {"GET"|"POST"|"PATCH"|"DELETE"} method
 * @param {string}  path    API path, e.g. "/dashboard"
 * @param {*}       [body]  JSON-serialisable request body
 * @param {Object}  [params] Query string parameters (null values omitted)
 * @returns {Promise<*>} Parsed JSON response, or null for 204 No Content
 */
export async function request(method, path, body, params) {
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

  const headers = { "Content-Type": "application/json" };
  if (token) headers["X-API-Key"] = token;

  const res = await fetch(url, {
    method,
    headers,
    body: body != null ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || j.message || detail;
    } catch {
      // Response body was not JSON — use statusText as-is
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return null;
  }
  return res.json();
}

export const api = {
  // Low-level HTTP verbs
  get:    (path, params) => request("GET",    path, null, params),
  post:   (path, body)   => request("POST",   path, body),
  patch:  (path, body)   => request("PATCH",  path, body),
  delete: (path)         => request("DELETE", path),

  // ── Named API methods ──────────────────────────────────────────────────────
  health:          ()            => request("GET",    "/health"),
  dashboard:       ()            => request("GET",    "/dashboard"),

  // Run control
  runStatus:       ()            => request("GET",    "/run/status"),
  startRun:        (body)        => request("POST",   "/run/start",  body),
  stopRun:         ()            => request("POST",   "/run/stop"),

  // Run history
  getRuns:         (limit)       => request("GET",    "/runs", null, limit ? { limit } : null),
  getRun:          (id)          => request("GET",    `/runs/${id}`),
  getRunLogs:      (id, level)   => request("GET",    `/runs/${id}/logs`, null, level ? { level } : null),

  // Restore
  restore:         (body)        => request("POST",   "/restore", body),

  // Config
  getConfig:       ()            => request("GET",    "/config"),
  updateConfig:    (body)        => request("PATCH",  "/config", body),
  addSite:         (body)        => request("POST",   "/config/sites", body),
  updateSite:      (name, body)  => request("PATCH",  `/config/sites/${encodeURIComponent(name)}`, body),
  removeSite:      (name)        => request("DELETE", `/config/sites/${encodeURIComponent(name)}`),

  // Settings
  updateSmtp:      (body)        => request("PATCH",  "/settings/smtp", body),
  testSmtp:        ()            => request("POST",   "/settings/smtp/test"),
  updateRetention: (body)        => request("PATCH",  "/settings/retention", body),
  runPrune:        ()            => request("POST",   "/settings/prune"),

  // SSD
  ssdStatus:       ()            => request("GET",    "/ssd/status"),

  // Alerts
  getAlerts:       ()            => request("GET",    "/alerts"),
  dismissAlert:    (id)          => request("POST",   `/alerts/${id}/dismiss`),
  dismissAllAlerts:()            => request("POST",   "/alerts/dismiss-all"),

  // Watcher
  watcherStatus:   ()            => request("GET",    "/watcher/status"),
  watcherStart:    ()            => request("POST",   "/watcher/start"),
  watcherStop:     ()            => request("POST",   "/watcher/stop"),

  // Encryption
  generateEncryptionKey: ()      => request("POST",   "/settings/encryption/generate-key"),
};

export default api;
