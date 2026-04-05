/**
 * errorboundary.test.jsx — Unit tests for ErrorBoundary component
 *
 * Covers: default ErrorBoundary (app-level), PageErrorBoundary (page-level),
 * error catching, fallback UI, reset/retry, componentDidCatch logging.
 *
 * Run with:  npm test
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ErrorBoundary, { PageErrorBoundary } from "../components/ErrorBoundary";

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------
function BrokenChild({ message = "Test crash" }) {
  throw new Error(message);
}

function WorkingChild() {
  return <div>Child rendered OK</div>;
}

function ConditionalChild({ shouldThrow }) {
  if (shouldThrow) throw new Error("conditional crash");
  return <div>Recovered successfully</div>;
}

// Suppress console.error from React error boundary internals
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

// ============================================================================
// ErrorBoundary (app-level)
// ============================================================================
describe("ErrorBoundary — renders children normally", () => {
  it("renders child content when no error occurs", () => {
    render(
      <ErrorBoundary>
        <WorkingChild />
      </ErrorBoundary>
    );
    expect(screen.getByText("Child rendered OK")).toBeTruthy();
  });

  it("does not show fallback UI when children render fine", () => {
    render(
      <ErrorBoundary>
        <WorkingChild />
      </ErrorBoundary>
    );
    expect(screen.queryByText("Something went wrong")).toBeNull();
    expect(screen.queryByText("Try Again")).toBeNull();
  });
});

describe("ErrorBoundary — catches errors", () => {
  it("displays fallback UI when child throws", () => {
    render(
      <ErrorBoundary>
        <BrokenChild />
      </ErrorBoundary>
    );
    expect(screen.getByText("Something went wrong")).toBeTruthy();
  });

  it("shows the error message text", () => {
    render(
      <ErrorBoundary>
        <BrokenChild message="Database connection failed" />
      </ErrorBoundary>
    );
    expect(screen.getByText("Database connection failed")).toBeTruthy();
  });

  it("shows the error icon", () => {
    render(
      <ErrorBoundary>
        <BrokenChild />
      </ErrorBoundary>
    );
    expect(screen.getByText("✖")).toBeTruthy();
  });

  it("shows Try Again button", () => {
    render(
      <ErrorBoundary>
        <BrokenChild />
      </ErrorBoundary>
    );
    expect(screen.getByText("Try Again")).toBeTruthy();
  });

  it("does not render children after catching an error", () => {
    render(
      <ErrorBoundary>
        <BrokenChild />
      </ErrorBoundary>
    );
    expect(screen.queryByText("Child rendered OK")).toBeNull();
  });
});

describe("ErrorBoundary — reset functionality", () => {
  it("recovers when Try Again is clicked and child no longer throws", () => {
    let shouldThrow = true;
    function MaybeBroken() {
      if (shouldThrow) throw new Error("boom");
      return <div>Back to normal</div>;
    }

    render(
      <ErrorBoundary>
        <MaybeBroken />
      </ErrorBoundary>
    );
    expect(screen.getByText("Something went wrong")).toBeTruthy();

    shouldThrow = false;
    fireEvent.click(screen.getByText("Try Again"));
    expect(screen.getByText("Back to normal")).toBeTruthy();
  });

  it("shows error again if child still throws after reset", () => {
    render(
      <ErrorBoundary>
        <BrokenChild message="persistent error" />
      </ErrorBoundary>
    );
    expect(screen.getByText("Something went wrong")).toBeTruthy();
    fireEvent.click(screen.getByText("Try Again"));
    expect(screen.getByText("Something went wrong")).toBeTruthy();
    expect(screen.getByText("persistent error")).toBeTruthy();
  });
});

describe("ErrorBoundary — componentDidCatch logging", () => {
  it("logs the error to console.error", () => {
    render(
      <ErrorBoundary>
        <BrokenChild message="logged error" />
      </ErrorBoundary>
    );
    expect(console.error).toHaveBeenCalled();
    const calls = console.error.mock.calls;
    const boundaryCall = calls.find(c =>
      typeof c[0] === "string" && c[0].includes("[ErrorBoundary]")
    );
    expect(boundaryCall).toBeTruthy();
  });
});

// ============================================================================
// PageErrorBoundary
// ============================================================================
describe("PageErrorBoundary — renders children normally", () => {
  it("renders child content when no error occurs", () => {
    render(
      <PageErrorBoundary pageName="Settings">
        <WorkingChild />
      </PageErrorBoundary>
    );
    expect(screen.getByText("Child rendered OK")).toBeTruthy();
  });

  it("does not show fallback when children are fine", () => {
    render(
      <PageErrorBoundary pageName="Settings">
        <WorkingChild />
      </PageErrorBoundary>
    );
    expect(screen.queryByText(/failed to load/)).toBeNull();
  });
});

describe("PageErrorBoundary — catches errors", () => {
  it("displays page name in error message", () => {
    render(
      <PageErrorBoundary pageName="Dashboard">
        <BrokenChild />
      </PageErrorBoundary>
    );
    expect(screen.getByText(/Dashboard failed to load/)).toBeTruthy();
  });

  it("shows the error message", () => {
    render(
      <PageErrorBoundary pageName="Logs">
        <BrokenChild message="API timeout" />
      </PageErrorBoundary>
    );
    expect(screen.getByText("API timeout")).toBeTruthy();
  });

  it("shows Reload Page button", () => {
    render(
      <PageErrorBoundary pageName="Settings">
        <BrokenChild />
      </PageErrorBoundary>
    );
    expect(screen.getByText("Reload Page")).toBeTruthy();
  });

  it("shows warning icon", () => {
    render(
      <PageErrorBoundary pageName="Test">
        <BrokenChild />
      </PageErrorBoundary>
    );
    // &#x26A0; renders as the warning sign character
    expect(screen.getByText("⚠")).toBeTruthy();
  });

  it("uses default page name when pageName is not provided", () => {
    render(
      <PageErrorBoundary>
        <BrokenChild />
      </PageErrorBoundary>
    );
    expect(screen.getByText(/Page failed to load/)).toBeTruthy();
  });
});

describe("PageErrorBoundary — reset functionality", () => {
  it("recovers when Reload Page is clicked and child no longer throws", () => {
    let shouldThrow = true;
    function MaybeBroken() {
      if (shouldThrow) throw new Error("page crash");
      return <div>Page recovered</div>;
    }

    render(
      <PageErrorBoundary pageName="LiveRun">
        <MaybeBroken />
      </PageErrorBoundary>
    );
    expect(screen.getByText(/LiveRun failed to load/)).toBeTruthy();

    shouldThrow = false;
    fireEvent.click(screen.getByText("Reload Page"));
    expect(screen.getByText("Page recovered")).toBeTruthy();
  });

  it("shows error again if child still throws after reload", () => {
    render(
      <PageErrorBoundary pageName="Logs">
        <BrokenChild message="still broken" />
      </PageErrorBoundary>
    );
    expect(screen.getByText(/Logs failed to load/)).toBeTruthy();
    fireEvent.click(screen.getByText("Reload Page"));
    expect(screen.getByText(/Logs failed to load/)).toBeTruthy();
    expect(screen.getByText("still broken")).toBeTruthy();
  });
});

describe("PageErrorBoundary — componentDidCatch logging", () => {
  it("logs the error with page name context", () => {
    render(
      <PageErrorBoundary pageName="Restore">
        <BrokenChild message="restore crash" />
      </PageErrorBoundary>
    );
    expect(console.error).toHaveBeenCalled();
    const calls = console.error.mock.calls;
    const boundaryCall = calls.find(c =>
      typeof c[0] === "string" && c[0].includes("[PageErrorBoundary:Restore]")
    );
    expect(boundaryCall).toBeTruthy();
  });
});

// ============================================================================
// Edge cases
// ============================================================================
describe("ErrorBoundary — edge cases", () => {
  it("handles error with empty message", () => {
    function EmptyError() { throw new Error(""); }
    render(
      <ErrorBoundary>
        <EmptyError />
      </ErrorBoundary>
    );
    expect(screen.getByText("Something went wrong")).toBeTruthy();
    expect(screen.getByText("Try Again")).toBeTruthy();
  });

  it("renders multiple children when no error", () => {
    render(
      <ErrorBoundary>
        <div>First child</div>
        <div>Second child</div>
      </ErrorBoundary>
    );
    expect(screen.getByText("First child")).toBeTruthy();
    expect(screen.getByText("Second child")).toBeTruthy();
  });
});
