/**
 * components.test.jsx — Unit tests for pure UI components
 *
 * Covers: ErrBanner, StatusPill, Countdown, LoadingState
 *
 * Run with:  npm test
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
import ErrBanner    from "../components/ErrBanner.jsx";
import StatusPill   from "../components/StatusPill.jsx";
import Countdown    from "../components/Countdown.jsx";
import LoadingState from "../components/LoadingState.jsx";

// ── ErrBanner ─────────────────────────────────────────────────────────────────

describe("ErrBanner", () => {
  it("renders nothing when error is null", () => {
    const { container } = render(<ErrBanner error={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when error is undefined", () => {
    const { container } = render(<ErrBanner />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when error is empty string", () => {
    const { container } = render(<ErrBanner error="" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders error message when error is set", () => {
    render(<ErrBanner error="Something went wrong" />);
    expect(screen.getByText("Something went wrong")).toBeTruthy();
  });

  it("renders dismiss button when onDismiss is provided", () => {
    render(<ErrBanner error="Error" onDismiss={() => {}} />);
    expect(screen.getByRole("button")).toBeTruthy();
  });

  it("does not render dismiss button when onDismiss is absent", () => {
    render(<ErrBanner error="Error" />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("calls onDismiss when dismiss button is clicked", () => {
    const onDismiss = vi.fn();
    render(<ErrBanner error="Error" onDismiss={onDismiss} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("renders structured error objects with code and message", () => {
    const err = { code: "GB-E001", message: "Key missing" };
    render(<ErrBanner error={err} />);
    expect(screen.getByText("GB-E001")).toBeTruthy();
    expect(screen.getByText("Key missing")).toBeTruthy();
  });

  it("renders fix suggestion when provided in error object", () => {
    const err = { message: "Error", fix: "Check settings" };
    render(<ErrBanner error={err} />);
    expect(screen.getByText("Fix: Check settings")).toBeTruthy();
  });

  it("handles error objects without code or fix gracefully", () => {
    const err = { message: "Simple error object" };
    render(<ErrBanner error={err} />);
    expect(screen.getByText("Simple error object")).toBeTruthy();
    expect(screen.queryByText("Fix:")).toBeNull();
  });

  it("shows warning icon on error", () => {
    render(<ErrBanner error="err" />);
    expect(screen.getByText("⚠")).toBeTruthy();
  });

  it("applies mono font style to error code", () => {
    const err = { code: "CODE123", message: "Msg" };
    render(<ErrBanner error={err} />);
    const codeElement = screen.getByText("CODE123");
    expect(codeElement.style.fontFamily).toContain("mono");
  });

  it("renders string representation of error object if message is missing", () => {
    render(<ErrBanner error={{ foo: "bar" }} />);
    expect(screen.getByText("[object Object]")).toBeTruthy();
  });

  it("displays the warning icon", () => {
    render(<ErrBanner error="Test error" />);
    expect(screen.getByText("⚠")).toBeTruthy();
  });

  it("renders long error message without truncation", () => {
    const msg = "A".repeat(500);
    render(<ErrBanner error={msg} />);
    expect(screen.getByText(msg)).toBeTruthy();
  });
});

// ── StatusPill ────────────────────────────────────────────────────────────────

describe("StatusPill", () => {
  it("renders 'Success' for status=success", () => {
    render(<StatusPill status="success" />);
    expect(screen.getByText("Success")).toBeTruthy();
  });

  it("renders 'Failed' for status=failed", () => {
    render(<StatusPill status="failed" />);
    expect(screen.getByText("Failed")).toBeTruthy();
  });

  it("renders 'Running' for status=running", () => {
    render(<StatusPill status="running" />);
    expect(screen.getByText("Running")).toBeTruthy();
  });

  it("renders 'Partial' for status=partial", () => {
    render(<StatusPill status="partial" />);
    expect(screen.getByText("Partial")).toBeTruthy();
  });

  it("renders 'Cancelled' for status=cancelled", () => {
    render(<StatusPill status="cancelled" />);
    expect(screen.getByText("Cancelled")).toBeTruthy();
  });

  it("renders 'Idle' for status=idle", () => {
    render(<StatusPill status="idle" />);
    expect(screen.getByText("Idle")).toBeTruthy();
  });

  it("renders the raw status string for unknown status", () => {
    render(<StatusPill status="queued" />);
    expect(screen.getByText("queued")).toBeTruthy();
  });

  it("renders 'Unknown' when status is undefined", () => {
    render(<StatusPill />);
    expect(screen.getByText("Unknown")).toBeTruthy();
  });

  it("renders a span element as the root", () => {
    const { container } = render(<StatusPill status="success" />);
    expect(container.firstChild.tagName).toBe("SPAN");
  });

  it("applies pill-success class for success status", () => {
    const { container } = render(<StatusPill status="success" />);
    expect(container.firstChild.className).toContain("pill-success");
  });

  it("applies pill-failed class for failed status", () => {
    const { container } = render(<StatusPill status="failed" />);
    expect(container.firstChild.className).toContain("pill-failed");
  });

  it("applies pill-idle class for unknown status", () => {
    const { container } = render(<StatusPill status="__unknown__" />);
    expect(container.firstChild.className).toContain("pill-idle");
  });
});

// ── LoadingState ──────────────────────────────────────────────────────────────

describe("LoadingState", () => {
  it("renders without crashing", () => {
    const { container } = render(<LoadingState />);
    expect(container.firstChild).toBeTruthy();
  });

  it("renders a loading indicator element", () => {
    render(<LoadingState />);
    expect(document.body.innerHTML).toBeTruthy();
  });
});

// ── Countdown ─────────────────────────────────────────────────────────────────

describe("Countdown", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders a time string in HH:MM:SS format", () => {
    const nextRun = new Date(Date.now() + 3_600_000).toISOString();
    render(<Countdown nextRun={nextRun} />);
    const text = screen.getByText(/\d{2}:\d{2}:\d{2}/);
    expect(text).toBeTruthy();
  });

  it("renders 00:00:00 when nextRun is in the past", () => {
    const nextRun = new Date(Date.now() - 1000).toISOString();
    render(<Countdown nextRun={nextRun} />);
    expect(screen.getByText("00:00:00")).toBeTruthy();
  });

  it("renders neutral placeholder when no nextRun provided", () => {
    act(() => {
      render(<Countdown scheduleTime="09:30" timezone="Europe/London" />);
    });
    expect(screen.getByText("--:--:--")).toBeTruthy();
    expect(screen.getByText("Until next backup · Daily at 09:30 Europe/London")).toBeTruthy();
  });

  it("updates display after 1 second", () => {
    const nextRun = new Date(Date.now() + 3_661_000).toISOString();
    render(<Countdown nextRun={nextRun} />);
    const before = screen.getByText(/\d{2}:\d{2}:\d{2}/).textContent;

    act(() => { vi.advanceTimersByTime(1000); });

    const after = screen.getByText(/\d{2}:\d{2}:\d{2}/).textContent;
    expect(before).not.toBe(after);
  });

  it("renders the countdown label", () => {
    const nextRun = new Date(Date.now() + 3_600_000).toISOString();
    render(<Countdown nextRun={nextRun} />);
    expect(screen.getByText(/Until next backup/)).toBeTruthy();
  });

  it("renders schedule metadata when provided", () => {
    render(
      <Countdown
        nextRun={new Date(Date.now() + 3_600_000).toISOString()}
        scheduleTime="09:30"
        timezone="Europe/London"
      />
    );
    expect(screen.getByText("Until next backup · Daily at 09:30 Europe/London")).toBeTruthy();
  });

  it("prefers a provided schedule label", () => {
    render(
      <Countdown
        nextRun={new Date(Date.now() + 3_600_000).toISOString()}
        scheduleLabel="Daily at 07:00 UTC"
        scheduleTime="09:30"
        timezone="Europe/London"
      />
    );
    expect(screen.getByText("Until next backup · Daily at 07:00 UTC")).toBeTruthy();
  });

  it("cleans up interval on unmount", () => {
    const clearSpy = vi.spyOn(global, "clearInterval");
    const nextRun  = new Date(Date.now() + 3_600_000).toISOString();
    const { unmount } = render(<Countdown nextRun={nextRun} />);
    unmount();
    expect(clearSpy).toHaveBeenCalled();
    clearSpy.mockRestore();
  });
});

// ── CSV export sanitization ──────────────────────────────────────────────────

describe("CSV export sanitization", () => {
  const escapeCsv = (v) => {
    let s = String(v ?? "").replace(/"/g, '""');
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return `"${s}"`;
  };

  it("escapes double quotes", () => {
    expect(escapeCsv('say "hello"')).toBe('"say ""hello"""');
  });

  it("prefixes formula characters with single quote", () => {
    expect(escapeCsv("=SUM(A1)")).toBe(`"'=SUM(A1)"`);
    expect(escapeCsv("+cmd")).toBe(`"'+cmd"`);
    expect(escapeCsv("-cmd")).toBe(`"'-cmd"`);
    expect(escapeCsv("@SUM")).toBe(`"'@SUM"`);
  });

  it("leaves normal text unchanged", () => {
    expect(escapeCsv("INFO")).toBe('"INFO"');
    expect(escapeCsv("Backup completed")).toBe('"Backup completed"');
  });

  it("handles null and undefined", () => {
    expect(escapeCsv(null)).toBe('""');
    expect(escapeCsv(undefined)).toBe('""');
  });
});

// ── PageErrorBoundary ────────────────────────────────────────────────────────

import { PageErrorBoundary } from "../components/ErrorBoundary.jsx";

function BrokenPage() {
  throw new Error("Page crashed!");
}

function WorkingPage() {
  return <div>Working</div>;
}

describe("PageErrorBoundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("renders children when no error", () => {
    render(<PageErrorBoundary pageName="Dashboard"><WorkingPage /></PageErrorBoundary>);
    expect(screen.getByText("Working")).toBeTruthy();
  });

  it("shows page-level error with retry button on crash", () => {
    render(<PageErrorBoundary pageName="Dashboard"><BrokenPage /></PageErrorBoundary>);
    expect(screen.getByText(/Dashboard failed to load/)).toBeTruthy();
    expect(screen.getByText("Reload Page")).toBeTruthy();
  });

  it("recovers when retry is clicked", () => {
    let shouldThrow = true;
    function MaybeBroken() {
      if (shouldThrow) throw new Error("boom");
      return <div>Recovered</div>;
    }
    render(<PageErrorBoundary pageName="Test"><MaybeBroken /></PageErrorBoundary>);
    expect(screen.getByText(/Test failed to load/)).toBeTruthy();
    shouldThrow = false;
    fireEvent.click(screen.getByText("Reload Page"));
    expect(screen.getByText("Recovered")).toBeTruthy();
  });
});
