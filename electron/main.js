/**
 * main.js — GhostBackup Electron Main Process
 *
 * Phase 1 Automation additions:
 *  - Auto-kill any process holding port 8765 before spawning backend
 *  - Register app in Windows startup (HKCU Run key) on first launch
 *  - Launch minimized to tray when started by Windows at boot
 *  - Startup flag detection (--startup-minimized)
 *
 * Original responsibilities:
 *  1. Spawn the Python FastAPI backend as a child process
 *  2. Wait for backend to be ready (health check polling)
 *  3. Create the BrowserWindow and load the React renderer
 *  4. Handle IPC messages from renderer
 *  5. Clean up: kill Python backend on app quit
 *  6. Single-instance lock
 */

const {
  app,
  BrowserWindow,
  ipcMain,
  dialog,
  shell,
  Tray,
  Menu,
  nativeImage,
  Notification,
} = require("electron");
const path    = require("path");
const fs      = require("fs");
const http    = require("http");
const { spawn, execSync } = require("child_process");

// ── Constants ─────────────────────────────────────────────────────────────────
const API_PORT        = 8765;
const API_URL         = `http://127.0.0.1:${API_PORT}`;
const API_HEALTH_URL  = `${API_URL}/health`;
const HEALTH_POLL_MS  = 500;
const HEALTH_TIMEOUT  = 30000;
const IS_DEV          = process.env.NODE_ENV === "development";
const IS_WIN          = process.platform === "win32";

// Paths
const ROOT_DIR    = path.join(__dirname, "..");
const BACKEND_DIR = path.join(ROOT_DIR, "backend");
const ICON_PATH   = path.join(ROOT_DIR, "assets", "icon.png");
const ENV_FILE    = path.join(ROOT_DIR, ".env.local");

// Startup flag — set when Windows launches us automatically at boot
const LAUNCHED_AT_STARTUP = process.argv.includes("--startup-minimized");

// ── State ─────────────────────────────────────────────────────────────────────
let mainWindow    = null;
let tray          = null;
let pythonProcess = null;
let backendReady  = false;

// ── Single instance lock ──────────────────────────────────────────────────────
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
  process.exit(0);
}

app.on("second-instance", () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  }
});

// ── PHASE 1: Windows Startup Registration ─────────────────────────────────────
/**
 * Registers GhostBackup in the Windows registry under
 * HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
 * so it auto-starts when the user logs in.
 *
 * Uses --startup-minimized flag so the app launches to tray silently.
 * Safe to call on every launch — registry write is idempotent.
 */
function registerWindowsStartup() {
  if (!IS_WIN) return;

  try {
    const exePath = process.execPath;
    // In dev mode, registering doesn't make sense — skip
    if (IS_DEV) {
      console.log("[startup] Skipping startup registration in dev mode");
      return;
    }

    const regKey   = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run";
    const appName  = "GhostBackup";
    const regValue = `"${exePath}" --startup-minimized`;

    // Read current value first to avoid unnecessary writes
    try {
      const current = execSync(`reg query "${regKey}" /v "${appName}"`, { encoding: "utf8" });
      if (current.includes(exePath)) {
        console.log("[startup] Windows startup entry already registered");
        return;
      }
    } catch {
      // Key doesn't exist yet — proceed to add
    }

    execSync(`reg add "${regKey}" /v "${appName}" /t REG_SZ /d "${regValue}" /f`, {
      encoding: "utf8",
      windowsHide: true,
    });

    console.log("[startup] Registered in Windows startup");
  } catch (err) {
    // Non-fatal — log and continue
    console.warn("[startup] Could not register Windows startup entry:", err.message);
  }
}

/**
 * Remove GhostBackup from Windows startup (for Settings toggle).
 */
function unregisterWindowsStartup() {
  if (!IS_WIN) return;
  try {
    const regKey  = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run";
    const appName = "GhostBackup";
    execSync(`reg delete "${regKey}" /v "${appName}" /f`, { encoding: "utf8", windowsHide: true });
    console.log("[startup] Removed from Windows startup");
  } catch (err) {
    console.warn("[startup] Could not remove Windows startup entry:", err.message);
  }
}

/**
 * Check if GhostBackup is currently in Windows startup.
 */
function isRegisteredInStartup() {
  if (!IS_WIN || IS_DEV) return false;
  try {
    const regKey = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run";
    const result = execSync(`reg query "${regKey}" /v "GhostBackup"`, { encoding: "utf8", windowsHide: true });
    return result.includes("GhostBackup");
  } catch {
    return false;
  }
}

// ── PHASE 1: Port Conflict Auto-Kill ─────────────────────────────────────────
/**
 * Find and kill any process holding port 8765 before we try to bind it.
 * This prevents the "only one usage of each socket address" error on restart.
 */
function killPortConflict(port) {
  if (!IS_WIN) {
    // Linux/macOS
    try {
      const result = execSync(`lsof -ti:${port}`, { encoding: "utf8" }).trim();
      if (result) {
        result.split("\n").forEach(pid => {
          try { execSync(`kill -9 ${pid.trim()}`); } catch {}
        });
        console.log(`[main] Killed process(es) holding port ${port}: ${result}`);
      }
    } catch {
      // No process on port — that's fine
    }
    return;
  }

  // Windows
  try {
    const output = execSync(`netstat -ano`, { encoding: "utf8", windowsHide: true });
    const lines  = output.split("\n");
    const killed = new Set();

    for (const line of lines) {
      // Match lines like: TCP  127.0.0.1:8765  0.0.0.0:0  LISTENING  1234
      if (line.includes(`:${port}`) && line.includes("LISTENING")) {
        const parts = line.trim().split(/\s+/);
        const pid   = parts[parts.length - 1];
        if (pid && pid !== "0" && !killed.has(pid)) {
          killed.add(pid);
          try {
            execSync(`taskkill /PID ${pid} /F`, { windowsHide: true });
            console.log(`[main] Killed PID ${pid} holding port ${port}`);
          } catch (e) {
            console.warn(`[main] Could not kill PID ${pid}: ${e.message}`);
          }
        }
      }
    }

    if (killed.size === 0) {
      console.log(`[main] Port ${port} is free`);
    } else {
      // Brief pause to let the OS release the port
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 300);
    }
  } catch (err) {
    console.warn("[main] Port conflict check failed:", err.message);
  }
}

// ── PHASE 2: Electron Notification Server (port 8766) ────────────────────────
/**
 * A tiny HTTP server that Python's reporter.py POSTs to when it fires
 * alert_and_notify(). This lets the backend trigger native Windows toasts
 * instantly without waiting for the renderer to poll /alerts.
 *
 * Only listens on 127.0.0.1 — not exposed to the network.
 */
function startNotifyServer() {
  const notifyServer = require("http").createServer((req, res) => {
    if (req.method !== "POST" || req.url !== "/notify") {
      res.writeHead(404); res.end(); return;
    }
    let body = "";
    req.on("data", chunk => { body += chunk; });
    req.on("end", () => {
      try {
        const { title, body: msg } = JSON.parse(body);
        if (title && Notification.isSupported()) {
          const notif = new Notification({ title, body: msg || "" });
          notif.show();
          // Also forward to renderer so the bell badge updates live
          mainWindow?.webContents.send("alert:new", { title, body: msg });
        }
      } catch {}
      res.writeHead(200); res.end("ok");
    });
  });

  notifyServer.listen(8766, "127.0.0.1", () => {
    console.log("[main] Notify server listening on 127.0.0.1:8766");
  });

  notifyServer.on("error", (err) => {
    // Port 8766 in use — not fatal, toasts will fall back to polling
    console.warn("[main] Notify server error:", err.message);
  });
}


function loadEnvFile() {
  if (!fs.existsSync(ENV_FILE)) return;
  const lines = fs.readFileSync(ENV_FILE, "utf8").split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf("=");
    if (idx === -1) continue;
    const key = trimmed.slice(0, idx).trim();
    const val = trimmed.slice(idx + 1).trim().replace(/^["']|["']$/g, "");
    if (!process.env[key]) process.env[key] = val;
  }
  console.log("[main] Loaded .env.local");
}

// ── Python backend spawning ───────────────────────────────────────────────────
function getPythonExecutable() {
  if (IS_WIN) {
    const bundled = path.join(ROOT_DIR, "python", "python.exe");
    if (fs.existsSync(bundled)) return bundled;
    return "python";
  }
  return "python3";
}

function spawnPythonBackend() {
  const python = getPythonExecutable();
  const script = path.join(BACKEND_DIR, "api.py");

  if (!fs.existsSync(script)) {
    console.error(`[main] Backend script not found: ${script}`);
    showFatalError("Backend not found", `api.py not found at:\n${script}`);
    return null;
  }

  console.log(`[main] Starting Python backend: ${python} ${script}`);

  const proc = spawn(python, [script], {
    cwd: BACKEND_DIR,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      GHOSTBACKUP_API_PORT: String(API_PORT),
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  proc.stdout.on("data", (data) => {
    data.toString().trim().split("\n").forEach(l => console.log(`[python] ${l}`));
  });

  proc.stderr.on("data", (data) => {
    data.toString().trim().split("\n").forEach(l => console.error(`[python:err] ${l}`));
  });

  proc.on("exit", (code, signal) => {
    console.log(`[main] Python backend exited — code: ${code}, signal: ${signal}`);
    backendReady = false;
    if (!app.isQuitting) showBackendCrashNotification(code);
  });

  proc.on("error", (err) => {
    console.error(`[main] Failed to spawn Python: ${err.message}`);
    showFatalError(
      "Python not found",
      `Could not start the backend.\n\nError: ${err.message}\n\nMake sure Python 3.10+ is installed.`
    );
  });

  return proc;
}

// ── Backend health check ──────────────────────────────────────────────────────
function waitForBackend(timeoutMs = HEALTH_TIMEOUT) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    let attempts = 0;

    const poll = () => {
      attempts++;
      const req = http.get(API_HEALTH_URL, (res) => {
        if (res.statusCode === 200) {
          console.log(`[main] Backend ready after ${attempts} polls (${Date.now() - start}ms)`);
          backendReady = true;
          resolve();
        } else {
          scheduleRetry();
        }
      });
      req.on("error", () => scheduleRetry());
      req.setTimeout(400, () => { req.destroy(); scheduleRetry(); });
    };

    const scheduleRetry = () => {
      if (Date.now() - start > timeoutMs) {
        reject(new Error(`Backend did not become ready within ${timeoutMs}ms`));
        return;
      }
      setTimeout(poll, HEALTH_POLL_MS);
    };

    poll();
  });
}

// ── Window creation ───────────────────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width:           1280,
    height:          800,
    minWidth:        960,
    minHeight:       600,
    backgroundColor: "#0e0f11",
    titleBarStyle:   IS_WIN ? "default" : "hiddenInset",
    icon:            fs.existsSync(ICON_PATH) ? ICON_PATH : undefined,
    webPreferences: {
      preload:          path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration:  false,
      sandbox:          false,
      webSecurity:      true,
    },
    show: false,
  });

  if (IS_DEV) {
    mainWindow.loadURL("http://localhost:3000");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(ROOT_DIR, "dist", "index.html"));
  }

  mainWindow.once("ready-to-show", () => {
    // If launched by Windows at startup, stay hidden in tray
    if (LAUNCHED_AT_STARTUP) {
      console.log("[main] Launched at startup — staying minimized in tray");
    } else {
      mainWindow.show();
      console.log("[main] Window shown");
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http")) shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.on("close", (e) => {
    if (!app.isQuitting && tray) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on("closed", () => { mainWindow = null; });
}

function createTray() {
  const icon = fs.existsSync(ICON_PATH)
    ? nativeImage.createFromPath(ICON_PATH).resize({ width: 16, height: 16 })
    : nativeImage.createEmpty();

  tray = new Tray(icon);
  tray.setToolTip("GhostBackup — Red Parrot Accounting");

  const rebuildMenu = () => {
    const startupEnabled = isRegisteredInStartup();
    const menu = Menu.buildFromTemplate([
      {
        label: "Open GhostBackup",
        click: () => { mainWindow?.show(); mainWindow?.focus(); },
      },
      { type: "separator" },
      {
        label: "Run Backup Now",
        click: async () => {
          try {
            await fetch(`${API_URL}/run/start`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ full: false }),
            });
            new Notification({ title: "GhostBackup", body: "Backup started" }).show();
          } catch (e) {
            console.error("[tray] Run start failed:", e.message);
          }
        },
      },
      { type: "separator" },
      {
        label: startupEnabled ? "✓ Start with Windows" : "Start with Windows",
        type:  "normal",
        click: () => {
          if (isRegisteredInStartup()) {
            unregisterWindowsStartup();
            new Notification({ title: "GhostBackup", body: "Removed from Windows startup" }).show();
          } else {
            registerWindowsStartup();
            new Notification({ title: "GhostBackup", body: "Will now start automatically with Windows" }).show();
          }
          // Rebuild menu to reflect new state
          rebuildMenu();
        },
      },
      { type: "separator" },
      {
        label: "Quit GhostBackup",
        click: () => { app.isQuitting = true; app.quit(); },
      },
    ]);

    tray.setContextMenu(menu);
  };

  rebuildMenu();
  tray.on("double-click", () => { mainWindow?.show(); mainWindow?.focus(); });
}

// ── IPC handlers ──────────────────────────────────────────────────────────────
function registerIpcHandlers() {
  ipcMain.handle("dialog:open-directory", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ["openDirectory", "createDirectory"],
      title: "Select Restore Destination",
    });
    return result.canceled ? null : result.filePaths[0];
  });

  ipcMain.handle("dialog:open-file", async (_, filters) => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ["openFile"],
      filters: filters || [{ name: "YAML", extensions: ["yaml", "yml"] }],
    });
    return result.canceled ? null : result.filePaths[0];
  });

  ipcMain.handle("credentials:save", async (_, { key, value }) => {
    const ALLOWED_KEYS = [
      "GHOSTBACKUP_TENANT_ID",
      "GHOSTBACKUP_CLIENT_ID",
      "GHOSTBACKUP_CLIENT_SECRET",
      "GHOSTBACKUP_SMTP_PASSWORD",
    ];
    if (!ALLOWED_KEYS.includes(key)) return { success: false, error: "Unknown credential key" };
    try {
      process.env[key] = value;
      let envContent = fs.existsSync(ENV_FILE) ? fs.readFileSync(ENV_FILE, "utf8") : "";
      const regex = new RegExp(`^${key}=.*$`, "m");
      if (regex.test(envContent)) {
        envContent = envContent.replace(regex, `${key}="${value}"`);
      } else {
        envContent += `\n${key}="${value}"`;
      }
      fs.writeFileSync(ENV_FILE, envContent.trim() + "\n", { mode: 0o600 });
      return { success: true };
    } catch (err) {
      return { success: false, error: err.message };
    }
  });

  ipcMain.handle("credentials:status", async () => ({
    tenant_id:     !!process.env.GHOSTBACKUP_TENANT_ID,
    client_id:     !!process.env.GHOSTBACKUP_CLIENT_ID,
    client_secret: !!process.env.GHOSTBACKUP_CLIENT_SECRET,
    smtp_password: !!process.env.GHOSTBACKUP_SMTP_PASSWORD,
  }));

  ipcMain.handle("shell:open-path", async (_, filePath) => {
    if (!filePath) return;
    await shell.openPath(filePath);
  });

  ipcMain.handle("app:api-url",  async () => API_URL);
  ipcMain.handle("app:version",  async () => app.getVersion());

  ipcMain.handle("backend:status", async () => ({
    ready: backendReady,
    url:   API_URL,
    pid:   pythonProcess?.pid ?? null,
  }));

  ipcMain.handle("notify", async (_, { title, body }) => {
    new Notification({ title, body }).show();
  });

  // ── Phase 1: Startup toggle from renderer ──────────────────────────────────
  ipcMain.handle("startup:get", async () => isRegisteredInStartup());

  ipcMain.handle("startup:set", async (_, enable) => {
    try {
      if (enable) {
        registerWindowsStartup();
      } else {
        unregisterWindowsStartup();
      }
      return { success: true, enabled: isRegisteredInStartup() };
    } catch (err) {
      return { success: false, error: err.message };
    }
  });
}

// ── Error helpers ─────────────────────────────────────────────────────────────
function showFatalError(title, message) {
  dialog.showErrorBox(`GhostBackup — ${title}`, message);
}

function showBackendCrashNotification(exitCode) {
  if (Notification.isSupported()) {
    new Notification({
      title: "GhostBackup — Backend Error",
      body:  `The backup service stopped unexpectedly (code ${exitCode}). Restart the app.`,
    }).show();
  }
  mainWindow?.webContents.send("backend:crashed", { exitCode });
}

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  console.log("[main] App ready — starting GhostBackup");

  loadEnvFile();
  registerIpcHandlers();

  // ── PHASE 2: Start notification receiver before Python spawns ────────────
  startNotifyServer();

  // ── PHASE 1: Kill any process already holding our port ────────────────────
  console.log(`[main] Checking port ${API_PORT} for conflicts...`);
  killPortConflict(API_PORT);

  // Show window (hidden if startup-minimized)
  createWindow();

  // ── PHASE 1: Register in Windows startup (prod only) ─────────────────────
  registerWindowsStartup();

  // Spawn backend
  pythonProcess = spawnPythonBackend();
  if (!pythonProcess) return;

  // Wait for health
  try {
    await waitForBackend(HEALTH_TIMEOUT);
    console.log("[main] Backend healthy — renderer ready");
    mainWindow?.webContents.send("backend:ready", { url: API_URL });
  } catch (err) {
    console.error("[main] Backend failed to start:", err.message);
    showFatalError(
      "Backend Startup Failed",
      `GhostBackup's Python backend did not start within 30 seconds.\n\n${err.message}\n\nCheck that Python 3.10+ is installed and run:\npip install -r backend/requirements.txt`
    );
    app.quit();
    return;
  }

  createTray();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else mainWindow?.show();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    if (!tray) app.quit();
  }
});

app.on("before-quit", () => { app.isQuitting = true; });

app.on("quit", () => {
  console.log("[main] App quitting — killing Python backend...");
  if (pythonProcess && !pythonProcess.killed) {
    pythonProcess.kill("SIGTERM");
    setTimeout(() => {
      if (pythonProcess && !pythonProcess.killed) {
        pythonProcess.kill("SIGKILL");
        console.log("[main] Python backend force-killed");
      }
    }, 3000);
  }
  tray?.destroy();
});

process.on("uncaughtException", (err) => {
  console.error("[main] Uncaught exception:", err);
  dialog.showErrorBox("GhostBackup Error", err.message);
});
