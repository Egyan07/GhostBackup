/**
 * csp.test.mjs — Behavioral tests for the fine-grained CSP directives
 * in the production onHeadersReceived callback of electron/main.js.
 *
 * Extracts and invokes the actual callback to verify each directive
 * is present and correctly configured.
 */

import { describe, it, expect, beforeEach } from "vitest";
import fs from "fs";
import path from "path";

describe("Fine-grained CSP directives (production)", () => {
  let cspCallback;
  let cspValue;

  beforeEach(() => {
    const mainPath = path.join(process.cwd(), "electron", "main.js");
    const mainSrc = fs.readFileSync(mainPath, "utf8");

    // Find the production (second) onHeadersReceived callback
    const firstIdx = mainSrc.indexOf("onHeadersReceived(");
    const secondIdx = mainSrc.indexOf("onHeadersReceived(", firstIdx + 1);
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

    const callbackSrc = mainSrc.slice(cbStart + 1, cbEnd - 1).trim();
    cspCallback = new Function("return " + callbackSrc)();

    // Capture the CSP header value
    cspCallback({ responseHeaders: {} }, (obj) => {
      cspValue = obj.responseHeaders["Content-Security-Policy"][0];
    });
  });

  it("includes default-src 'self'", () => {
    expect(cspValue).toMatch(/default-src\s+'self'/);
  });

  it("includes script-src 'self' without unsafe-inline", () => {
    expect(cspValue).toMatch(/script-src\s+'self'/);
    // Production CSP should NOT allow unsafe-inline for scripts
    const scriptDirective = cspValue.match(/script-src\s+[^;]+/)[0];
    expect(scriptDirective).not.toContain("unsafe-inline");
  });

  it("includes style-src 'self' 'unsafe-inline'", () => {
    expect(cspValue).toMatch(/style-src\s+'self'\s+'unsafe-inline'/);
  });

  it("includes img-src 'self' data:", () => {
    expect(cspValue).toMatch(/img-src\s+'self'\s+data:/);
  });

  it("includes font-src 'self'", () => {
    expect(cspValue).toMatch(/font-src\s+'self'/);
  });

  it("includes connect-src with localhost:8765 and 127.0.0.1:8765", () => {
    expect(cspValue).toMatch(/connect-src\s+[^;]*http:\/\/localhost:8765/);
    expect(cspValue).toMatch(/connect-src\s+[^;]*http:\/\/127\.0\.0\.1:8765/);
  });

  it("includes connect-src 'self'", () => {
    expect(cspValue).toMatch(/connect-src\s+'self'/);
  });

  it("includes object-src 'none'", () => {
    expect(cspValue).toMatch(/object-src\s+'none'/);
  });

  it("includes base-uri 'self'", () => {
    expect(cspValue).toMatch(/base-uri\s+'self'/);
  });

  it("includes form-action 'self'", () => {
    expect(cspValue).toMatch(/form-action\s+'self'/);
  });

  it("includes frame-ancestors 'none'", () => {
    expect(cspValue).toMatch(/frame-ancestors\s+'none'/);
  });

  it("does not allow wildcard connect-src", () => {
    const connectDirective = cspValue.match(/connect-src\s+[^;]+/)[0];
    expect(connectDirective).not.toContain("*");
  });

  it("does not allow unsafe-eval anywhere", () => {
    expect(cspValue).not.toContain("unsafe-eval");
  });

  it("preserves existing response headers when adding CSP", () => {
    let captured = null;
    cspCallback({ responseHeaders: { "X-Custom": ["value1"], "X-Other": ["value2"] } }, (obj) => {
      captured = obj;
    });
    expect(captured.responseHeaders["X-Custom"]).toEqual(["value1"]);
    expect(captured.responseHeaders["X-Other"]).toEqual(["value2"]);
    expect(captured.responseHeaders["Content-Security-Policy"]).toBeDefined();
  });
});
