/**
 * alertbell.test.jsx — Unit tests for AlertBell component
 *
 * Covers: rendering, notification badge, panel open/close, dismiss, dismiss all,
 * alert levels, polling, custom event listener.
 *
 * Run with:  npm test
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ---------------------------------------------------------------------------
// Hoisted API mock
// ---------------------------------------------------------------------------
const apiMocks = vi.hoisted(() => ({
  getAlerts:       vi.fn(),
  dismissAlert:    vi.fn(),
  dismissAllAlerts: vi.fn(),
}));

vi.mock("../api-client", () => ({
  default: {
    getAlerts:        apiMocks.getAlerts,
    dismissAlert:     apiMocks.dismissAlert,
    dismissAllAlerts: apiMocks.dismissAllAlerts,
  },
}));

import AlertBell from "../components/AlertBell";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const EMPTY_ALERTS = { alerts: [], unread_count: 0 };

const TWO_ALERTS = {
  alerts: [
    { id: 1, level: "info",  title: "Backup completed", body: "Run #10 finished successfully", ts: "2025-06-01T10:00:00Z", run_id: 10, dismissed: false },
    { id: 2, level: "error", title: "SSD disconnected", body: "Target drive not found",        ts: "2025-06-01T11:00:00Z", run_id: null, dismissed: false },
  ],
  unread_count: 2,
};

const CRITICAL_ALERT = {
  alerts: [
    { id: 3, level: "critical", title: "Encryption key missing", body: "Cannot proceed", ts: "2025-06-01T12:00:00Z", dismissed: false },
  ],
  unread_count: 1,
};

const MIXED_ALERTS = {
  alerts: [
    { id: 4, level: "warn",  title: "Low disk space",   body: "Only 5 GB remaining", dismissed: false },
    { id: 5, level: "info",  title: "Update available",  body: "v9.5 is out",        dismissed: true },
  ],
  unread_count: 1,
};

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------
beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.getAlerts.mockResolvedValue(EMPTY_ALERTS);
  apiMocks.dismissAlert.mockResolvedValue(null);
  apiMocks.dismissAllAlerts.mockResolvedValue(null);
});

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
describe("AlertBell — rendering", () => {
  it("renders the bell button", async () => {
    render(<AlertBell />);
    await waitFor(() => expect(screen.getByRole("button")).toBeTruthy());
    expect(screen.getByText("🔔")).toBeTruthy();
  });

  it("does not show unread badge when there are no alerts", async () => {
    render(<AlertBell />);
    await waitFor(() => expect(apiMocks.getAlerts).toHaveBeenCalled());
    expect(screen.queryByText("0")).toBeNull();
  });

  it("shows unread count badge when there are unread alerts", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    await waitFor(() => expect(screen.getByText("2")).toBeTruthy());
  });

  it("shows 9+ when unread count exceeds 9", async () => {
    apiMocks.getAlerts.mockResolvedValue({ alerts: [], unread_count: 15 });
    render(<AlertBell />);
    await waitFor(() => expect(screen.getByText("9+")).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// Panel toggle
// ---------------------------------------------------------------------------
describe("AlertBell — panel toggle", () => {
  it("opens the alert panel on bell click", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    await waitFor(() => expect(screen.getByText("2")).toBeTruthy());
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText("Alerts")).toBeTruthy());
  });

  it("shows alert titles inside the open panel", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    await waitFor(() => screen.getByText("2"));
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => {
      expect(screen.getByText("Backup completed")).toBeTruthy();
      expect(screen.getByText("SSD disconnected")).toBeTruthy();
    });
  });

  it("shows alert body text in the panel", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    await waitFor(() => screen.getByText("2"));
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText("Run #10 finished successfully")).toBeTruthy());
  });

  it("closes the panel on second bell click", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    await waitFor(() => screen.getByText("2"));
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText("Alerts")).toBeTruthy());
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.queryByText("Backup completed")).toBeNull());
  });

  it("closes the panel on outside mousedown", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    await waitFor(() => screen.getByText("2"));
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText("Alerts")).toBeTruthy());
    fireEvent.mouseDown(document.body);
    await waitFor(() => expect(screen.queryByText("Backup completed")).toBeNull());
  });
});

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------
describe("AlertBell — empty state", () => {
  it("shows empty state message when no active alerts", async () => {
    apiMocks.getAlerts.mockResolvedValue(EMPTY_ALERTS);
    render(<AlertBell />);
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText("No active alerts")).toBeTruthy());
  });

  it("shows empty state when all alerts are dismissed", async () => {
    apiMocks.getAlerts.mockResolvedValue({
      alerts: [{ id: 1, level: "info", title: "Old", body: "Old body", dismissed: true }],
      unread_count: 0,
    });
    render(<AlertBell />);
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText("No active alerts")).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// Dismiss single alert
// ---------------------------------------------------------------------------
describe("AlertBell — dismiss single alert", () => {
  it("calls dismissAlert API when dismiss button is clicked", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    await waitFor(() => screen.getByText("2"));
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText("Backup completed")).toBeTruthy());

    const dismissButtons = screen.getAllByText("×");
    fireEvent.click(dismissButtons[0]);
    await waitFor(() => expect(apiMocks.dismissAlert).toHaveBeenCalledWith(1));
  });

  it("removes dismissed alert from the visible list", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    await waitFor(() => screen.getByText("2"));
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText("Backup completed")).toBeTruthy());

    const dismissButtons = screen.getAllByText("×");
    fireEvent.click(dismissButtons[0]);
    await waitFor(() => expect(screen.queryByText("Backup completed")).toBeNull());
  });

  it("decrements unread count after dismissing", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    await waitFor(() => expect(screen.getByText("2")).toBeTruthy());
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => screen.getByText("Backup completed"));

    const dismissButtons = screen.getAllByText("×");
    fireEvent.click(dismissButtons[0]);
    await waitFor(() => expect(screen.getByText("1")).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// Dismiss all
// ---------------------------------------------------------------------------
describe("AlertBell — dismiss all", () => {
  it("calls dismissAllAlerts API when Clear all is clicked", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    await waitFor(() => screen.getByText("2"));
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText("Clear all")).toBeTruthy());
    fireEvent.click(screen.getByText("Clear all"));
    await waitFor(() => expect(apiMocks.dismissAllAlerts).toHaveBeenCalledTimes(1));
  });

  it("shows empty state after clearing all alerts", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    await waitFor(() => screen.getByText("2"));
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => screen.getByText("Clear all"));
    fireEvent.click(screen.getByText("Clear all"));
    await waitFor(() => expect(screen.getByText("No active alerts")).toBeTruthy());
  });

  it("disables Clear all button when no unread alerts", async () => {
    apiMocks.getAlerts.mockResolvedValue(EMPTY_ALERTS);
    render(<AlertBell />);
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => {
      const clearBtn = screen.getByText("Clear all");
      expect(clearBtn.disabled).toBe(true);
    });
  });
});

// ---------------------------------------------------------------------------
// Alert levels and icons
// ---------------------------------------------------------------------------
describe("AlertBell — alert levels", () => {
  it("shows info icon for info-level alert", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText("ℹ")).toBeTruthy());
  });

  it("shows error icon for error-level alert", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText("✖")).toBeTruthy());
  });

  it("shows critical icon for critical-level alert", async () => {
    apiMocks.getAlerts.mockResolvedValue(CRITICAL_ALERT);
    render(<AlertBell />);
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText("🚨")).toBeTruthy());
  });

  it("shows warn icon for warn-level alert", async () => {
    apiMocks.getAlerts.mockResolvedValue(MIXED_ALERTS);
    render(<AlertBell />);
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText("⚠")).toBeTruthy());
  });

  it("only shows non-dismissed alerts in the panel", async () => {
    apiMocks.getAlerts.mockResolvedValue(MIXED_ALERTS);
    render(<AlertBell />);
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => {
      expect(screen.getByText("Low disk space")).toBeTruthy();
      expect(screen.queryByText("Update available")).toBeNull();
    });
  });
});

// ---------------------------------------------------------------------------
// Run ID display
// ---------------------------------------------------------------------------
describe("AlertBell — run ID display", () => {
  it("shows run ID for alerts that have one", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText(/Run #10/)).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// Unread indicator text
// ---------------------------------------------------------------------------
describe("AlertBell — unread indicator in header", () => {
  it("shows unread count in the panel header", async () => {
    apiMocks.getAlerts.mockResolvedValue(TWO_ALERTS);
    render(<AlertBell />);
    await waitFor(() => screen.getByText("2"));
    fireEvent.click(screen.getByText("🔔"));
    await waitFor(() => expect(screen.getByText(/2 unread/)).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// Refresh button
// ---------------------------------------------------------------------------
describe("AlertBell — refresh", () => {
  it("calls getAlerts when refresh button is clicked", async () => {
    apiMocks.getAlerts.mockResolvedValue(EMPTY_ALERTS);
    render(<AlertBell />);
    await waitFor(() => expect(apiMocks.getAlerts).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText("🔔"));
    // Opening the panel also triggers a fetch
    await waitFor(() => expect(apiMocks.getAlerts).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByText("↺"));
    await waitFor(() => expect(apiMocks.getAlerts).toHaveBeenCalledTimes(3));
  });
});

// ---------------------------------------------------------------------------
// Polling
// ---------------------------------------------------------------------------
describe("AlertBell — polling", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("polls for alerts every 15 seconds", async () => {
    // Mock document.visibilityState
    Object.defineProperty(document, "visibilityState", { value: "visible", writable: true });
    apiMocks.getAlerts.mockResolvedValue(EMPTY_ALERTS);
    render(<AlertBell />);
    await act(async () => { await Promise.resolve(); });
    expect(apiMocks.getAlerts).toHaveBeenCalledTimes(1);
    await act(async () => { vi.advanceTimersByTime(15000); await Promise.resolve(); });
    expect(apiMocks.getAlerts).toHaveBeenCalledTimes(2);
  });

  it("cleans up interval on unmount", async () => {
    apiMocks.getAlerts.mockResolvedValue(EMPTY_ALERTS);
    const { unmount } = render(<AlertBell />);
    await act(async () => { await Promise.resolve(); });
    expect(apiMocks.getAlerts).toHaveBeenCalledTimes(1);
    unmount();
    await act(async () => { vi.advanceTimersByTime(15000); await Promise.resolve(); });
    expect(apiMocks.getAlerts).toHaveBeenCalledTimes(1);
  });
});
