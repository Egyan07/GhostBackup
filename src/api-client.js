/**
 * api-client.js — GhostBackup API Client
 *
 * Fixes applied:
 *  - All requests include X-API-Key header from Electron IPC   [FIX-P1]
 *  - Token cached after first IPC call (Electron) or env var   [FIX-P1]
 *  - getApiToken() returns empty string in browser dev mode     [FIX-P1]
 */

const BASE_URL = "http://127.0.0.1:8765";

// FIX-P1: Cache the API token — fetched once from Electron IPC on first request.
let _cachedToken = null;

async function _getToken() {
  if (_cachedToken !== null) return _cachedToken;

  if (window.ghostbackup?.getApiToken) {
    try {
      _cachedToken = await window.ghostbackup.getApiToken();
    } catch {
      _cachedToken = "";
    }
  } else {
    // Browser dev mode without Electron — no token required
    _cachedToken = "";
  }
  return _cachedToken;
}

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message);
    this.status = status;
    this.body   = body;
  }
}

/**
 * Core request wrapper. Automatically includes X-API-Key on every call.
 */
export async function request(method, path, body, params) {
  const token = await _getToken();

  let url = BASE_URL + path;
  if (params) {
    const qs = new URLSearchParams(
      Object.fromEntries(
        Object.entries(params)
          .filter(([, v]) => v != null)
          .map(([k, v]) => [k, String(v)])
      )
    );
    if (qs.toString()) url += "?" + qs.toString();
  }

  const headers = { "Content-Type": "application/json" };

  // FIX-P1: Attach auth token to every request
  if (token) {
    headers["X-API-Key"] = token;
  }

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
    } catch {}
    throw new ApiError(res.status, detail, null);
  }

  if (res.status === 204 || res.headers.get("content-length") === "0") return null;
  return res.json();
}

export const api = {
  get:    (path, params) => request("GET",    path, null, params),
  post:   (path, body)   => request("POST",   path, body),
  patch:  (path, body)   => request("PATCH",  path, body),
  delete: (path)         => request("DELETE", path),
};
