/**
 * logsviewer.test.jsx — Unit tests for LogsViewer page
 *
 * Covers: loading state, error state, run list, log display, filtering,
 * search, run summary, empty states, export button.
 *
 * Run with:  npm test
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Hoisted API mock
// ---------------------------------------------------------------------------
const apiMocks = vi.hoisted(() => ({
  getRuns:    vi.fn(),
  getRun:     vi.fn(),
  getRunLogs: vi.fn(),
}));

vi.mock("../api-client", () => ({
  default: {
    getRuns:    apiMocks.getRuns,
    getRun:     apiMocks.getRun,
    getRunLogs: apiMocks.getRunLogs,
  },
}));

// ---------------------------------------------------------------------------
// Stub child components
// ---------------------------------------------------------------------------
vi.mock("../components/StatusPill",   () => ({ default: ({ status }) => <span data-testid="status-pill">{status}</span> }));
vi.mock("../components/ErrBanner",    () => ({ default: ({ error, onDismiss }) => error ? <div data-testid="err-banner" onClick={onDismiss}>{typeof error === "string" ? error : error?.message ?? String(error)}</div> : null }));
vi.mock("../components/LoadingState", () => ({ default: () => <div data-testid="loading-state" /> }));

import LogsViewer from "../pages/LogsViewer";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const RUN_1 = {
  id: 1,
  status: "success",
  started_at: "2025-06-01T03:00:00",
  files_transferred: 500,
  files_failed: 0,
  duration_human: "2m 10s",
  bytes_human: "1.2 GB",
};

const RUN_2 = {
  id: 2,
  status: "failed",
  started_at: "2025-06-02T03:00:00",
  files_transferred: 100,
  files_failed: 5,
  duration_human: "0m 45s",
  bytes_human: "0.3 GB",
};

const LOGS = [
  { logged_at: "2025-06-01T03:00:01", level: "INFO",  message: "Backup started" },
  { logged_at: "2025-06-01T03:00:05", level: "INFO",  message: "Scanning Documents folder" },
  { logged_at: "2025-06-01T03:01:00", level: "WARN",  message: "Skipped locked file: data.db" },
  { logged_at: "2025-06-01T03:02:10", level: "ERROR", message: "Failed to transfer report.xlsx" },
  { logged_at: "2025-06-01T03:02:10", level: "INFO",  message: "Backup completed" },
];

const RUN_1_DETAIL = {
  ...RUN_1,
  folder_summary: {
    Documents: { files_transferred: 300, files_failed: 0 },
    Photos:    { files_transferred: 200, files_failed: 0 },
  },
};

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------
beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.getRuns.mockResolvedValue([RUN_1, RUN_2]);
  apiMocks.getRun.mockResolvedValue(RUN_1_DETAIL);
  apiMocks.getRunLogs.mockResolvedValue(LOGS);
});

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------
describe("LogsViewer — loading state", () => {
  it("shows LoadingState while runs are fetching", async () => {
    let resolve;
    apiMocks.getRuns.mockReturnValue(new Promise(r => { resolve = r; }));
    render(<LogsViewer />);
    expect(screen.getByTestId("loading-state")).toBeTruthy();
    await waitFor(() => resolve([RUN_1]));
  });

  it("hides LoadingState after data arrives", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.queryByTestId("loading-state")).toBeNull());
  });
});

// ---------------------------------------------------------------------------
// Error state
// ---------------------------------------------------------------------------
describe("LogsViewer — error state", () => {
  it("shows ErrBanner when getRuns fails", async () => {
    apiMocks.getRuns.mockRejectedValue(new Error("Network error"));
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByTestId("err-banner")).toBeTruthy());
    expect(screen.getByTestId("err-banner").textContent).toBe("Network error");
  });

  it("dismisses error on ErrBanner click", async () => {
    apiMocks.getRuns.mockRejectedValue(new Error("fail"));
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByTestId("err-banner")).toBeTruthy());
    fireEvent.click(screen.getByTestId("err-banner"));
    await waitFor(() => expect(screen.queryByTestId("err-banner")).toBeNull());
  });

  it("shows ErrBanner when getRunLogs fails", async () => {
    apiMocks.getRunLogs.mockRejectedValue(new Error("Log fetch failed"));
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByTestId("err-banner")).toBeTruthy());
    expect(screen.getByTestId("err-banner").textContent).toBe("Log fetch failed");
  });
});

// ---------------------------------------------------------------------------
// Run history panel
// ---------------------------------------------------------------------------
describe("LogsViewer — run history panel", () => {
  it("renders Run History title", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("Run History")).toBeTruthy());
  });

  it("renders run list with run IDs", async () => {
    render(<LogsViewer />);
    await waitFor(() => {
      expect(screen.getByText(/Run #1/)).toBeTruthy();
      expect(screen.getByText(/Run #2/)).toBeTruthy();
    });
  });

  it("renders StatusPill for each run", async () => {
    render(<LogsViewer />);
    await waitFor(() => {
      const pills = screen.getAllByTestId("status-pill");
      const texts = pills.map(p => p.textContent);
      expect(texts).toContain("success");
      expect(texts).toContain("failed");
    });
  });

  it("shows files transferred for each run", async () => {
    render(<LogsViewer />);
    await waitFor(() => {
      expect(screen.getByText(/500 files transferred/)).toBeTruthy();
      expect(screen.getByText(/100 files transferred/)).toBeTruthy();
    });
  });

  it("shows run date and duration", async () => {
    render(<LogsViewer />);
    await waitFor(() => {
      expect(screen.getByText(/2025-06-01/)).toBeTruthy();
      expect(screen.getByText(/2m 10s/)).toBeTruthy();
    });
  });

  it("shows empty state when there are no runs", async () => {
    apiMocks.getRuns.mockResolvedValue([]);
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("No runs yet")).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// Log display
// ---------------------------------------------------------------------------
describe("LogsViewer — log display", () => {
  it("shows log entries in a table", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("Backup started")).toBeTruthy());
  });

  it("shows all log messages", async () => {
    render(<LogsViewer />);
    await waitFor(() => {
      expect(screen.getByText("Backup started")).toBeTruthy();
      expect(screen.getByText("Scanning Documents folder")).toBeTruthy();
      expect(screen.getByText("Skipped locked file: data.db")).toBeTruthy();
      expect(screen.getByText("Failed to transfer report.xlsx")).toBeTruthy();
      expect(screen.getByText("Backup completed")).toBeTruthy();
    });
  });

  it("shows log levels", async () => {
    render(<LogsViewer />);
    await waitFor(() => {
      const infos = screen.getAllByText("INFO");
      expect(infos.length).toBeGreaterThan(0);
      expect(screen.getByText("WARN")).toBeTruthy();
      expect(screen.getByText("ERROR")).toBeTruthy();
    });
  });

  it("shows time column values", async () => {
    render(<LogsViewer />);
    await waitFor(() => {
      expect(screen.getByText("03:00:01")).toBeTruthy();
    });
  });

  it("shows table headers", async () => {
    render(<LogsViewer />);
    await waitFor(() => {
      expect(screen.getByText("Time")).toBeTruthy();
      expect(screen.getByText("Level")).toBeTruthy();
      expect(screen.getByText("Message")).toBeTruthy();
    });
  });

  it("shows selected run info in title", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText(/Run #1/)).toBeTruthy());
    expect(screen.getByText(/2025-06-01/)).toBeTruthy();
  });

  it("shows No logs found when log list is empty", async () => {
    apiMocks.getRunLogs.mockResolvedValue([]);
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("No logs found")).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// Level filter buttons
// ---------------------------------------------------------------------------
describe("LogsViewer — filter buttons", () => {
  it("renders ALL, INFO, WARN, ERROR filter buttons", async () => {
    render(<LogsViewer />);
    await waitFor(() => {
      expect(screen.getByText("ALL")).toBeTruthy();
      expect(screen.getByText("INFO")).toBeTruthy();
      expect(screen.getByText("WARN")).toBeTruthy();
      expect(screen.getByText("ERROR")).toBeTruthy();
    });
  });

  it("calls getRunLogs with level when filter is clicked", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("Backup started")).toBeTruthy());
    apiMocks.getRunLogs.mockClear();

    // Click the WARN button (there are multiple elements with text WARN — one is filter button, one is log level)
    const buttons = screen.getAllByText("WARN");
    const warnButton = buttons.find(el => el.tagName === "BUTTON");
    fireEvent.click(warnButton);

    await waitFor(() => {
      expect(apiMocks.getRunLogs).toHaveBeenCalledWith(1, "WARN");
    });
  });

  it("calls getRunLogs without level when ALL filter is clicked", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("Backup started")).toBeTruthy());

    // First click a specific level
    const errorButtons = screen.getAllByText("ERROR");
    const errorButton = errorButtons.find(el => el.tagName === "BUTTON");
    fireEvent.click(errorButton);
    await waitFor(() => expect(apiMocks.getRunLogs).toHaveBeenCalledWith(1, "ERROR"));

    apiMocks.getRunLogs.mockClear();
    const allButtons = screen.getAllByText("ALL");
    const allButton = allButtons.find(el => el.tagName === "BUTTON");
    fireEvent.click(allButton);
    await waitFor(() => expect(apiMocks.getRunLogs).toHaveBeenCalledWith(1, undefined));
  });
});

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------
describe("LogsViewer — search", () => {
  it("renders search input", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByPlaceholderText("Search logs…")).toBeTruthy());
  });

  it("filters logs by search text", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("Backup started")).toBeTruthy());

    const searchInput = screen.getByPlaceholderText("Search logs…");
    fireEvent.change(searchInput, { target: { value: "report" } });

    await waitFor(() => {
      expect(screen.getByText("Failed to transfer report.xlsx")).toBeTruthy();
      expect(screen.queryByText("Backup started")).toBeNull();
      expect(screen.queryByText("Scanning Documents folder")).toBeNull();
    });
  });

  it("search is case-insensitive", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("Backup started")).toBeTruthy());

    const searchInput = screen.getByPlaceholderText("Search logs…");
    fireEvent.change(searchInput, { target: { value: "BACKUP" } });

    await waitFor(() => {
      expect(screen.getByText("Backup started")).toBeTruthy();
      expect(screen.getByText("Backup completed")).toBeTruthy();
      expect(screen.queryByText("Scanning Documents folder")).toBeNull();
    });
  });

  it("shows No logs found when search matches nothing", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("Backup started")).toBeTruthy());

    const searchInput = screen.getByPlaceholderText("Search logs…");
    fireEvent.change(searchInput, { target: { value: "zzzznonexistent" } });

    await waitFor(() => expect(screen.getByText("No logs found")).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// Run summary card
// ---------------------------------------------------------------------------
describe("LogsViewer — run summary", () => {
  it("renders Run Summary title", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("Run Summary")).toBeTruthy());
  });

  it("shows transferred count", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("Transferred")).toBeTruthy());
    expect(screen.getByText("500")).toBeTruthy();
  });

  it("shows failed count", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("Failed")).toBeTruthy());
    expect(screen.getByText("0")).toBeTruthy();
  });

  it("shows duration", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("Duration")).toBeTruthy());
    expect(screen.getByText("2m 10s")).toBeTruthy();
  });

  it("shows data size", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("Data")).toBeTruthy());
    expect(screen.getByText("1.2 GB")).toBeTruthy();
  });

  it("shows run ID in summary", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("#1")).toBeTruthy());
  });

  it("shows StatusPill in summary", async () => {
    render(<LogsViewer />);
    await waitFor(() => {
      const pills = screen.getAllByTestId("status-pill");
      expect(pills.some(p => p.textContent === "success")).toBe(true);
    });
  });
});

// ---------------------------------------------------------------------------
// Run selection
// ---------------------------------------------------------------------------
describe("LogsViewer — run selection", () => {
  it("loads logs for a different run when clicked", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText(/Run #1/)).toBeTruthy());

    apiMocks.getRunLogs.mockClear();
    apiMocks.getRun.mockClear();

    // Click on Run #2
    fireEvent.click(screen.getByText(/Run #2/));

    await waitFor(() => {
      expect(apiMocks.getRunLogs).toHaveBeenCalledWith(2, undefined);
      expect(apiMocks.getRun).toHaveBeenCalledWith(2);
    });
  });
});

// ---------------------------------------------------------------------------
// Export button
// ---------------------------------------------------------------------------
describe("LogsViewer — export", () => {
  it("renders Export button", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(screen.getByText("Export")).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// API calls on mount
// ---------------------------------------------------------------------------
describe("LogsViewer — API calls", () => {
  it("calls getRuns with limit 30 on mount", async () => {
    render(<LogsViewer />);
    await waitFor(() => expect(apiMocks.getRuns).toHaveBeenCalledWith(30));
  });

  it("auto-selects first run and fetches its logs", async () => {
    render(<LogsViewer />);
    await waitFor(() => {
      expect(apiMocks.getRunLogs).toHaveBeenCalledWith(1, undefined);
      expect(apiMocks.getRun).toHaveBeenCalledWith(1);
    });
  });
});
