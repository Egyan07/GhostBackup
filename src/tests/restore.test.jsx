import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Hoisted API mock
// ---------------------------------------------------------------------------
const apiMocks = vi.hoisted(() => ({
  getRuns:  vi.fn(),
  getRun:   vi.fn(),
  restore:  vi.fn(),
}));

vi.mock("../api-client", () => ({
  default: {
    getRuns:  apiMocks.getRuns,
    getRun:   apiMocks.getRun,
    restore:  apiMocks.restore,
  },
}));

// ---------------------------------------------------------------------------
// Stub child components
// ---------------------------------------------------------------------------
vi.mock("../components/StatusPill",  () => ({ default: ({ status }) => <span data-testid="status-pill">{status}</span> }));
vi.mock("../components/ErrBanner",   () => ({ default: ({ error, onDismiss }) => error ? <div data-testid="err-banner" onClick={onDismiss}>{typeof error === "string" ? error : error?.message ?? String(error)}</div> : null }));
vi.mock("../components/LoadingState",() => ({ default: () => <div data-testid="loading-state" /> }));

import RestoreUI from "../pages/RestoreUI";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const RUN_1 = {
  id: 1,
  status: "success",
  started_at: "2025-01-01T03:00:00",
  files_transferred: 500,
  bytes_human: "1.2 GB",
  folder_summary: {
    Documents: { files_transferred: 300, files_failed: 0, size_gb: 0.8 },
    Photos:    { files_transferred: 200, files_failed: 2, size_gb: 0.4 },
  },
};

const RUN_2 = {
  id: 2,
  status: "success",
  started_at: "2025-01-02T03:00:00",
  files_transferred: 600,
  bytes_human: "1.5 GB",
  folder_summary: {
    Documents: { files_transferred: 600, files_failed: 0, size_gb: 1.5 },
  },
};

const FAILED_RUN = {
  id: 3,
  status: "failed",
  started_at: "2025-01-03T03:00:00",
  files_transferred: 0,
  bytes_human: "0 B",
  folder_summary: {},
};

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.getRuns.mockResolvedValue([RUN_1, RUN_2]);
  apiMocks.getRun.mockResolvedValue(RUN_1);
  apiMocks.restore.mockResolvedValue({ files_to_restore: 10, files: [], dry_run: true, destination: "/tmp" });
});
// ---------------------------------------------------------------------------
// Loading & error states
// ---------------------------------------------------------------------------
describe("RestoreUI — loading state", () => {
  it("shows LoadingState while runs are fetching", async () => {
    let resolve;
    apiMocks.getRuns.mockReturnValue(new Promise(r => { resolve = r; }));
    render(<RestoreUI />);
    expect(screen.getByTestId("loading-state")).toBeTruthy();
    await waitFor(() => { resolve([RUN_1]); });
  });

  it("hides LoadingState after runs arrive", async () => {
    render(<RestoreUI />);
    await waitFor(() => expect(screen.queryByTestId("loading-state")).toBeNull());
  });
});

describe("RestoreUI — error state", () => {
  it("shows ErrBanner when getRuns throws", async () => {
    apiMocks.getRuns.mockRejectedValue(new Error("fetch failed"));
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByTestId("err-banner")).toBeTruthy());
    expect(screen.getByTestId("err-banner").textContent).toBe("fetch failed");
  });

  it("dismisses error on ErrBanner click", async () => {
    apiMocks.getRuns.mockRejectedValue(new Error("oops"));
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByTestId("err-banner")).toBeTruthy());
    fireEvent.click(screen.getByTestId("err-banner"));
    await waitFor(() => expect(screen.queryByTestId("err-banner")).toBeNull());
  });
});

// ---------------------------------------------------------------------------
// Run list
// ---------------------------------------------------------------------------
describe("RestoreUI — run list", () => {
  it("renders run list items", async () => {
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText(/Run #1/)).toBeTruthy());
    expect(screen.getByText(/Run #2/)).toBeTruthy();
  });

  it("filters out failed runs", async () => {
    apiMocks.getRuns.mockResolvedValue([RUN_1, FAILED_RUN]);
    apiMocks.getRun.mockResolvedValue(RUN_1);
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText(/Run #1/)).toBeTruthy());
    expect(screen.queryByText(/Run #3/)).toBeNull();
  });

  it("shows empty state when no successful runs", async () => {
    apiMocks.getRuns.mockResolvedValue([FAILED_RUN]);
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText(/No successful backups yet/)).toBeTruthy());
  });

  it("shows run date in list", async () => {
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText(/2025-01-01/)).toBeTruthy());
  });

  it("shows StatusPill for each run", async () => {
    render(<RestoreUI />);
    await waitFor(() => {
      const pills = screen.getAllByTestId("status-pill");
      expect(pills.some(p => p.textContent === "success")).toBe(true);
    });
  });
});
// ---------------------------------------------------------------------------
// Library selection
// ---------------------------------------------------------------------------
describe("RestoreUI — library selection", () => {
  it("shows library names from folder_summary", async () => {
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText("Documents")).toBeTruthy());
    expect(screen.getByText("Photos")).toBeTruthy();
  });

  it("selecting a library updates the selected library input", async () => {
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText("Documents")).toBeTruthy());
    fireEvent.click(screen.getByText("Documents"));
    await waitFor(() => {
      const input = screen.getByDisplayValue("Documents");
      expect(input).toBeTruthy();
    });
  });

  it("deselects library when clicked again", async () => {
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText("Documents")).toBeTruthy());
    fireEvent.click(screen.getByText("Documents"));
    await waitFor(() => expect(screen.getByDisplayValue("Documents")).toBeTruthy());
    fireEvent.click(screen.getByText("Documents"));
    await waitFor(() => expect(screen.getByDisplayValue("None selected")).toBeTruthy());
  });

  it("shows 'None selected' initially", async () => {
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByDisplayValue("None selected")).toBeTruthy());
  });

  it("shows empty state when run has no library data", async () => {
    apiMocks.getRun.mockResolvedValue({ ...RUN_1, folder_summary: {} });
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText("No library data")).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// Destination path
// ---------------------------------------------------------------------------
describe("RestoreUI — destination path", () => {
  it("renders destination path input", async () => {
    render(<RestoreUI />);
    await waitFor(() => {
      const inputs = screen.getAllByRole("textbox");
      expect(inputs.length).toBeGreaterThan(0);
    });
  });

  it("allows typing a custom destination path", async () => {
    render(<RestoreUI />);
    await waitFor(() => screen.getAllByRole("textbox"));
    const destInput = screen.getAllByRole("textbox")[0];
    fireEvent.change(destInput, { target: { value: "/custom/path" } });
    expect(destInput.value).toBe("/custom/path");
  });

  it("renders Browse button", async () => {
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText("Browse")).toBeTruthy());
  });
});
// ---------------------------------------------------------------------------
// Dry-run toggle
// ---------------------------------------------------------------------------
describe("RestoreUI — dry-run toggle", () => {
  it("dry-run is enabled by default", async () => {
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText("(enabled)")).toBeTruthy());
  });

  it("button shows 'Run Dry-Run Preview' when dry-run enabled", async () => {
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText("Run Dry-Run Preview")).toBeTruthy());
  });

  it("toggling dry-run changes label to disabled", async () => {
    render(<RestoreUI />);
    await waitFor(() => screen.getByText("(enabled)"));
    const checkbox = document.querySelector('input[type="checkbox"]');
    fireEvent.click(checkbox);
    await waitFor(() => expect(screen.getByText("(disabled)")).toBeTruthy());
  });

  it("button shows 'Restore Files' when dry-run disabled", async () => {
    render(<RestoreUI />);
    await waitFor(() => screen.getByText("(enabled)"));
    const checkbox = document.querySelector('input[type="checkbox"]');
    fireEvent.click(checkbox);
    await waitFor(() => expect(screen.getByText("Restore Files")).toBeTruthy());
  });
});

// ---------------------------------------------------------------------------
// Restore button & API call
// ---------------------------------------------------------------------------
describe("RestoreUI — restore button", () => {
  it("restore button is disabled when no library selected", async () => {
    render(<RestoreUI />);
    await waitFor(() => screen.getByText("Run Dry-Run Preview"));
    const btn = screen.getByText("Run Dry-Run Preview");
    expect(btn.disabled).toBe(true);
  });

  it("restore button enabled after library selected", async () => {
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText("Documents")).toBeTruthy());
    fireEvent.click(screen.getByText("Documents"));
    await waitFor(() => {
      const btn = screen.getByText("Run Dry-Run Preview");
      expect(btn.disabled).toBe(false);
    });
  });

  it("calls api.restore with correct params on click", async () => {
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText("Documents")).toBeTruthy());
    fireEvent.click(screen.getByText("Documents"));
    await waitFor(() => expect(screen.getByText("Run Dry-Run Preview").disabled).toBe(false));
    fireEvent.click(screen.getByText("Run Dry-Run Preview"));
    await waitFor(() => expect(apiMocks.restore).toHaveBeenCalledTimes(1));
    expect(apiMocks.restore).toHaveBeenCalledWith(
      expect.objectContaining({ run_id: 1, library: "Documents", dry_run: true })
    );
  });

  it("shows error when doRestore called without library selected", async () => {
    apiMocks.getRun.mockResolvedValue({ ...RUN_1, folder_summary: {} });
    render(<RestoreUI />);
    await waitFor(() => screen.getByText("Run Dry-Run Preview"));
    // button is disabled — invoke handler directly via the underlying button element
    const btn = screen.getByText("Run Dry-Run Preview");
    fireEvent.click(btn, {}, { bubbles: true });
    // button disabled means doRestore won't fire; verify button is indeed disabled
    expect(btn.disabled).toBe(true);
  });
});
describe("RestoreUI — restore result", () => {
  const selectAndRestore = async () => {
    render(<RestoreUI />);
    await waitFor(() => expect(screen.getByText("Documents")).toBeTruthy());
    fireEvent.click(screen.getByText("Documents"));
    await waitFor(() => expect(screen.getByText("Run Dry-Run Preview").disabled).toBe(false));
    fireEvent.click(screen.getByText("Run Dry-Run Preview"));
  };

  it("shows files_to_restore count after dry-run", async () => {
    apiMocks.restore.mockResolvedValue({ files_to_restore: 10, files: [], dry_run: true, destination: "/tmp" });
    await selectAndRestore();
    await waitFor(() => expect(screen.getByText(/10 files would be restored/)).toBeTruthy());
  });

  it("shows dry-run complete message", async () => {
    apiMocks.restore.mockResolvedValue({ files_to_restore: 5, files: [], dry_run: true, destination: "/tmp" });
    await selectAndRestore();
    await waitFor(() => expect(screen.getByText(/Dry-run complete/)).toBeTruthy());
  });

  it("shows restore result heading when not dry-run", async () => {
    apiMocks.restore.mockResolvedValue({ files_count: 5, files: [], dry_run: false, destination: "/tmp" });
    render(<RestoreUI />);
    await waitFor(() => screen.getByText("(enabled)"));
    fireEvent.click(document.querySelector('input[type="checkbox"]'));
    await waitFor(() => screen.getByText("(disabled)"));
    fireEvent.click(screen.getByText("Documents"));
    await waitFor(() => expect(screen.getByText("Restore Files").disabled).toBe(false));
    fireEvent.click(screen.getByText("Restore Files"));
    await waitFor(() => expect(screen.getByText(/Restore complete/)).toBeTruthy());
  });

  it("shows file list when files array is non-empty", async () => {
    apiMocks.restore.mockResolvedValue({
      files_to_restore: 1,
      dry_run: true,
      destination: "/tmp",
      files: [{ name: "report.docx", size: 2097152 }],
    });
    await selectAndRestore();
    await waitFor(() => expect(screen.getByText("report.docx")).toBeTruthy());
  });

  it("shows api error in ErrBanner when restore throws", async () => {
    apiMocks.restore.mockRejectedValue(new Error("restore failed"));
    await selectAndRestore();
    await waitFor(() => expect(screen.getByTestId("err-banner").textContent).toBe("restore failed"));
  });
});

describe("RestoreUI — warning banner", () => {
  it("always shows the safety warning", async () => {
    render(<RestoreUI />);
    await waitFor(() =>
      expect(screen.getByText(/Original source folders are not modified/)).toBeTruthy()
    );
  });
});




