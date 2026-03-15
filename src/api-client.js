/**
 * api-client.js — GhostBackup React API Client
 *
 * Centralises all fetch() calls from the React UI to the FastAPI backend.
 * Handles errors, JSON parsing, and provides typed response objects.
 *
 * Usage:
 *   import api from './api-client';
 *   const data = await api.dashboard();
 *   await api.startRun({ full: false });
 */

const BASE = "http://127.0.0.1:8765";

// ── Core fetch wrapper ────────────────────────────────────────────────────────
async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== null) {
    opts.body = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(`${BASE}${path}`, opts);
  } catch (err) {
    // Network failure — backend not reachable
    throw new ApiError(0, "Backend unreachable", err.message);
  }

  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }

  if (!res.ok) {
    const detail = data?.detail || `HTTP ${res.status}`;
    throw new ApiError(res.status, detail, data);
  }

  return data;
}

const get    = (path)         => request("GET",    path);
const post   = (path, body)   => request("POST",   path, body   ?? {});
const patch  = (path, body)   => request("PATCH",  path, body   ?? {});
const del    = (path)         => request("DELETE", path);

// ── API surface ───────────────────────────────────────────────────────────────
const api = {

  // Health
  health: ()          => get("/health"),

  // Dashboard
  dashboard: ()       => get("/dashboard"),

  // Run control
  startRun: (opts)    => post("/run/start", opts),
  stopRun:  ()        => post("/run/stop"),
  runStatus: ()       => get("/run/status"),

  // Run history
  getRuns: (limit = 30, offset = 0) =>
    get(`/runs?limit=${limit}&offset=${offset}`),

  getRun:  (id)       => get(`/runs/${id}`),
  getRunLogs: (id, level = "ALL") =>
    get(`/runs/${id}/logs?level=${level}`),
  getRunFiles: (id, library = "") =>
    get(`/runs/${id}/files${library ? `?library=${encodeURIComponent(library)}` : ""}`),

  // Config
  getConfig:    ()      => get("/config"),
  updateConfig: (data)  => patch("/config", data),
  addSite:      (site)  => post("/config/sites", site),
  removeSite:   (name)  => del(`/config/sites/${encodeURIComponent(name)}`),

  // Restore
  restore: (opts)     => post("/restore", opts),

  // SSD
  ssdStatus:       ()     => get("/ssd/status"),

  // Watcher  (Phase 3)
  watcherStatus:   ()     => get("/watcher/status"),
  watcherStart:    ()     => post("/watcher/start"),
  watcherStop:     ()     => post("/watcher/stop"),

  // Settings
  updateSmtp:      (data) => patch("/settings/smtp", data),
  testSmtp:        ()     => post("/settings/smtp/test"),
  updateRetention: (data) => patch("/settings/retention", data),
  runPrune:        ()     => post("/settings/prune"),
};

export default api;

// ── Error class ───────────────────────────────────────────────────────────────
export class ApiError extends Error {
  constructor(status, message, data = null) {
    super(message);
    this.name   = "ApiError";
    this.status = status;
    this.data   = data;
  }
}
