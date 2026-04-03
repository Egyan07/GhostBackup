import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ---------------------------------------------------------------------------
// Hoisted API mock
// ---------------------------------------------------------------------------
const apiMocks = vi.hoisted(() => ({
  dashboard: vi.fn(),
}));

vi.mock("../api-client", () => ({
  default: {
    dashboard:             apiMocks.dashboard,
    ssdStatus:             vi.fn().mockResolvedValue({ status: "ok" }),
    watcherStatus:         vi.fn().mockResolvedValue({ running: false }),
    getConfig:             vi.fn().mockResolvedValue({}),
  },
}));

// ---------------------------------------------------------------------------
// Stub heavy child components so we only test Dashboard logic
// ---------------------------------------------------------------------------
vi.mock("../components/StatusPill",  () => ({ default: ({ status }) => <span data-testid="status-pill">{status}</span> }));
vi.mock("../components/SsdGauge",    () => ({ default: ({ used, total }) => <div data-testid="ssd-gauge">{used}/{total}</div> }));
vi.mock("../components/Heatmap",     () => ({ default: () => <div data-testid="heatmap" /> }));
vi.mock("../components/Countdown",   () => ({ default: ({ nextRun, scheduleLabel }) => <div data-testid="countdown">{scheduleLabel || nextRun}</div> }));
vi.mock("../components/ErrBanner",   () => ({ default: ({ error, onDismiss }) => error ? <div data-testid="err-banner" onClick={onDismiss}>{typeof error === "string" ? error : error?.message ?? String(error)}</div> : null }));
vi.mock("../components/LoadingState",() => ({ default: () => <div data-testid="loading-state" /> }));

import Dashboard from "../pages/Dashboard";

// ---------------------------------------------------------------------------
// Shared fixture
// ---------------------------------------------------------------------------
const BASE_DATA = {
  runs: [
    { date: "2025-01-01", status: "success" },
    { date: "2025-01-02", status: "failed"  },
  ],
  last_run: {
    started_at:        "2025-01-02T03:00:00",
    status:            "success",
    files_transferred: 1200,
    duration_seconds:  90,
    duration_human:    "1m 30s",
    bytes_human:       "2.5 GB",
    total_size_gb:     2.5,
    folder_summary: {
      Documents: { status: "success", files_transferred: 800, files_failed: 0 },
      Photos:    { status: "partial", files_transferred: 400, files_failed: 3 },
    },
  },
  active_run:  null,
  ssd_storage: { status: "ok",  used_gb: 40, total_gb: 100, available_gb: 60, path: "/mnt/ssd" },
  schedule:    { label: "Daily", time: "03:00", timezone: "Europe/London" },
  next_run:    "2025-01-03T03:00:00",
};

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.dashboard.mockResolvedValue(BASE_DATA);
});
// ---------------------------------------------------------------------------
// Loading & error states
// ---------------------------------------------------------------------------
describe("Dashboard — loading state", () => {
  it("shows LoadingState while fetch is pending", async () => {
    let resolve;
    apiMocks.dashboard.mockReturnValue(new Promise(r => { resolve = r; }));
    render(<Dashboard />);
    expect(screen.getByTestId("loading-state")).toBeTruthy();
    await act(async () => resolve(BASE_DATA));
  });

  it("hides LoadingState after data arrives", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.queryByTestId("loading-state")).toBeNull());
  });
});

describe("Dashboard — error state", () => {
  it("shows ErrBanner when dashboard API throws", async () => {
    apiMocks.dashboard.mockRejectedValue(new Error("Network error"));
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByTestId("err-banner")).toBeTruthy());
    expect(screen.getByTestId("err-banner").textContent).toBe("Network error");
  });

  it("clears error when ErrBanner is dismissed", async () => {
    apiMocks.dashboard.mockRejectedValueOnce(new Error("fail"))
                      .mockResolvedValue(BASE_DATA);
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByTestId("err-banner")).toBeTruthy());
    await userEvent.click(screen.getByTestId("err-banner"));
    await waitFor(() => expect(screen.queryByTestId("err-banner")).toBeNull());
  });
});

// ---------------------------------------------------------------------------
// Stat strip
// ---------------------------------------------------------------------------
describe("Dashboard — stat strip", () => {
  it("renders Files Last Run value", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getAllByText("1200").length).toBeGreaterThan(0));
  });

  it("renders Duration value", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getAllByText("1m 30s").length).toBeGreaterThan(0));
  });

  it("renders Data Transferred value", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getAllByText("2.5 GB").length).toBeGreaterThan(0));
  });

  it("renders em-dash placeholders when last_run is null", async () => {
    apiMocks.dashboard.mockResolvedValue({ ...BASE_DATA, last_run: null });
    render(<Dashboard />);
    await waitFor(() => {
      const dashes = screen.getAllByText("—");
      expect(dashes.length).toBeGreaterThanOrEqual(3);
    });
  });
});
// ---------------------------------------------------------------------------
// Active run banner
// ---------------------------------------------------------------------------
describe("Dashboard — active run banner", () => {
  it("does not render banner when active_run is null", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.queryByText(/Backup in progress/)).toBeNull());
  });

  it("shows banner with percentage when backup is running", async () => {
    apiMocks.dashboard.mockResolvedValue({
      ...BASE_DATA,
      active_run: { status: "running", overall_pct: 42, files_transferred: 300 },
    });
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText(/Backup in progress/)).toBeTruthy());
    expect(screen.getByText(/42%/)).toBeTruthy();
  });

  it("shows files_transferred count in banner", async () => {
    apiMocks.dashboard.mockResolvedValue({
      ...BASE_DATA,
      active_run: { status: "running", overall_pct: 10, files_transferred: 99 },
    });
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("99 files")).toBeTruthy());
  });

  it("does not show banner when active_run status is not running", async () => {
    apiMocks.dashboard.mockResolvedValue({
      ...BASE_DATA,
      active_run: { status: "idle", overall_pct: 0, files_transferred: 0 },
    });
    render(<Dashboard />);
    await waitFor(() => expect(screen.queryByText(/Backup in progress/)).toBeNull());
  });
});

// ---------------------------------------------------------------------------
// Run history / Heatmap
// ---------------------------------------------------------------------------
describe("Dashboard — run history", () => {
  it("renders Heatmap when runs array is non-empty", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByTestId("heatmap")).toBeTruthy());
  });

  it("shows empty state when runs array is empty", async () => {
    apiMocks.dashboard.mockResolvedValue({ ...BASE_DATA, runs: [] });
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText(/No backup runs yet/)).toBeTruthy());
  });

  it("shows last run date formatted correctly", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("2025-01-02 03:00")).toBeTruthy());
  });

  it("shows 'Never' for last run when last_run is null", async () => {
    apiMocks.dashboard.mockResolvedValue({ ...BASE_DATA, last_run: null });
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("Never")).toBeTruthy());
  });

  it("renders StatusPill for last run status", async () => {
    render(<Dashboard />);
    await waitFor(() => {
      const pills = screen.getAllByTestId("status-pill");
      expect(pills.some(p => p.textContent === "success")).toBe(true);
    });
  });
});
// ---------------------------------------------------------------------------
// Next scheduled run / Countdown
// ---------------------------------------------------------------------------
describe("Dashboard — next scheduled run", () => {
  it("renders Countdown component", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByTestId("countdown")).toBeTruthy());
  });

  it("passes scheduleLabel to Countdown", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByTestId("countdown").textContent).toBe("Daily"));
  });

  it("renders 'Next Scheduled Run' card title", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("Next Scheduled Run")).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// SSD Storage
// ---------------------------------------------------------------------------
describe("Dashboard — SSD storage", () => {
  it("renders SsdGauge with used and total", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByTestId("ssd-gauge").textContent).toBe("40/100"));
  });

  it("shows available GB text", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("60.0 GB free")).toBeTruthy());
  });

  it("shows SSD path", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("/mnt/ssd")).toBeTruthy());
  });

  it("shows Mounted pill when status is ok", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("Mounted")).toBeTruthy());
  });

  it("shows Disconnected pill when status is disconnected", async () => {
    apiMocks.dashboard.mockResolvedValue({
      ...BASE_DATA,
      ssd_storage: { status: "disconnected", used_gb: 0, total_gb: 100, available_gb: 100 },
    });
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("Disconnected")).toBeTruthy());
  });

  it("shows em-dash for available GB when not provided", async () => {
    apiMocks.dashboard.mockResolvedValue({
      ...BASE_DATA,
      ssd_storage: { status: "ok", used_gb: 0, total_gb: 100 },
    });
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("— GB free")).toBeTruthy());
  });

  it("does not render path element when path is absent", async () => {
    apiMocks.dashboard.mockResolvedValue({
      ...BASE_DATA,
      ssd_storage: { status: "ok", used_gb: 10, total_gb: 100, available_gb: 90 },
    });
    render(<Dashboard />);
    await waitFor(() => expect(screen.queryByText("/mnt/ssd")).toBeNull());
  });
});
// ---------------------------------------------------------------------------
// Folder status table
// ---------------------------------------------------------------------------
describe("Dashboard — folder status table", () => {
  it("renders folder names from folder_summary", async () => {
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText("Documents")).toBeTruthy();
      expect(screen.getByText("Photos")).toBeTruthy();
    });
  });

  it("renders StatusPill for each folder", async () => {
    render(<Dashboard />);
    await waitFor(() => {
      const pills = screen.getAllByTestId("status-pill");
      const texts = pills.map(p => p.textContent);
      expect(texts).toContain("success");
      expect(texts).toContain("partial");
    });
  });

  it("renders files_transferred count per folder", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getAllByText("800").length).toBeGreaterThan(0));
  });

  it("renders files_failed count per folder", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText("3")).toBeTruthy());
  });

  it("shows empty state when folder_summary is empty", async () => {
    apiMocks.dashboard.mockResolvedValue({
      ...BASE_DATA,
      last_run: { ...BASE_DATA.last_run, folder_summary: {} },
    });
    render(<Dashboard />);
    await waitFor(() => expect(screen.getByText(/Run a backup to see folder status/)).toBeTruthy());
  });
});
// ---------------------------------------------------------------------------
// Auto-refresh (setInterval)
// ---------------------------------------------------------------------------
describe("Dashboard — auto-refresh", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("calls dashboard API once on mount", async () => {
    render(<Dashboard />);
    await act(async () => { await Promise.resolve(); });
    expect(apiMocks.dashboard).toHaveBeenCalledTimes(1);
  });

  it("calls dashboard API again after 15 seconds", async () => {
    render(<Dashboard />);
    await act(async () => { await Promise.resolve(); });
    expect(apiMocks.dashboard).toHaveBeenCalledTimes(1);
    await act(async () => { vi.advanceTimersByTime(15000); await Promise.resolve(); });
    expect(apiMocks.dashboard).toHaveBeenCalledTimes(2);
  });

  it("clears interval on unmount", async () => {
    const { unmount } = render(<Dashboard />);
    await act(async () => { await Promise.resolve(); });
    expect(apiMocks.dashboard).toHaveBeenCalledTimes(1);
    unmount();
    await act(async () => { vi.advanceTimersByTime(15000); await Promise.resolve(); });
    expect(apiMocks.dashboard).toHaveBeenCalledTimes(1);
  });
});
