import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

const apiMocks = vi.hoisted(() => ({
  getConfig:           vi.fn(),
  updateSmtp:          vi.fn(),
  sendTestEmail:       vi.fn(),
  runVerify:           vi.fn(),
  runPrune:            vi.fn(),
  resetConfig:         vi.fn(),
  generateEncryptionKey: vi.fn(),
}));

vi.mock("../api-client.js", () => ({
  default: {
    getConfig:             apiMocks.getConfig,
    updateSmtp:            apiMocks.updateSmtp,
    sendTestEmail:         apiMocks.sendTestEmail,
    testSmtp:              vi.fn().mockResolvedValue({}),
    runVerify:             apiMocks.runVerify,
    runPrune:              apiMocks.runPrune,
    resetConfig:           apiMocks.resetConfig,
    generateEncryptionKey: apiMocks.generateEncryptionKey,
    ssdStatus:             vi.fn().mockResolvedValue({ status: "ok" }),
    watcherStatus:         vi.fn().mockResolvedValue({ running: false }),
    watcherStart:          vi.fn().mockResolvedValue({ running: true }),
    watcherStop:           vi.fn().mockResolvedValue({ running: false }),
    updateRetention:       vi.fn().mockResolvedValue({}),
    verifyBackups:         vi.fn().mockResolvedValue({ verified: 0, failed: 0 }),
    drillStatus:           vi.fn().mockResolvedValue({ last_completed: null, days_since_last: null, next_due: null, overdue: false, history: [] }),
    health:                vi.fn().mockResolvedValue({ status: "ok", key_storage: "keyring" }),
  },
}));

import Settings from "../pages/Settings.jsx";

const BASE_CFG = {
  encryption_active: true,
  hkdf_salt_active:  true,
  smtp: { host: "smtp.office365.com", port: 587, user: "backup@example.com", recipients: ["it@example.com"] },
  retention: { daily_days: 365, weekly_days: 2555, compliance_years: 7, guard_days: 7 },
};

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.getConfig.mockResolvedValue(BASE_CFG);
});

describe("Settings — encryption panel", () => {
  it("shows Encryption Active pill when key is set", async () => {
    render(<Settings />);
    expect(await screen.findByText(/Encryption Active/)).toBeTruthy();
  });

  it("shows warning when encryption is inactive", async () => {
    apiMocks.getConfig.mockResolvedValue({ ...BASE_CFG, encryption_active: false });
    render(<Settings />);
    await waitFor(() =>
      expect(screen.getByText(/GHOSTBACKUP_ENCRYPTION_KEY/)).toBeTruthy()
    );
  });

  it("shows HKDF salt warning when salt is not set", async () => {
    apiMocks.getConfig.mockResolvedValue({ ...BASE_CFG, hkdf_salt_active: false });
    render(<Settings />);
    await waitFor(() =>
      expect(screen.getByText(/GHOSTBACKUP_HKDF_SALT/)).toBeTruthy()
    );
  });

  it("does not show HKDF warning when salt is active", async () => {
    render(<Settings />);
    await screen.findByText(/Encryption Active/);
    expect(screen.queryByText(/GHOSTBACKUP_HKDF_SALT/)).toBeNull();
  });
});

describe("Settings — SMTP panel", () => {
  it("renders SMTP host field with existing value", async () => {
    render(<Settings />);
    const inputs = await screen.findAllByDisplayValue("smtp.office365.com");
    expect(inputs.length).toBeGreaterThan(0);
  });

  it("calls testSmtp when test button is clicked", async () => {
    const testSmtpMock = vi.fn().mockResolvedValue({});
    const { default: api } = await import("../api-client.js");
    api.testSmtp = testSmtpMock;
    render(<Settings />);
    const btn = await screen.findByText("Send Test Email");
    fireEvent.click(btn);
    await waitFor(() => expect(testSmtpMock).toHaveBeenCalledTimes(1));
  });
});

describe("Settings — Generate New Key", () => {
  it("renders Generate New Key button", async () => {
    render(<Settings />);
    expect(await screen.findByText("Generate New Key")).toBeTruthy();
  });

  it("calls generateEncryptionKey API on click", async () => {
    apiMocks.generateEncryptionKey.mockResolvedValue({ key: "new-key-abc" });
    render(<Settings />);
    fireEvent.click(await screen.findByText("Generate New Key"));
    await waitFor(() => expect(apiMocks.generateEncryptionKey).toHaveBeenCalledTimes(1));
  });
});
