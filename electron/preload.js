/**
 * preload.js — GhostBackup Electron Preload Script
 *
 * Fixes applied:
 *  - getApiToken() added — renderer can include X-API-Key in requests [FIX-P1]
 *  - credentials:status updated (removed legacy cloud keys)           [FIX]
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("ghostbackup", {
  // ── File system dialogs ───────────────────────────────────────────────────
  openDirectory: () => ipcRenderer.invoke("dialog:open-directory"),
  openFile: (filters) => ipcRenderer.invoke("dialog:open-file", filters),
  openInExplorer: (filePath) => ipcRenderer.invoke("shell:open-path", filePath),

  // ── Credentials (values never cross bridge) ───────────────────────────────
  saveCredential: (key, value) =>
    ipcRenderer.invoke("credentials:save", { key, value }),

  credentialStatus: () => ipcRenderer.invoke("credentials:status"),

  // ── App info ──────────────────────────────────────────────────────────────
  apiUrl:  () => ipcRenderer.invoke("app:api-url"),
  version: () => ipcRenderer.invoke("app:version"),

  // FIX-P1: Expose API token so React can include it in every request header.
  // The token value stays in main process memory; this only forwards it.
  getApiToken: () => ipcRenderer.invoke("app:api-token"),

  backendStatus: () => ipcRenderer.invoke("backend:status"),

  // ── Notifications ─────────────────────────────────────────────────────────
  notify: (title, body) => ipcRenderer.invoke("notify", { title, body }),

  // ── Event listeners (main → renderer) ────────────────────────────────────
  onBackendReady: (callback) => {
    const handler = (_, data) => callback(data);
    ipcRenderer.on("backend:ready", handler);
    return () => ipcRenderer.removeListener("backend:ready", handler);
  },

  onBackendCrashed: (callback) => {
    const handler = (_, data) => callback(data);
    ipcRenderer.on("backend:crashed", handler);
    return () => ipcRenderer.removeListener("backend:crashed", handler);
  },

  onRunComplete: (callback) => {
    const handler = (_, data) => callback(data);
    ipcRenderer.on("run:complete", handler);
    return () => ipcRenderer.removeListener("run:complete", handler);
  },
});
