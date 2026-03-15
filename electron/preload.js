/**
 * preload.js — GhostBackup Electron Preload Script
 *
 * Runs in a privileged context but exposes a controlled, minimal API
 * to the React renderer via contextBridge. The renderer cannot access
 * Node.js or Electron APIs directly — only what's explicitly exposed here.
 *
 * Exposed as window.ghostbackup in the renderer.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("ghostbackup", {
  // ── File system dialogs ───────────────────────────────────────────────────
  /**
   * Open OS directory picker. Returns selected path or null.
   */
  openDirectory: () => ipcRenderer.invoke("dialog:open-directory"),

  /**
   * Open OS file picker. Returns selected file path or null.
   * @param {Array} filters - [{name, extensions}]
   */
  openFile: (filters) => ipcRenderer.invoke("dialog:open-file", filters),

  /**
   * Open a path in the OS file explorer.
   * @param {string} filePath
   */
  openInExplorer: (filePath) => ipcRenderer.invoke("shell:open-path", filePath),

  // ── Credentials (secure, values never cross bridge) ───────────────────────
  /**
   * Save a credential by key. Value is handled in main process only.
   * Returns {success, error?}
   */
  saveCredential: (key, value) =>
    ipcRenderer.invoke("credentials:save", { key, value }),

  /**
   * Check which credentials are currently set. Returns booleans only.
   * Returns {tenant_id, client_id, client_secret, smtp_password}
   */
  credentialStatus: () => ipcRenderer.invoke("credentials:status"),

  // ── App info ──────────────────────────────────────────────────────────────
  /** Returns the backend API base URL e.g. http://127.0.0.1:8765 */
  apiUrl: () => ipcRenderer.invoke("app:api-url"),

  /** Returns app version string */
  version: () => ipcRenderer.invoke("app:version"),

  /** Returns {ready, url, pid} for the Python backend */
  backendStatus: () => ipcRenderer.invoke("backend:status"),

  // ── Notifications ─────────────────────────────────────────────────────────
  /**
   * Show a desktop notification.
   * @param {string} title
   * @param {string} body
   */
  notify: (title, body) => ipcRenderer.invoke("notify", { title, body }),

  // ── Event listeners (main → renderer) ────────────────────────────────────
  /**
   * Listen for backend ready event.
   * @param {function} callback - ({url}) => void
   * @returns {function} unsubscribe function
   */
  onBackendReady: (callback) => {
    const handler = (_, data) => callback(data);
    ipcRenderer.on("backend:ready", handler);
    return () => ipcRenderer.removeListener("backend:ready", handler);
  },

  /**
   * Listen for backend crash event.
   * @param {function} callback - ({exitCode}) => void
   * @returns {function} unsubscribe function
   */
  onBackendCrashed: (callback) => {
    const handler = (_, data) => callback(data);
    ipcRenderer.on("backend:crashed", handler);
    return () => ipcRenderer.removeListener("backend:crashed", handler);
  },

  /**
   * Listen for backup run completion notification from main process.
   * @param {function} callback
   * @returns {function} unsubscribe function
   */
  onRunComplete: (callback) => {
    const handler = (_, data) => callback(data);
    ipcRenderer.on("run:complete", handler);
    return () => ipcRenderer.removeListener("run:complete", handler);
  },
});
