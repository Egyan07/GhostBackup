/**
 * preload.js — GhostBackup Electron Preload Script
 *
 * Exposes a locked-down API surface to the renderer process via contextBridge.
 * Sensitive values (API token, credentials) remain in the main process and are
 * only forwarded through IPC — they are never directly accessible to renderer JS.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("ghostbackup", {
  // ── File system dialogs ───────────────────────────────────────────────────
  openDirectory:  ()        => ipcRenderer.invoke("dialog:open-directory"),
  openFile:       (filters) => ipcRenderer.invoke("dialog:open-file", filters),
  openInExplorer: (filePath) => ipcRenderer.invoke("shell:open-path", filePath),

  // ── Credentials (values never cross the bridge) ───────────────────────────
  saveCredential:   (key, value) => ipcRenderer.invoke("credentials:save", { key, value }),
  credentialStatus: ()           => ipcRenderer.invoke("credentials:status"),

  // ── App info ──────────────────────────────────────────────────────────────
  apiUrl:        () => ipcRenderer.invoke("app:api-url"),
  version:       () => ipcRenderer.invoke("app:version"),
  getApiToken:   () => ipcRenderer.invoke("app:api-token"),
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

  onAlertNew: (callback) => {
    const handler = (_, data) => callback(data);
    ipcRenderer.on("alert:new", handler);
    return () => ipcRenderer.removeListener("alert:new", handler);
  },

});
