/**
 * liverun.test.jsx — Unit tests for LiveRun page
 *
 * Covers: loading, idle state, running state, progress display, start/stop,
 * per-library progress, live statistics, live file feed, error handling.
 *
 * Run with:  npm test
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Hoisted API mock
// ---------------------------------------------------------------------------
const apiMocks = vi.hoisted(() => ({
  runStatus: vi.fn(),
  startRun: vi.fn(),
  stopRun: vi.fn(),
}));

vi.mock("../api-client", () => ({
  default: {
    runStatus: apiMocks.runStatus,
    startRun: apiMocks.startRun,
    stopRun: apiMocks.stopRun,
  },
}));

// ---------------------------------------------------------------------------
// Stub child components
// ---------------------------------------------------------------------------
vi.mock("../components/StatusPill", () => ({
  default: ({ status }) => <span data-testid="status-pill">{status}</span>,
}));
vi.mock("../components/ErrBanner", () => ({
  default: ({ error, onDismiss }) =>
    error ? (
      <div data-testid="err-banner" onClick={onDismiss}>
        {typeof error === "string" ? error : (error?.message ?? String(error))}
      </div>
    ) : null,
}));

import LiveRun from "../pages/LiveRun";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const IDLE_STATUS = {
  status: "idle",
  overall_pct: 0,
  files_transferred: 0,
  files_failed: 0,
  feed: [],
  libraries: {},
};

const RUNNING_STATUS = {
  status: "running",
  overall_pct: 42,
  files_transferred: 300,
  files_failed: 2,
  bytes_transferred: 2684354560, // ~2.50 GB
  started_at: "2025-06-01T10:00:00Z",
  feed: [
    { time: "10:01", file: "Documents/report.pdf", size_mb: 1.5, library: "Documents" },
    { time: "10:02", file: "Photos/img_001.jpg", size_mb: 3.2, library: "Photos" },
  ],
  libraries: {
    Documents: { pct: 60 },
    Photos: { pct: 25 },
  },
};

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------
beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.runStatus.mockResolvedValue(IDLE_STATUS);
  apiMocks.startRun.mockResolvedValue(null);
  apiMocks.stopRun.mockResolvedValue(null);
});

// ---------------------------------------------------------------------------
// Initial rendering — idle state
// ---------------------------------------------------------------------------
describe("LiveRun — idle state", () => {
  it("renders the Overall Progress title", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText("Overall Progress")).toBeTruthy());
  });

  it("shows 0% progress when idle", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText("0")).toBeTruthy());
  });

  it("shows idle StatusPill", async () => {
    render(<LiveRun />);
    await waitFor(() => {
      const pills = screen.getAllByTestId("status-pill");
      expect(pills.some((p) => p.textContent === "idle")).toBe(true);
    });
  });

  it("shows Run Incremental button when idle", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/Run Incremental/)).toBeTruthy());
  });

  it("shows Run Full Backup button when idle", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/Run Full Backup/)).toBeTruthy());
  });

  it("does not show Stop button when idle", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/Run Incremental/)).toBeTruthy());
    expect(screen.queryByText(/Stop/)).toBeNull();
  });

  it("shows empty library state when not running", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText("Start a backup run")).toBeTruthy());
  });

  it("shows awaiting activity message in file feed", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/Awaiting backup activity/)).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// Running state
// ---------------------------------------------------------------------------
describe("LiveRun — running state", () => {
  beforeEach(() => {
    apiMocks.runStatus.mockResolvedValue(RUNNING_STATUS);
  });

  it("shows overall percentage", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText("42")).toBeTruthy());
  });

  it("shows running StatusPill", async () => {
    render(<LiveRun />);
    await waitFor(() => {
      const pills = screen.getAllByTestId("status-pill");
      expect(pills.some((p) => p.textContent === "running")).toBe(true);
    });
  });

  it("shows Stop button when running", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/Stop/)).toBeTruthy());
  });

  it("does not show start buttons when running", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/Stop/)).toBeTruthy());
    expect(screen.queryByText(/Run Incremental/)).toBeNull();
    expect(screen.queryByText(/Run Full Backup/)).toBeNull();
  });

  it("shows files transferred count in stats", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText("300")).toBeTruthy());
  });

  it("shows files failed count", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/2 errors/)).toBeTruthy());
  });

  it("shows elapsed time when running", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/elapsed/)).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// Per-library progress
// ---------------------------------------------------------------------------
describe("LiveRun — per-library progress", () => {
  beforeEach(() => {
    apiMocks.runStatus.mockResolvedValue(RUNNING_STATUS);
  });

  it("renders library names", async () => {
    render(<LiveRun />);
    await waitFor(() => {
      expect(screen.getAllByText("Documents").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Photos").length).toBeGreaterThan(0);
    });
  });

  it("renders library percentages", async () => {
    render(<LiveRun />);
    await waitFor(() => {
      expect(screen.getByText("60%")).toBeTruthy();
      expect(screen.getByText("25%")).toBeTruthy();
    });
  });
});

// ---------------------------------------------------------------------------
// Live statistics panel
// ---------------------------------------------------------------------------
describe("LiveRun — live statistics", () => {
  it("shows dash placeholders when idle", async () => {
    render(<LiveRun />);
    await waitFor(() => {
      const dashes = screen.getAllByText("—");
      expect(dashes.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("shows data written in GB when running", async () => {
    apiMocks.runStatus.mockResolvedValue(RUNNING_STATUS);
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText("2.50 GB")).toBeTruthy());
  });

  it("shows stat labels", async () => {
    render(<LiveRun />);
    await waitFor(() => {
      expect(screen.getByText("Files Transferred")).toBeTruthy();
      expect(screen.getByText("Files Failed")).toBeTruthy();
      expect(screen.getByText("Data Written")).toBeTruthy();
      expect(screen.getByText("Run Status")).toBeTruthy();
    });
  });
});

// ---------------------------------------------------------------------------
// Live file feed
// ---------------------------------------------------------------------------
describe("LiveRun — live file feed", () => {
  it("renders Live File Feed title", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText("Live File Feed")).toBeTruthy());
  });

  it("shows file entries when running", async () => {
    apiMocks.runStatus.mockResolvedValue(RUNNING_STATUS);
    render(<LiveRun />);
    await waitFor(() => {
      expect(screen.getByText("Documents/report.pdf")).toBeTruthy();
      expect(screen.getByText("Photos/img_001.jpg")).toBeTruthy();
    });
  });

  it("shows file size in MB", async () => {
    apiMocks.runStatus.mockResolvedValue(RUNNING_STATUS);
    render(<LiveRun />);
    await waitFor(() => {
      expect(screen.getByText("1.5 MB")).toBeTruthy();
      expect(screen.getByText("3.2 MB")).toBeTruthy();
    });
  });

  it("shows library name for each feed entry", async () => {
    apiMocks.runStatus.mockResolvedValue(RUNNING_STATUS);
    render(<LiveRun />);
    await waitFor(() => {
      // Library names in feed entries
      const docs = screen.getAllByText("Documents");
      expect(docs.length).toBeGreaterThanOrEqual(1);
    });
  });
});

// ---------------------------------------------------------------------------
// Start run
// ---------------------------------------------------------------------------
describe("LiveRun — start run", () => {
  it("calls startRun with full=false for incremental", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/Run Incremental/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Run Incremental/));
    await waitFor(() => expect(apiMocks.startRun).toHaveBeenCalledWith({ full: false }));
  });

  it("calls startRun with full=true for full backup", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/Run Full Backup/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Run Full Backup/));
    await waitFor(() => expect(apiMocks.startRun).toHaveBeenCalledWith({ full: true }));
  });

  it("polls status after starting a run", async () => {
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/Run Incremental/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Run Incremental/));
    await waitFor(() => {
      // Initial poll + post-start poll
      expect(apiMocks.runStatus.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("shows Starting text while run is being started", async () => {
    let resolveStart;
    apiMocks.startRun.mockReturnValue(
      new Promise((r) => {
        resolveStart = r;
      })
    );
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/Run Incremental/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Run Incremental/));
    await waitFor(() => expect(screen.getByText(/Starting/)).toBeTruthy());
    await act(async () => resolveStart(null));
  });
});

// ---------------------------------------------------------------------------
// Stop run
// ---------------------------------------------------------------------------
describe("LiveRun — stop run", () => {
  it("calls stopRun API when Stop is clicked", async () => {
    apiMocks.runStatus.mockResolvedValue(RUNNING_STATUS);
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/Stop/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Stop/));
    await waitFor(() => expect(apiMocks.stopRun).toHaveBeenCalledTimes(1));
  });

  it("shows Stopping text while stop is in progress", async () => {
    apiMocks.runStatus.mockResolvedValue(RUNNING_STATUS);
    let resolveStop;
    apiMocks.stopRun.mockReturnValue(
      new Promise((r) => {
        resolveStop = r;
      })
    );
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/Stop/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Stop/));
    await waitFor(() => expect(screen.getByText(/Stopping/)).toBeTruthy());
    await act(async () => resolveStop(null));
  });
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------
describe("LiveRun — error handling", () => {
  it("shows ErrBanner when runStatus fails", async () => {
    apiMocks.runStatus.mockRejectedValue(new Error("Connection refused"));
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByTestId("err-banner")).toBeTruthy());
    expect(screen.getByTestId("err-banner").textContent).toBe("Connection refused");
  });

  it("shows ErrBanner when startRun fails", async () => {
    apiMocks.startRun.mockRejectedValue(new Error("SSD not mounted"));
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByText(/Run Incremental/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Run Incremental/));
    await waitFor(() => expect(screen.getByTestId("err-banner")).toBeTruthy());
    expect(screen.getByTestId("err-banner").textContent).toBe("SSD not mounted");
  });

  it("dismisses error on ErrBanner click", async () => {
    apiMocks.runStatus.mockRejectedValueOnce(new Error("fail")).mockResolvedValue(IDLE_STATUS);
    render(<LiveRun />);
    await waitFor(() => expect(screen.getByTestId("err-banner")).toBeTruthy());
    fireEvent.click(screen.getByTestId("err-banner"));
    await waitFor(() => expect(screen.queryByTestId("err-banner")).toBeNull());
  });
});

// ---------------------------------------------------------------------------
// Polling behavior
// ---------------------------------------------------------------------------
describe("LiveRun — polling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("polls status on mount", async () => {
    render(<LiveRun />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(apiMocks.runStatus).toHaveBeenCalledTimes(1);
  });

  it("polls again after delay", async () => {
    render(<LiveRun />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(apiMocks.runStatus).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });
    expect(apiMocks.runStatus).toHaveBeenCalledTimes(2);
  });

  it("cleans up timeout on unmount", async () => {
    const { unmount } = render(<LiveRun />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(apiMocks.runStatus).toHaveBeenCalledTimes(1);
    unmount();
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });
    expect(apiMocks.runStatus).toHaveBeenCalledTimes(1);
  });
});
