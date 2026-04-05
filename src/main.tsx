/**
 * main.tsx — GhostBackup React Entry Point
 *
 * Renders the app once the Python backend is confirmed healthy.
 * Startup polling uses exponential backoff to catch the ready state
 * even if the IPC event arrives before the renderer has loaded.
 */

import { createRoot } from "react-dom/client";
import { useState, useEffect } from "react";
import App from "./GhostBackup";
import ErrorBoundary from "./components/ErrorBoundary";
import "./splash.css";
import "./styles.css";

const BACKOFF_DELAYS = [200, 400, 800, 1500, 2500, 4000, 5000];

function BackendProvider() {
  const [state, setState] = useState<"loading" | "ready" | "crashed">("loading");
  const [crashCode, setCrashCode] = useState<number | null>(null);

  // Add/remove splash-active class on body so splash.css styles
  // don't bleed into the main app layout
  useEffect(() => {
    if (state !== "ready") {
      document.body.classList.add("splash-active");
    } else {
      document.body.classList.remove("splash-active");
    }
  }, [state]);

  useEffect(() => {
    if (!window.ghostbackup) {
      setState("ready");
      return;
    }

    const unsubReady = window.ghostbackup.onBackendReady?.(() => {
      setState("ready");
    });

    const unsubCrash = window.ghostbackup.onBackendCrashed?.(({ exitCode }) => {
      setState("crashed");
      setCrashCode(exitCode);
    });

    // Poll with exponential backoff in case we missed the IPC ready event
    // (e.g. renderer loaded after backend was already running)
    let attempt = 0;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const poll = async () => {
      if (cancelled) return;
      try {
        const status = await window.ghostbackup!.backendStatus!();
        if (status.ready) {
          setState("ready");
          return;
        }
      } catch {
        // Backend not yet available — continue polling
      }
      const delay = BACKOFF_DELAYS[Math.min(attempt, BACKOFF_DELAYS.length - 1)];
      attempt++;
      timeoutId = setTimeout(poll, delay);
    };

    timeoutId = setTimeout(poll, 200);

    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
      unsubReady?.();
      unsubCrash?.();
    };
  }, []);

  if (state === "ready")
    return (
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    );

  return (
    <div className="splash">
      <div className="logo">GhostBackup</div>
      <div className="sub">Red Parrot Accounting</div>
      {state === "loading" && (
        <div className="status">
          <span className="dot" />
          Starting backup service...
        </div>
      )}
      {state === "crashed" && (
        <div className="error">
          ✕ The backup service stopped unexpectedly (exit code: {crashCode}).
          <br />
          <br />
          Check that Python 3.10+ is installed and run:
          <br />
          <code>pip install -r backend/requirements.txt</code>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<BackendProvider />);
