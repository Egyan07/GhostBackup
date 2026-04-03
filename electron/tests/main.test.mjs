/**
 * main.test.mjs — Electron main process unit tests
 *
 * Tests the extractable pure/testable logic from electron/main.js.
 * Since main.js has import-time side effects (app.requestSingleInstanceLock()),
 * we test by re-implementing key functions with the same logic and mocking
 * the Electron APIs they depend on.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import fs from "fs";
import path from "path";
import http from "http";
import crypto from "crypto";

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
    const val = trimmed.slice(idx + 1).trim().replace(/^["']|["']$/g, "");
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
    fs.writeFileSync(envFile, 'API_KEY="secret123"\nPATH=\'hello\'\n');
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
    const start    = Date.now();
    let   attempts = 0;
    const delays   = [50, 100, 200];

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
      req.setTimeout(200, () => { req.destroy(); scheduleRetry(); });
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
    await new Promise(r => server.listen(0, "127.0.0.1", r));
    const port = server.address().port;

    const result = await waitForBackend(`http://127.0.0.1:${port}/health`);
    expect(result.attempts).toBeGreaterThanOrEqual(1);
  });

  it("rejects after timeout when server never responds 200", async () => {
    server = http.createServer((_, res) => {
      res.writeHead(503);
      res.end("not ready");
    });
    await new Promise(r => server.listen(0, "127.0.0.1", r));
    const port = server.address().port;

    await expect(
      waitForBackend(`http://127.0.0.1:${port}/health`, 500)
    ).rejects.toThrow(/did not become ready/);
  });

  it("rejects when no server is running", async () => {
    await expect(
      waitForBackend("http://127.0.0.1:19999/health", 500)
    ).rejects.toThrow(/did not become ready/);
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
    await new Promise(r => server.listen(0, "127.0.0.1", r));
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
        if (bodySize > 10240) { req.destroy(); return; }
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
    await new Promise(r => notifyServer.listen(0, "127.0.0.1", r));
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

// ── Preload bridge structure ────────────────────────────────────────────────

describe("preload bridge API surface", () => {
  // Verify that the preload script exposes the expected set of methods
  // by reading the file and checking for the IPC channel mappings

  const preloadSrc = fs.readFileSync(
    path.join(process.cwd(), "electron", "preload.js"),
    "utf8"
  );

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
    it(`exposes ${method} method`, () => {
      expect(preloadSrc).toContain(method);
    });
  }

  const expectedChannels = [
    "dialog:open-directory",
    "dialog:open-file",
    "shell:open-path",
    "credentials:save",
    "credentials:status",
    "app:api-url",
    "app:version",
    "app:author",
    "app:api-token",
    "backend:status",
    "notify",
    "backend:ready",
    "backend:crashed",
    "alert:new",
  ];

  for (const channel of expectedChannels) {
    it(`maps to IPC channel "${channel}"`, () => {
      expect(preloadSrc).toContain(channel);
    });
  }
});

// ── IPC handler channel coverage ─────────────────────────────────────────────

describe("main.js IPC handler registration", () => {
  const mainSrc = fs.readFileSync(
    path.join(process.cwd(), "electron", "main.js"),
    "utf8"
  );

  const expectedHandlers = [
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

  for (const handler of expectedHandlers) {
    it(`registers handler for "${handler}"`, () => {
      expect(mainSrc).toContain(`"${handler}"`);
    });
  }
});

// ── CSP headers ──────────────────────────────────────────────────────────────

describe("CSP configuration", () => {
  const mainSrc = fs.readFileSync(
    path.join(process.cwd(), "electron", "main.js"),
    "utf8"
  );

  it("sets Content-Security-Policy headers", () => {
    expect(mainSrc).toContain("Content-Security-Policy");
  });

  it("restricts default-src to self", () => {
    expect(mainSrc).toContain("default-src 'self'");
  });

  it("disables nodeIntegration", () => {
    expect(mainSrc).toContain("nodeIntegration:  false");
  });

  it("enables contextIsolation", () => {
    expect(mainSrc).toContain("contextIsolation: true");
  });

  it("enables sandbox", () => {
    expect(mainSrc).toContain("sandbox:          true");
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
    let envContent = fs.existsSync(envFilePath)
      ? fs.readFileSync(envFilePath, "utf8")
      : "";
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
