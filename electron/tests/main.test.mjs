/**
 * main.test.mjs — Electron main process unit tests
 *
 * Tests the extractable pure/testable logic from electron/main.js.
 * Since main.js has import-time side effects (app.requestSingleInstanceLock()),
 * we test by re-implementing key functions with the same logic and mocking
 * the Electron APIs they depend on.
 *
 * The preload bridge and IPC handler sections mock Electron's module system
 * to verify actual registration behavior rather than string-matching source.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import fs from "fs";
import path from "path";
import http from "http";
import crypto from "crypto";
import { createRequire } from "module";

// ── loadEnvFile logic ────────────────────────────────────────────────────────

function loadEnvFile(envFile) {
  if (!fs.existsSync(envFile)) return {};
  const lines = fs.readFileSync(envFile, "utf8").split("\n");
  const result = {};
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf("=");
    if (idx === -1) continue;
    const key = trimmed.slice(0, idx).trim();
    const val = trimmed
      .slice(idx + 1)
      .trim()
      .replace(/^["']|["']$/g, "");
    result[key] = val;
  }
  return result;
}

describe("loadEnvFile", () => {
  const tmpDir = path.join("/tmp", "gb-test-" + Date.now());
  const envFile = path.join(tmpDir, ".env.local");

  beforeEach(() => {
    fs.mkdirSync(tmpDir, { recursive: true });
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it("returns empty object when file does not exist", () => {
    expect(loadEnvFile("/tmp/nonexistent/.env.local")).toEqual({});
  });

  it("parses KEY=value lines", () => {
    fs.writeFileSync(envFile, "FOO=bar\nBAZ=qux\n");
    const result = loadEnvFile(envFile);
    expect(result).toEqual({ FOO: "bar", BAZ: "qux" });
  });

  it("strips quotes from values", () => {
    fs.writeFileSync(envFile, "API_KEY=\"secret123\"\nPATH='hello'\n");
    const result = loadEnvFile(envFile);
    expect(result.API_KEY).toBe("secret123");
    expect(result.PATH).toBe("hello");
  });

  it("ignores comments and empty lines", () => {
    fs.writeFileSync(envFile, "# This is a comment\n\nKEY=value\n# another\n");
    const result = loadEnvFile(envFile);
    expect(result).toEqual({ KEY: "value" });
  });

  it("ignores lines without =", () => {
    fs.writeFileSync(envFile, "INVALID_LINE\nGOOD=value\n");
    const result = loadEnvFile(envFile);
    expect(result).toEqual({ GOOD: "value" });
  });

  it("handles values with = in them", () => {
    fs.writeFileSync(envFile, "KEY=abc=def=ghi\n");
    const result = loadEnvFile(envFile);
    expect(result.KEY).toBe("abc=def=ghi");
  });
});

// ── waitForBackend logic ─────────────────────────────────────────────────────

function waitForBackend(url, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    let attempts = 0;
    const delays = [50, 100, 200];

    const poll = () => {
      attempts++;
      const req = http.get(url, (res) => {
        if (res.statusCode === 200) {
          resolve({ attempts, elapsed: Date.now() - start });
        } else {
          scheduleRetry();
        }
        res.resume();
      });
      req.on("error", () => scheduleRetry());
      req.setTimeout(200, () => {
        req.destroy();
        scheduleRetry();
      });
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

describe("waitForBackend", () => {
  let server;

  afterEach(() => {
    if (server) {
      server.close();
      server = null;
    }
  });

  it("resolves when server responds with 200", async () => {
    server = http.createServer((_, res) => {
      res.writeHead(200);
      res.end("ok");
    });
    await new Promise((r) => server.listen(0, "127.0.0.1", r));
    const port = server.address().port;

    const result = await waitForBackend(`http://127.0.0.1:${port}/health`);
    expect(result.attempts).toBeGreaterThanOrEqual(1);
  });

  it("rejects after timeout when server never responds 200", async () => {
    server = http.createServer((_, res) => {
      res.writeHead(503);
      res.end("not ready");
    });
    await new Promise((r) => server.listen(0, "127.0.0.1", r));
    const port = server.address().port;

    await expect(waitForBackend(`http://127.0.0.1:${port}/health`, 500)).rejects.toThrow(
      /did not become ready/
    );
  });

  it("rejects when no server is running", async () => {
    await expect(waitForBackend("http://127.0.0.1:19999/health", 500)).rejects.toThrow(
      /did not become ready/
    );
  });

  it("retries and succeeds when server becomes ready", async () => {
    let requestCount = 0;
    server = http.createServer((_, res) => {
      requestCount++;
      if (requestCount >= 3) {
        res.writeHead(200);
        res.end("ok");
      } else {
        res.writeHead(503);
        res.end("not ready");
      }
    });
    await new Promise((r) => server.listen(0, "127.0.0.1", r));
    const port = server.address().port;

    const result = await waitForBackend(`http://127.0.0.1:${port}/health`, 5000);
    expect(result.attempts).toBeGreaterThanOrEqual(3);
  });
});

// ── API token generation ────────────────────────────────────────────────────

describe("API token generation", () => {
  it("generates a 64-character hex token", () => {
    const token = crypto.randomBytes(32).toString("hex");
    expect(token).toHaveLength(64);
    expect(/^[0-9a-f]+$/.test(token)).toBe(true);
  });

  it("generates unique tokens on each call", () => {
    const a = crypto.randomBytes(32).toString("hex");
    const b = crypto.randomBytes(32).toString("hex");
    expect(a).not.toBe(b);
  });
});

// ── Credential validation logic ──────────────────────────────────────────────

function validateCredentialKey(key) {
  const ALLOWED_KEYS = [
    "GHOSTBACKUP_SMTP_PASSWORD",
    "GHOSTBACKUP_ENCRYPTION_KEY",
    "GHOSTBACKUP_HKDF_SALT",
  ];
  return ALLOWED_KEYS.includes(key);
}

function validateCredentialValue(value) {
  const safeValue = value.replace(/[\r\n"\\]/g, "");
  return safeValue === value;
}

describe("credential validation", () => {
  it("accepts allowed credential keys", () => {
    expect(validateCredentialKey("GHOSTBACKUP_SMTP_PASSWORD")).toBe(true);
    expect(validateCredentialKey("GHOSTBACKUP_ENCRYPTION_KEY")).toBe(true);
    expect(validateCredentialKey("GHOSTBACKUP_HKDF_SALT")).toBe(true);
  });

  it("rejects unknown credential keys", () => {
    expect(validateCredentialKey("GHOSTBACKUP_SECRET")).toBe(false);
    expect(validateCredentialKey("PATH")).toBe(false);
    expect(validateCredentialKey("")).toBe(false);
  });

  it("accepts valid credential values", () => {
    expect(validateCredentialValue("abc123!@#$%")).toBe(true);
    expect(validateCredentialValue("simple-key")).toBe(true);
  });

  it("rejects credential values with newlines", () => {
    expect(validateCredentialValue("abc\n123")).toBe(false);
    expect(validateCredentialValue("abc\r123")).toBe(false);
  });

  it("rejects credential values with quotes", () => {
    expect(validateCredentialValue('abc"123')).toBe(false);
  });

  it("rejects credential values with backslashes", () => {
    expect(validateCredentialValue("abc\\123")).toBe(false);
  });
});

// ── Notify server logic ──────────────────────────────────────────────────────

describe("notification server", () => {
  const API_TOKEN = "test-token-123";
  let notifyServer;

  beforeEach(async () => {
    const notifications = [];
    notifyServer = http.createServer((req, res) => {
      if (req.method !== "POST" || req.url !== "/notify") {
        res.writeHead(404);
        res.end();
        return;
      }

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
        if (bodySize > 10240) {
          req.destroy();
          return;
        }
        body += chunk;
      });
      req.on("end", () => {
        try {
          const parsed = JSON.parse(body);
          notifications.push(parsed);
        } catch {
          // ignore
        }
        res.writeHead(200);
        res.end("ok");
      });
    });
    await new Promise((r) => notifyServer.listen(0, "127.0.0.1", r));
    notifyServer._notifications = notifications;
  });

  afterEach(() => {
    notifyServer?.close();
  });

  it("rejects requests without valid token", async () => {
    const port = notifyServer.address().port;
    const res = await fetch(`http://127.0.0.1:${port}/notify`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": "wrong-token" },
      body: JSON.stringify({ title: "Test", body: "test" }),
    });
    expect(res.status).toBe(401);
  });

  it("accepts notifications with valid token", async () => {
    const port = notifyServer.address().port;
    const res = await fetch(`http://127.0.0.1:${port}/notify`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": API_TOKEN },
      body: JSON.stringify({ title: "Backup Done", body: "500 files" }),
    });
    expect(res.status).toBe(200);
    expect(notifyServer._notifications).toHaveLength(1);
    expect(notifyServer._notifications[0].title).toBe("Backup Done");
  });

  it("returns 404 for non-notify routes", async () => {
    const port = notifyServer.address().port;
    const res = await fetch(`http://127.0.0.1:${port}/other`, { method: "POST" });
    expect(res.status).toBe(404);
  });

  it("returns 404 for GET requests", async () => {
    const port = notifyServer.address().port;
    const res = await fetch(`http://127.0.0.1:${port}/notify`);
    expect(res.status).toBe(404);
  });
});

// ── Preload bridge behavioral tests ─────────────────────────────────────────
//
// Instead of reading preload.js as a text file and checking for substrings,
// we mock electron's contextBridge and ipcRenderer, then evaluate preload.js
// so the actual code runs and registers real methods via exposeInMainWorld.
//

describe("preload bridge API surface", () => {
  let exposedApi;
  let mockIpcRenderer;

  beforeEach(() => {
    exposedApi = null;

    // Track ipcRenderer.on registrations so we can verify event listeners
    const onListeners = {};

    mockIpcRenderer = {
      invoke: vi.fn().mockResolvedValue("mock-result"),
      on: vi.fn((channel, handler) => {
        onListeners[channel] = handler;
      }),
      removeListener: vi.fn(),
    };

    const mockContextBridge = {
      exposeInMainWorld: vi.fn((apiKey, api) => {
        exposedApi = { key: apiKey, api };
      }),
    };

    // Build a sandboxed require that intercepts "electron" imports
    const preloadPath = path.join(process.cwd(), "electron", "preload.js");
    const preloadSrc = fs.readFileSync(preloadPath, "utf8");

    // Create a module-scoped sandbox with mocked electron
    const Module = createRequire(import.meta.url);
    const moduleObj = { exports: {} };
    const wrappedFn = new Function(
      "require",
      "module",
      "exports",
      "__filename",
      "__dirname",
      preloadSrc
    );

    const fakeRequire = (id) => {
      if (id === "electron") {
        return {
          contextBridge: mockContextBridge,
          ipcRenderer: mockIpcRenderer,
        };
      }
      return Module(id);
    };

    wrappedFn(fakeRequire, moduleObj, moduleObj.exports, preloadPath, path.dirname(preloadPath));
  });

  it('registers the API under "ghostbackup" namespace', () => {
    expect(exposedApi).not.toBeNull();
    expect(exposedApi.key).toBe("ghostbackup");
  });

  // All methods that should be exposed on window.ghostbackup
  const expectedMethods = [
    "openDirectory",
    "openFile",
    "openInExplorer",
    "saveCredential",
    "credentialStatus",
    "apiUrl",
    "version",
    "author",
    "getApiToken",
    "backendStatus",
    "notify",
    "onBackendReady",
    "onBackendCrashed",
    "onAlertNew",
  ];

  for (const method of expectedMethods) {
    it(`exposes ${method} as a function`, () => {
      expect(exposedApi.api).toHaveProperty(method);
      expect(typeof exposedApi.api[method]).toBe("function");
    });
  }

  it("does not expose unexpected methods", () => {
    const actualKeys = Object.keys(exposedApi.api).sort();
    expect(actualKeys).toEqual([...expectedMethods].sort());
  });

  // Verify each invoke-based method calls the correct IPC channel with args
  const invokeMethodChannelMap = [
    { method: "openDirectory", channel: "dialog:open-directory", args: [], expectedArgs: [] },
    {
      method: "openFile",
      channel: "dialog:open-file",
      args: [[{ name: "YAML", extensions: ["yaml"] }]],
      expectedArgs: [[{ name: "YAML", extensions: ["yaml"] }]],
    },
    {
      method: "openInExplorer",
      channel: "shell:open-path",
      args: ["/some/path"],
      expectedArgs: ["/some/path"],
    },
    {
      method: "saveCredential",
      channel: "credentials:save",
      args: ["MY_KEY", "MY_VAL"],
      expectedArgs: [{ key: "MY_KEY", value: "MY_VAL" }],
    },
    { method: "credentialStatus", channel: "credentials:status", args: [], expectedArgs: [] },
    { method: "apiUrl", channel: "app:api-url", args: [], expectedArgs: [] },
    { method: "version", channel: "app:version", args: [], expectedArgs: [] },
    { method: "author", channel: "app:author", args: [], expectedArgs: [] },
    { method: "getApiToken", channel: "app:api-token", args: [], expectedArgs: [] },
    { method: "backendStatus", channel: "backend:status", args: [], expectedArgs: [] },
    {
      method: "notify",
      channel: "notify",
      args: ["Title", "Body"],
      expectedArgs: [{ title: "Title", body: "Body" }],
    },
  ];

  for (const { method, channel, args, expectedArgs } of invokeMethodChannelMap) {
    it(`${method}() invokes IPC channel "${channel}" with correct arguments`, async () => {
      mockIpcRenderer.invoke.mockClear();
      await exposedApi.api[method](...args);
      expect(mockIpcRenderer.invoke).toHaveBeenCalledTimes(1);
      expect(mockIpcRenderer.invoke.mock.calls[0][0]).toBe(channel);
      // Check remaining args (after channel name)
      const passedArgs = mockIpcRenderer.invoke.mock.calls[0].slice(1);
      expect(passedArgs).toEqual(expectedArgs);
    });
  }

  // Verify event-listener methods register on correct channels and return unsubscribe fns
  const listenerMethods = [
    { method: "onBackendReady", channel: "backend:ready" },
    { method: "onBackendCrashed", channel: "backend:crashed" },
    { method: "onAlertNew", channel: "alert:new" },
  ];

  for (const { method, channel } of listenerMethods) {
    it(`${method}() registers listener on "${channel}" and returns unsubscribe`, () => {
      mockIpcRenderer.on.mockClear();
      mockIpcRenderer.removeListener.mockClear();

      const callback = vi.fn();
      const unsubscribe = exposedApi.api[method](callback);

      expect(mockIpcRenderer.on).toHaveBeenCalledTimes(1);
      expect(mockIpcRenderer.on.mock.calls[0][0]).toBe(channel);
      expect(typeof mockIpcRenderer.on.mock.calls[0][1]).toBe("function");

      // Simulate an event from main process
      const handler = mockIpcRenderer.on.mock.calls[0][1];
      handler({}, { some: "data" });
      expect(callback).toHaveBeenCalledWith({ some: "data" });

      // Unsubscribe should call removeListener
      expect(typeof unsubscribe).toBe("function");
      unsubscribe();
      expect(mockIpcRenderer.removeListener).toHaveBeenCalledWith(channel, handler);
    });
  }
});

// ── IPC handler behavioral tests ────────────────────────────────────────────
//
// Instead of string-matching main.js source for "ipcMain.handle", we mock
// Electron's module system, load main.js's registerIpcHandlers function, and
// verify that handlers are registered for all expected channels with correct
// behavior.
//

describe("main.js IPC handler registration", () => {
  let registeredHandlers;
  let mockDialog;
  let mockShell;
  let mockApp;

  beforeEach(() => {
    registeredHandlers = {};

    const mockIpcMain = {
      handle: vi.fn((channel, handler) => {
        registeredHandlers[channel] = handler;
      }),
    };

    mockDialog = {
      showOpenDialog: vi.fn().mockResolvedValue({ canceled: false, filePaths: ["/picked/dir"] }),
      showErrorBox: vi.fn(),
    };

    mockShell = {
      openPath: vi.fn().mockResolvedValue(""),
      openExternal: vi.fn(),
    };

    mockApp = {
      requestSingleInstanceLock: vi.fn().mockReturnValue(true),
      getVersion: vi.fn().mockReturnValue("9.4.0"),
      on: vi.fn(),
      whenReady: vi.fn().mockReturnValue(new Promise(() => {})), // never resolve to prevent lifecycle
      isQuitting: false,
      quit: vi.fn(),
    };

    const mockBrowserWindow = vi.fn();
    mockBrowserWindow.getAllWindows = vi.fn().mockReturnValue([]);

    const mockNotification = vi.fn().mockImplementation(() => ({
      show: vi.fn(),
    }));
    mockNotification.isSupported = vi.fn().mockReturnValue(true);

    const mockNativeImage = {
      createFromPath: vi.fn().mockReturnValue({ resize: vi.fn().mockReturnValue({}) }),
      createEmpty: vi.fn().mockReturnValue({}),
    };

    const mockTray = vi.fn().mockImplementation(() => ({
      setToolTip: vi.fn(),
      setContextMenu: vi.fn(),
      on: vi.fn(),
      destroy: vi.fn(),
    }));

    const mockMenu = {
      buildFromTemplate: vi.fn().mockReturnValue({}),
    };

    const mockSession = {
      defaultSession: {
        webRequest: {
          onHeadersReceived: vi.fn(),
        },
      },
    };

    const mainPath = path.join(process.cwd(), "electron", "main.js");
    const mainSrc = fs.readFileSync(mainPath, "utf8");

    // Extract only the registerIpcHandlers function to avoid side effects.
    // We find the function body and evaluate it with mocked dependencies.
    const fnStart = mainSrc.indexOf("function registerIpcHandlers()");
    const fnBodyStart = mainSrc.indexOf("{", fnStart);

    // Find the matching closing brace by counting braces
    let depth = 0;
    let fnEnd = fnBodyStart;
    for (let i = fnBodyStart; i < mainSrc.length; i++) {
      if (mainSrc[i] === "{") depth++;
      if (mainSrc[i] === "}") depth--;
      if (depth === 0) {
        fnEnd = i + 1;
        break;
      }
    }

    const fnBody = mainSrc.slice(fnStart, fnEnd);

    // Build a context with all the variables the function references
    const context = new Function(
      "ipcMain",
      "dialog",
      "shell",
      "app",
      "Notification",
      "mainWindow",
      "backendReady",
      "pythonProcess",
      "API_URL",
      "API_TOKEN",
      "ENV_FILE",
      "ROOT_DIR",
      "fs",
      "path",
      "process",
      "isRegisteredInStartup",
      "registerWindowsStartup",
      "unregisterWindowsStartup",
      `
      ${fnBody}
      registerIpcHandlers();
      `
    );

    const tmpDir = path.join("/tmp", "gb-ipc-test-" + Date.now());
    fs.mkdirSync(tmpDir, { recursive: true });

    context(
      mockIpcMain,
      mockDialog,
      mockShell,
      mockApp,
      mockNotification,
      null, // mainWindow
      false, // backendReady
      null, // pythonProcess
      "http://127.0.0.1:8765",
      "test-api-token",
      path.join(tmpDir, ".env.local"),
      tmpDir,
      fs,
      path,
      process,
      vi.fn().mockReturnValue(false), // isRegisteredInStartup
      vi.fn(), // registerWindowsStartup
      vi.fn() // unregisterWindowsStartup
    );

    // Store tmpDir for cleanup
    registeredHandlers._tmpDir = tmpDir;
  });

  afterEach(() => {
    if (registeredHandlers._tmpDir) {
      fs.rmSync(registeredHandlers._tmpDir, { recursive: true, force: true });
    }
  });

  const expectedChannels = [
    "dialog:open-directory",
    "dialog:open-file",
    "credentials:save",
    "credentials:status",
    "shell:open-path",
    "app:api-url",
    "app:version",
    "app:author",
    "app:api-token",
    "backend:status",
    "notify",
    "startup:get",
    "startup:set",
  ];

  for (const channel of expectedChannels) {
    it(`registers handler for "${channel}"`, () => {
      expect(registeredHandlers).toHaveProperty(channel);
      expect(typeof registeredHandlers[channel]).toBe("function");
    });
  }

  it("dialog:open-directory calls dialog.showOpenDialog", async () => {
    const result = await registeredHandlers["dialog:open-directory"]({});
    expect(mockDialog.showOpenDialog).toHaveBeenCalled();
    expect(result).toBe("/picked/dir");
  });

  it("dialog:open-directory returns null when canceled", async () => {
    mockDialog.showOpenDialog.mockResolvedValueOnce({ canceled: true, filePaths: [] });
    const result = await registeredHandlers["dialog:open-directory"]({});
    expect(result).toBeNull();
  });

  it("dialog:open-file calls dialog.showOpenDialog with filters", async () => {
    const filters = [{ name: "JSON", extensions: ["json"] }];
    mockDialog.showOpenDialog.mockResolvedValueOnce({ canceled: false, filePaths: ["/a/b.json"] });
    const result = await registeredHandlers["dialog:open-file"]({}, filters);
    expect(result).toBe("/a/b.json");
    const callArgs = mockDialog.showOpenDialog.mock.calls[0][1];
    expect(callArgs.filters).toEqual(filters);
  });

  it("dialog:open-file uses YAML filter as default", async () => {
    mockDialog.showOpenDialog.mockResolvedValueOnce({ canceled: false, filePaths: ["/a/b.yaml"] });
    await registeredHandlers["dialog:open-file"]({}, undefined);
    const callArgs = mockDialog.showOpenDialog.mock.calls[0][1];
    expect(callArgs.filters).toEqual([{ name: "YAML", extensions: ["yaml", "yml"] }]);
  });

  it("app:api-url returns the API URL", async () => {
    const result = await registeredHandlers["app:api-url"]({});
    expect(result).toBe("http://127.0.0.1:8765");
  });

  it("app:version returns the app version", async () => {
    const result = await registeredHandlers["app:version"]({});
    expect(result).toBe("9.4.0");
  });

  it("app:api-token returns the API token", async () => {
    const result = await registeredHandlers["app:api-token"]({});
    expect(result).toBe("test-api-token");
  });

  it("backend:status returns ready state and url", async () => {
    const result = await registeredHandlers["backend:status"]({});
    expect(result).toEqual({ ready: false, url: "http://127.0.0.1:8765", pid: null });
  });

  it("credentials:save rejects unknown keys", async () => {
    const result = await registeredHandlers["credentials:save"](
      {},
      { key: "UNKNOWN", value: "abc" }
    );
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/[Uu]nknown/);
  });

  it("credentials:save accepts allowed keys and writes .env.local", async () => {
    const result = await registeredHandlers["credentials:save"](
      {},
      { key: "GHOSTBACKUP_ENCRYPTION_KEY", value: "testkey123" }
    );
    expect(result.success).toBe(true);
    const envContent = fs.readFileSync(path.join(registeredHandlers._tmpDir, ".env.local"), "utf8");
    expect(envContent).toContain('GHOSTBACKUP_ENCRYPTION_KEY="testkey123"');
  });

  it("credentials:save rejects values with dangerous characters", async () => {
    const result = await registeredHandlers["credentials:save"](
      {},
      { key: "GHOSTBACKUP_ENCRYPTION_KEY", value: "bad\nvalue" }
    );
    expect(result.error).toBeTruthy();
  });

  it("credentials:status returns boolean status for each credential", async () => {
    const result = await registeredHandlers["credentials:status"]({});
    expect(result).toHaveProperty("smtp_password");
    expect(result).toHaveProperty("encryption_key");
    expect(result).toHaveProperty("hkdf_salt");
    expect(typeof result.smtp_password).toBe("boolean");
  });

  it("shell:open-path rejects empty paths", async () => {
    const result = await registeredHandlers["shell:open-path"]({}, "");
    expect(result).toBeUndefined();
    expect(mockShell.openPath).not.toHaveBeenCalled();
  });

  it("shell:open-path rejects non-existent paths", async () => {
    const result = await registeredHandlers["shell:open-path"]({}, "/nonexistent/xyz");
    expect(result).toEqual({ error: "Path not found" });
  });

  it("shell:open-path opens valid directories", async () => {
    await registeredHandlers["shell:open-path"]({}, registeredHandlers._tmpDir);
    expect(mockShell.openPath).toHaveBeenCalledWith(registeredHandlers._tmpDir);
  });

  it("startup:get returns a boolean", async () => {
    const result = await registeredHandlers["startup:get"]({});
    expect(typeof result).toBe("boolean");
  });

  it("startup:set returns success status", async () => {
    const result = await registeredHandlers["startup:set"]({}, true);
    expect(result).toHaveProperty("success");
  });
});

// ── CSP header behavioral tests ─────────────────────────────────────────────
//
// Instead of string-matching, we extract and invoke the onHeadersReceived
// callback from main.js's createWindow function to verify actual CSP headers.
//

describe("CSP configuration", () => {
  let cspCallback;

  beforeEach(() => {
    // We simulate what createWindow does: it calls
    //   session.webRequest.onHeadersReceived(callback)
    // and that callback modifies response headers.
    //
    // Extract the production CSP callback from main.js source.
    const mainPath = path.join(process.cwd(), "electron", "main.js");
    const mainSrc = fs.readFileSync(mainPath, "utf8");

    // Find the production (non-dev) onHeadersReceived block.
    // The production block is in the `else` branch after the IS_DEV block.
    // We look for the second onHeadersReceived callback.
    const firstIdx = mainSrc.indexOf("onHeadersReceived(");
    const secondIdx = mainSrc.indexOf("onHeadersReceived(", firstIdx + 1);

    // Extract from the opening paren of the callback to its closing
    const cbStart = mainSrc.indexOf("(", secondIdx + "onHeadersReceived".length);

    let depth = 0;
    let cbEnd = cbStart;
    for (let i = cbStart; i < mainSrc.length; i++) {
      if (mainSrc[i] === "(") depth++;
      if (mainSrc[i] === ")") depth--;
      if (depth === 0) {
        cbEnd = i + 1;
        break;
      }
    }

    // The content between the parens is the callback function
    // Format: (details, callback) => { ... }
    const callbackSrc = mainSrc.slice(cbStart + 1, cbEnd - 1).trim();

    // Wrap it so we can call it
    cspCallback = new Function("return " + callbackSrc)();
  });

  it("sets Content-Security-Policy header in the response", () => {
    let capturedHeaders = null;
    const mockCallback = (obj) => {
      capturedHeaders = obj;
    };

    cspCallback({ responseHeaders: { "X-Existing": ["keep"] } }, mockCallback);

    expect(capturedHeaders).not.toBeNull();
    expect(capturedHeaders.responseHeaders).toHaveProperty("Content-Security-Policy");
  });

  it("preserves existing response headers", () => {
    let capturedHeaders = null;
    const mockCallback = (obj) => {
      capturedHeaders = obj;
    };

    cspCallback({ responseHeaders: { "X-Custom": ["myval"] } }, mockCallback);

    expect(capturedHeaders.responseHeaders["X-Custom"]).toEqual(["myval"]);
  });

  it("restricts default-src to 'self'", () => {
    let capturedHeaders = null;
    const mockCallback = (obj) => {
      capturedHeaders = obj;
    };
    cspCallback({ responseHeaders: {} }, mockCallback);

    const csp = capturedHeaders.responseHeaders["Content-Security-Policy"][0];
    expect(csp).toMatch(/default-src\s+'self'/);
  });

  it("restricts script-src to 'self'", () => {
    let capturedHeaders = null;
    const mockCallback = (obj) => {
      capturedHeaders = obj;
    };
    cspCallback({ responseHeaders: {} }, mockCallback);

    const csp = capturedHeaders.responseHeaders["Content-Security-Policy"][0];
    expect(csp).toMatch(/script-src\s+'self'/);
  });

  it("allows connect-src for local backend", () => {
    let capturedHeaders = null;
    const mockCallback = (obj) => {
      capturedHeaders = obj;
    };
    cspCallback({ responseHeaders: {} }, mockCallback);

    const csp = capturedHeaders.responseHeaders["Content-Security-Policy"][0];
    expect(csp).toMatch(/connect-src\s+.*127\.0\.0\.1/);
  });

  it("allows img-src self and data URIs", () => {
    let capturedHeaders = null;
    const mockCallback = (obj) => {
      capturedHeaders = obj;
    };
    cspCallback({ responseHeaders: {} }, mockCallback);

    const csp = capturedHeaders.responseHeaders["Content-Security-Policy"][0];
    expect(csp).toMatch(/img-src\s+'self'\s+data:/);
  });

  it("CSP is a single string value in an array", () => {
    let capturedHeaders = null;
    const mockCallback = (obj) => {
      capturedHeaders = obj;
    };
    cspCallback({ responseHeaders: {} }, mockCallback);

    const cspArr = capturedHeaders.responseHeaders["Content-Security-Policy"];
    expect(Array.isArray(cspArr)).toBe(true);
    expect(cspArr).toHaveLength(1);
    expect(typeof cspArr[0]).toBe("string");
  });
});

// ── Window security settings ─────────────────────────────────────────────────
//
// Verify that the BrowserWindow webPreferences in main.js use secure defaults.
//

describe("BrowserWindow security settings", () => {
  const mainPath = path.join(process.cwd(), "electron", "main.js");
  const mainSrc = fs.readFileSync(mainPath, "utf8");

  // Extract the webPreferences object from the createWindow function
  const wpStart = mainSrc.indexOf("webPreferences:");
  const braceStart = mainSrc.indexOf("{", wpStart);
  let depth = 0;
  let braceEnd = braceStart;
  for (let i = braceStart; i < mainSrc.length; i++) {
    if (mainSrc[i] === "{") depth++;
    if (mainSrc[i] === "}") depth--;
    if (depth === 0) {
      braceEnd = i + 1;
      break;
    }
  }
  const wpSrc = mainSrc.slice(braceStart, braceEnd);

  // Parse the object using Function (it references __dirname and path, so provide them)
  const webPrefs = new Function("__dirname", "path", `return (${wpSrc})`)(
    path.join(process.cwd(), "electron"),
    path
  );

  it("disables nodeIntegration", () => {
    expect(webPrefs.nodeIntegration).toBe(false);
  });

  it("enables contextIsolation", () => {
    expect(webPrefs.contextIsolation).toBe(true);
  });

  it("enables sandbox", () => {
    expect(webPrefs.sandbox).toBe(true);
  });

  it("enables webSecurity", () => {
    expect(webPrefs.webSecurity).toBe(true);
  });

  it("sets preload script path", () => {
    expect(webPrefs.preload).toMatch(/preload\.js$/);
  });
});

// ── Env file writing (credential save) ──────────────────────────────────────

describe("credential persistence to .env.local", () => {
  const tmpDir = path.join("/tmp", "gb-cred-test-" + Date.now());
  const envFile = path.join(tmpDir, ".env.local");

  beforeEach(() => {
    fs.mkdirSync(tmpDir, { recursive: true });
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  function saveCredential(envFilePath, key, value) {
    const safeValue = value.replace(/[\r\n"\\]/g, "");
    if (safeValue !== value) return { error: "Invalid characters" };
    let envContent = fs.existsSync(envFilePath) ? fs.readFileSync(envFilePath, "utf8") : "";
    const regex = new RegExp(`^${key}=.*$`, "m");
    if (regex.test(envContent)) {
      envContent = envContent.replace(regex, `${key}="${safeValue}"`);
    } else {
      envContent += `\n${key}="${safeValue}"`;
    }
    fs.writeFileSync(envFilePath, envContent.trim() + "\n", { mode: 0o600 });
    return { success: true };
  }

  it("creates .env.local if it doesn't exist", () => {
    saveCredential(envFile, "GHOSTBACKUP_ENCRYPTION_KEY", "abc123");
    expect(fs.existsSync(envFile)).toBe(true);
    const content = fs.readFileSync(envFile, "utf8");
    expect(content).toContain('GHOSTBACKUP_ENCRYPTION_KEY="abc123"');
  });

  it("updates existing key in .env.local", () => {
    fs.writeFileSync(envFile, 'GHOSTBACKUP_ENCRYPTION_KEY="old"\n');
    saveCredential(envFile, "GHOSTBACKUP_ENCRYPTION_KEY", "new-key");
    const content = fs.readFileSync(envFile, "utf8");
    expect(content).toContain('GHOSTBACKUP_ENCRYPTION_KEY="new-key"');
    expect(content).not.toContain("old");
  });

  it("appends new key without overwriting existing keys", () => {
    fs.writeFileSync(envFile, 'EXISTING_KEY="keep"\n');
    saveCredential(envFile, "GHOSTBACKUP_HKDF_SALT", "salt123");
    const content = fs.readFileSync(envFile, "utf8");
    expect(content).toContain('EXISTING_KEY="keep"');
    expect(content).toContain('GHOSTBACKUP_HKDF_SALT="salt123"');
  });

  it("rejects values with invalid characters", () => {
    const result = saveCredential(envFile, "KEY", "bad\nvalue");
    expect(result.error).toBeTruthy();
  });

  it("sets restrictive file permissions (mode 0o600)", () => {
    saveCredential(envFile, "KEY", "value");
    const stat = fs.statSync(envFile);
    // 0o600 = owner read+write only
    expect(stat.mode & 0o777).toBe(0o600);
  });
});
