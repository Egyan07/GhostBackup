/**
 * api-client.test.js — Unit tests for src/api-client.js
 *
 * Tests the request wrapper, error handling, ApiError class,
 * and token caching behaviour without hitting a real server.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import apiDefault, { ApiError, clearTokenCache, request, api } from "../api-client";

beforeEach(() => {
  clearTokenCache();

  global.window = {
    ghostbackup: {
      apiUrl: vi.fn().mockResolvedValue("http://127.0.0.1:8765"),
      getApiToken: vi.fn().mockResolvedValue("test-token-abc"),
    },
  };

  global.fetch = vi.fn();
});

describe("ApiError", () => {
  it("has name set to 'ApiError' for instanceof across module boundaries", () => {
    const err = new ApiError(404, "not found");
    expect(err.name).toBe("ApiError");
  });

  it("is an instance of Error", () => {
    expect(new ApiError(500, "oops") instanceof Error).toBe(true);
  });

  it("stores status code", () => {
    expect(new ApiError(401, "unauthorized").status).toBe(401);
  });

  it("stores message", () => {
    expect(new ApiError(404, "not found").message).toBe("not found");
  });

  it("stores optional code", () => {
    const err = new ApiError(409, "Backup already in progress", "GB-E020");
    expect(err.code).toBe("GB-E020");
  });

  it("stores optional fix", () => {
    const err = new ApiError(409, "Backup already in progress", "GB-E020", "Wait for the current run to finish");
    expect(err.fix).toBe("Wait for the current run to finish");
  });

  it("code defaults to null when not provided", () => {
    expect(new ApiError(500, "error").code).toBeNull();
  });

  it("fix defaults to null when not provided", () => {
    expect(new ApiError(500, "error").fix).toBeNull();
  });
});

describe("request() — success", () => {
  it("calls the Electron-provided base URL", async () => {
    global.window.ghostbackup.apiUrl.mockResolvedValueOnce("http://127.0.0.1:9876");
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({ status: "ok" }),
    });

    await request("GET", "/health");

    expect(global.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:9876/health",
      expect.any(Object)
    );
  });

  it("falls back to the default base URL without Electron apiUrl", async () => {
    delete global.window.ghostbackup.apiUrl;
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({ status: "ok" }),
    });

    await request("GET", "/health");

    expect(global.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/health",
      expect.any(Object)
    );
  });

  it("sends X-API-Key header with the token", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({}),
    });

    await request("GET", "/health");

    const headers = global.fetch.mock.calls[0][1].headers;
    expect(headers["X-API-Key"]).toBe("test-token-abc");
  });

  it("caches token — only calls getApiToken once across multiple requests", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({}),
    });

    await request("GET", "/health");
    await request("GET", "/runs");
    await request("GET", "/config");

    expect(global.window.ghostbackup.getApiToken).toHaveBeenCalledTimes(1);
  });

  it("caches the API base URL across requests", async () => {
    global.window.ghostbackup.apiUrl.mockResolvedValue("http://127.0.0.1:9999");
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({}),
    });

    await request("GET", "/health");
    await request("GET", "/runs");

    expect(global.window.ghostbackup.apiUrl).toHaveBeenCalledTimes(1);
  });

  it("clears cached token after clearTokenCache()", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({}),
    });

    await request("GET", "/health");
    clearTokenCache();
    await request("GET", "/health");

    expect(global.window.ghostbackup.getApiToken).toHaveBeenCalledTimes(2);
  });

  it("sets method correctly on POST", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({ message: "started" }),
    });

    await request("POST", "/run/start", { full: false });

    const opts = global.fetch.mock.calls[0][1];
    expect(opts.method).toBe("POST");
  });

  it("serialises body to JSON on POST", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({}),
    });

    await request("POST", "/run/start", { full: true, sources: ["Clients"] });

    const opts = global.fetch.mock.calls[0][1];
    expect(JSON.parse(opts.body)).toEqual({ full: true, sources: ["Clients"] });
  });

  it("does not include body on GET", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({}),
    });

    await request("GET", "/health");

    const opts = global.fetch.mock.calls[0][1];
    expect(opts.body).toBeUndefined();
  });

  it("appends query string params", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ([]),
    });

    await request("GET", "/runs", null, { limit: 10, offset: 0 });

    const url = global.fetch.mock.calls[0][0];
    expect(url).toContain("limit=10");
    expect(url).toContain("offset=0");
  });

  it("omits null query params", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ([]),
    });

    await request("GET", "/runs", null, { limit: 10, offset: null });

    const url = global.fetch.mock.calls[0][0];
    expect(url).not.toContain("offset");
  });

  it("returns null for 204 No Content", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      headers: { get: () => null },
      json: async () => { throw new Error("no body"); },
    });

    const result = await request("DELETE", "/config/sites/old");
    expect(result).toBeNull();
  });
});

describe("request() — errors", () => {
  it("throws ApiError on 401", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      headers: { get: () => null },
      json: async () => ({ detail: "Unauthorized — invalid or missing X-API-Key" }),
    });

    await expect(request("GET", "/runs")).rejects.toBeInstanceOf(ApiError);
  });

  it("sets correct status on ApiError", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: "Not Found",
      headers: { get: () => null },
      json: async () => ({ detail: "Run #999 not found" }),
    });

    try {
      await request("GET", "/runs/999");
    } catch (e) {
      expect(e.status).toBe(404);
    }
  });

  it("uses detail field from JSON error body", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 409,
      statusText: "Conflict",
      headers: { get: () => null },
      json: async () => ({ detail: "A backup run is already in progress" }),
    });

    try {
      await request("POST", "/run/start", {});
    } catch (e) {
      expect(e.message).toContain("already in progress");
    }
  });
});

describe("api convenience object", () => {
  it("api.get() uses GET method", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({ status: "ok" }),
    });

    await api.get("/health");
    expect(global.fetch.mock.calls[0][1].method).toBe("GET");
  });

  it("api.post() uses POST method", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({ ok: true }),
    });

    await api.post("/run/start", { full: true });
    expect(global.fetch.mock.calls[0][1].method).toBe("POST");
  });

  it("api.patch() uses PATCH method", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({ ok: true }),
    });

    await api.patch("/config", { ssd_path: "D:\\Backup" });
    expect(global.fetch.mock.calls[0][1].method).toBe("PATCH");
  });

  it("api.delete() uses DELETE method", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      headers: { get: () => "0" },
      json: async () => null,
    });

    await api.delete("/config/sites/old");
    expect(global.fetch.mock.calls[0][1].method).toBe("DELETE");
  });
});

describe("default export", () => {
  it("exports the same object as named api export", () => {
    expect(apiDefault).toBe(api);
  });
});
