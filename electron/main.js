/**
 * main.js — GhostBackup Electron Main Process
 *
 * Spawns the Python backend, manages the application window and system tray,
 * handles IPC with the renderer, and forwards desktop notifications from
 * the backend's HTTP notification server.
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
const crypto  = require("crypto");
const { spawn, execSync } = require("child_process");

// ── Constants ─────────────────────────────────────────────────────────────────
const API_PORT       = Number(process.env.GHOSTBACKUP_API_PORT || 8765);
const API_URL        = `http://127.0.0.1:${API_PORT}`;
const API_HEALTH_URL = `${API_URL}/health`;
const HEALTH_TIMEOUT = 30000;
const IS_DEV         = process.argv.includes("--dev") || process.env.NODE_ENV === "development";
const IS_WIN         = process.platform === "win32";

const ROOT_DIR    = path.join(__dirname, "..");
const BACKEND_DIR = path.join(ROOT_DIR, "backend");
const ICON_PATH   = path.join(ROOT_DIR, "assets", "icon.png");
const ENV_FILE    = path.join(ROOT_DIR, ".env.local");

const LAUNCHED_AT_STARTUP = process.argv.includes("--startup-minimized");

// Generate a fresh API token on every launch. Passed to the Python backend
// via GHOSTBACKUP_API_TOKEN and required in every request as X-API-Key.
const API_TOKEN = crypto.randomBytes(32).toString("hex");

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

// ── Windows Startup Registration ──────────────────────────────────────────────
function registerWindowsStartup() {
  if (!IS_WIN || IS_DEV) return;
  try {
    const exePath  = process.execPath;
    const regKey   = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run";
    const appName  = "GhostBackup";
    const regValue = `"${exePath}" --startup-minimized`;
    try {
      const current = execSync(`reg query "${regKey}" /v "${appName}"`, { encoding: "utf8" });
      if (current.includes(exePath)) return; // already registered
    } catch {
      // Key doesn't exist yet — fall through to add it
    }
    // Use /d with the value passed via stdin-style argument to handle spaces in path
    execSync(`reg add "${regKey}" /v "${appName}" /t REG_SZ /d "${regValue.replace(/"/g, '\\"')}" /f`, {
      encoding: "utf8", windowsHide: true,
    });
    console.log("[startup] Registered in Windows startup");
  } catch (err) {
    console.warn("[startup] Could not register Windows startup entry:", err.message);
  }
}

function unregisterWindowsStartup() {
  if (!IS_WIN) return;
  try {
    const regKey = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run";
    execSync(`reg delete "${regKey}" /v "GhostBackup" /f`, {
      encoding: "utf8", windowsHide: true,
    });
    console.log("[startup] Removed from Windows startup");
  } catch (err) {
    console.warn("[startup] Could not remove Windows startup entry:", err.message);
  }
}

function isRegisteredInStartup() {
  if (!IS_WIN || IS_DEV) return false;
  try {
    const regKey = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run";
    const result = execSync(`reg query "${regKey}" /v "GhostBackup"`, {
      encoding: "utf8", windowsHide: true,
    });
    return result.includes("GhostBackup");
  } catch {
    return false;
  }
}

// ── Port Conflict Resolution ──────────────────────────────────────────────────
/**
 * Only terminate a process occupying our API port if it is identifiably
 * a Python or previous GhostBackup process. Never blindly kill unknown processes.
 */
function killPortConflict(port) {
  if (!IS_WIN) {
    try {
      const result = execSync(`lsof -ti:${port}`, { encoding: "utf8" }).trim();
      if (!result) return;
      result.split("\n").forEach((pid) => {
        pid = pid.trim();
        if (!pid) return;
        try {
          const cmdline = execSync(`ps -p ${pid} -o comm=`, { encoding: "utf8" })
            .trim()
            .toLowerCase();
          if (cmdline.includes("python") || cmdline.includes("ghostbackup")) {
            execSync(`kill -9 ${pid}`);
            console.log(`[main] Killed python/ghostbackup PID ${pid} on port ${port}`);
          } else {
            console.warn(
              `[main] Port ${port} held by '${cmdline}' (PID ${pid}) — NOT killing unknown process`
            );
          }
        } catch {
          // Cannot determine process name — skip to be safe
        }
      });
    } catch {
      // No process on this port
    }
    return;
  }

  // Windows
  try {
    const output = execSync("netstat -ano", { encoding: "utf8", windowsHide: true });
    const killed = new Set();

    for (const line of output.split("\n")) {
      if (!line.includes(`:${port}`) || !line.includes("LISTENING")) continue;
      const parts = line.trim().split(/\s+/);
      const pid   = parts[parts.length - 1];
      if (!pid || pid === "0" || killed.has(pid)) continue;

      try {
        const info = execSync(
          `wmic process where "ProcessId=${pid}" get Name /format:value`,
          { encoding: "utf8", windowsHide: true }
        ).toLowerCase();

        if (info.includes("python") || info.includes("ghostbackup")) {
          killed.add(pid);
          execSync(`taskkill /PID ${pid} /F`, { windowsHide: true });
          console.log(`[main] Killed python PID ${pid} on port ${port}`);
        } else {
          console.warn(
            `[main] Port ${port} held by non-python PID ${pid} — skipping kill`
          );
        }
      } catch {
        console.warn(`[main] Could not check PID ${pid} — skipping`);
      }
    }
  } catch (err) {
    console.warn("[main] Port conflict check failed:", err.message);
  }
}

/** Non-blocking async sleep using setTimeout. */
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ── Notification Server (port 8766) ──────────────────────────────────────────
function startNotifyServer() {
  const notifyServer = http.createServer((req, res) => {
    if (req.method !== "POST" || req.url !== "/notify") {
      res.writeHead(404);
      res.end();
      return;
    }

    // Validate API token — only the backend should send notifications
    const token = req.headers["x-api-key"];
    if (token !== API_TOKEN) {
      res.writeHead(401);
      res.end("Unauthorized");
      return;
    }

    let body = "";
    let bodySize = 0;
    req.on("data", (chunk) => {
      bodySize += chunk.length;
      if (bodySize > 10240) { req.destroy(); return; }
      body += chunk;
    });
    req.on("end", () => {
      try {
        const { title, body: msg } = JSON.parse(body);
        if (title && Notification.isSupported()) {
          new Notification({ title, body: msg || "" }).show();
          mainWindow?.webContents.send("alert:new", { title, body: msg });
        }
      } catch {
        // Ignore malformed payloads
      }
      res.writeHead(200);
      res.end("ok");
    });
  });

  notifyServer.listen(8766, "127.0.0.1", () => {
    console.log("[main] Notify server listening on 127.0.0.1:8766");
  });

  notifyServer.on("error", (err) => {
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
      PYTHONUNBUFFERED:      "1",
      GHOSTBACKUP_API_PORT:  String(API_PORT),
      GHOSTBACKUP_API_TOKEN: API_TOKEN,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  proc.stdout.on("data", (data) => {
    data.toString().trim().split("\n").forEach((l) => console.log(`[python] ${l}`));
  });
  proc.stderr.on("data", (data) => {
    data.toString().trim().split("\n").forEach((l) => console.error(`[python:err] ${l}`));
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
    const start    = Date.now();
    let   attempts = 0;
    const delays   = [200, 300, 500, 800, 1000, 1500, 2000];

    const poll = () => {
      attempts++;
      const req = http.get(API_HEALTH_URL, (res) => {
        if (res.statusCode === 200) {
          console.log(
            `[main] Backend ready after ${attempts} polls (${Date.now() - start}ms)`
          );
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
      const delay = delays[Math.min(attempts, delays.length - 1)];
      setTimeout(poll, delay);
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
      sandbox:          true,
      webSecurity:      true,
    },
    show: false,
  });

  if (IS_DEV) {
    // In dev mode, override CSP to allow Vite HMR (inline styles, websocket)
    mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          "Content-Security-Policy": [
            "default-src 'self'; " +
            "script-src 'self' 'unsafe-inline'; " +
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; " +
            "font-src 'self' https://fonts.gstatic.com; " +
            `connect-src 'self' ${API_URL} ws://localhost:3000 ws://127.0.0.1:3000; ` +
            "img-src 'self' data:;"
          ],
        },
      });
    });
    mainWindow.loadURL("http://localhost:3000");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          "Content-Security-Policy": [
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src http://127.0.0.1:* ws://127.0.0.1:*; img-src 'self' data:;"
          ]
        }
      });
    });
    mainWindow.loadFile(path.join(ROOT_DIR, "dist", "index.html"));
  }

  mainWindow.once("ready-to-show", () => {
    if (!LAUNCHED_AT_STARTUP) mainWindow.show();
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
              method:  "POST",
              headers: {
                "Content-Type": "application/json",
                "X-API-Key":    API_TOKEN,
              },
              body: JSON.stringify({ full: false }),
            });
            new Notification({ title: "GhostBackup", body: "Backup started" }).show();
          } catch (e) {
            console.error("[tray] Run start failed:", e.message);
          }
        },
      },
      { type: "separator" },
      ...(IS_WIN ? [{
        label: startupEnabled ? "✓ Start with Windows" : "Start with Windows",
        click: () => {
          if (isRegisteredInStartup()) {
            unregisterWindowsStartup();
            new Notification({
              title: "GhostBackup",
              body: "Removed from Windows startup",
            }).show();
          } else {
            registerWindowsStartup();
            new Notification({
              title: "GhostBackup",
              body: "Will now start automatically with Windows",
            }).show();
          }
          rebuildMenu();
        },
      }] : []),
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
      "GHOSTBACKUP_SMTP_PASSWORD",
      "GHOSTBACKUP_ENCRYPTION_KEY",
    ];
    if (!ALLOWED_KEYS.includes(key)) {
      return { success: false, error: "Unknown credential key" };
    }
    const safeValue = value.replace(/[\r\n"\\]/g, "");
    if (safeValue !== value) return { error: "Invalid characters in credential value" };
    try {
      process.env[key] = safeValue;
      let envContent = fs.existsSync(ENV_FILE)
        ? fs.readFileSync(ENV_FILE, "utf8")
        : "";
      const regex = new RegExp(`^${key}=.*$`, "m");
      if (regex.test(envContent)) {
        envContent = envContent.replace(regex, `${key}="${safeValue}"`);
      } else {
        envContent += `\n${key}="${safeValue}"`;
      }
      fs.writeFileSync(ENV_FILE, envContent.trim() + "\n", { mode: 0o600 });
      return { success: true };
    } catch (err) {
      return { success: false, error: err.message };
    }
  });

  ipcMain.handle("credentials:status", async () => ({
    smtp_password:  !!process.env.GHOSTBACKUP_SMTP_PASSWORD,
    encryption_key: !!process.env.GHOSTBACKUP_ENCRYPTION_KEY,
  }));

  ipcMain.handle("shell:open-path", async (_, filePath) => {
    if (!filePath) return;
    const resolved = path.resolve(filePath);
    try {
      const stat = fs.statSync(resolved);
      if (!stat.isDirectory()) return { error: "Not a directory" };
    } catch { return { error: "Path not found" }; }
    await shell.openPath(resolved);
  });

  ipcMain.handle("app:api-url",   async () => API_URL);
  ipcMain.handle("app:version",   async () => app.getVersion());
  ipcMain.handle("app:api-token", async () => API_TOKEN);

  ipcMain.handle("backend:status", async () => ({
    ready: backendReady,
    url:   API_URL,
    pid:   pythonProcess?.pid ?? null,
  }));

  ipcMain.handle("notify", async (_, { title, body }) => {
    new Notification({ title, body }).show();
  });

  ipcMain.handle("startup:get", async () => isRegisteredInStartup());

  ipcMain.handle("startup:set", async (_, enable) => {
    try {
      if (enable) registerWindowsStartup();
      else        unregisterWindowsStartup();
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
  startNotifyServer();

  console.log(`[main] Checking port ${API_PORT} for conflicts...`);
  killPortConflict(API_PORT);

  createWindow();
  registerWindowsStartup();

  pythonProcess = spawnPythonBackend();
  if (!pythonProcess) return;

  try {
    await waitForBackend(HEALTH_TIMEOUT);
    console.log("[main] Backend healthy — renderer ready");
    mainWindow?.webContents.send("backend:ready", { url: API_URL });
  } catch (err) {
    console.error("[main] Backend failed to start:", err.message);
    showFatalError(
      "Backend Startup Failed",
      `GhostBackup's Python backend did not start within 30 seconds.\n\n${err.message}\n\n` +
      `Check that Python 3.10+ is installed and run:\npip install -r backend/requirements.txt`
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
      }
    }, 3000);
  }
  tray?.destroy();
});

process.on("uncaughtException", (err) => {
  console.error("[main] Uncaught exception:", err);
  dialog.showErrorBox("GhostBackup Error", err.message);
});
