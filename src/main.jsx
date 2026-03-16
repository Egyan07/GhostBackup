/**
 * main.jsx — GhostBackup React Entry Point
 *
 * Fixes applied:
 *  - Startup polling uses exponential backoff instead of fixed 800ms [FIX-P3]
 *  - Poll clears itself when backend becomes ready                   [FIX-P3]
 */

import { createRoot }          from "react-dom/client";
import { useState, useEffect } from "react";
import App from "./GhostBackup.jsx";

const splash = `
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{background:#0d0f12;display:flex;align-items:center;
       justify-content:center;height:100vh;font-family:monospace;color:#e8eaf0}
  .splash{text-align:center}
  .logo{font-size:32px;font-weight:800;color:#00e5cc;letter-spacing:-1px;
        font-family:'Syne',sans-serif}
  .sub{font-size:11px;color:#555;letter-spacing:3px;text-transform:uppercase;
       margin-top:6px}
  .status{font-size:11px;color:#8892a4;margin-top:32px}
  .dot{display:inline-block;width:6px;height:6px;border-radius:50%;
       background:#00e5cc;margin-right:6px;
       animation:blink 1s infinite}
  @keyframes blink{0%,100%{opacity:1}50%{opacity:0.2}}
  .error{color:#ff4757;margin-top:16px;font-size:12px;max-width:400px}
`;

// FIX-P3: Exponential backoff delays (ms) for startup poll
const BACKOFF_DELAYS = [200, 400, 800, 1500, 2500, 4000, 5000];

function BackendProvider() {
  const [state, setState]       = useState("loading");
  const [crashCode, setCrashCode] = useState(null);

  useEffect(() => {
    if (!window.ghostbackup) {
      setState("ready");
      return;
    }

    const unsubReady = window.ghostbackup.onBackendReady(() => {
      setState("ready");
    });

    const unsubCrash = window.ghostbackup.onBackendCrashed(({ exitCode }) => {
      setState("crashed");
      setCrashCode(exitCode);
    });

    // FIX-P3: Exponential backoff poll — check if backend is up in case we
    // missed the IPC event (e.g. renderer loaded after backend was already ready)
    let attempt   = 0;
    let timeoutId = null;
    let cancelled = false;

    const poll = async () => {
      if (cancelled) return;
      try {
        const status = await window.ghostbackup.backendStatus();
        if (status.ready) {
          setState("ready");
          return;
        }
      } catch {}
      // Schedule next attempt with exponential backoff
      const delay = BACKOFF_DELAYS[Math.min(attempt, BACKOFF_DELAYS.length - 1)];
      attempt++;
      timeoutId = setTimeout(poll, delay);
    };

    // Start first poll after a short delay
    timeoutId = setTimeout(poll, 200);

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
      unsubReady?.();
      unsubCrash?.();
    };
  }, []);

  if (state === "ready") return <App />;

  return (
    <>
      <style>{splash}</style>
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
            <br /><br />
            Check that Python 3.10+ is installed and run:
            <br />
            <code>pip install -r backend/requirements.txt</code>
          </div>
        )}
      </div>
    </>
  );
}

createRoot(document.getElementById("root")).render(<BackendProvider />);
