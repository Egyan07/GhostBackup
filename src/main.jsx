/**
 * main.jsx — GhostBackup React Entry Point
 *
 * Wraps the app in a BackendProvider that:
 *  - Waits for the Electron main process to signal backend ready
 *  - Shows a loading splash while backend is starting
 *  - Shows a crash screen if backend dies
 *  - Provides the API URL to all components via context
 */

import { createRoot }     from "react-dom/client";
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

function BackendProvider() {
  const [state, setState] = useState("loading"); // loading | ready | crashed
  const [crashCode, setCrashCode] = useState(null);

  useEffect(() => {
    // Check if running in Electron
    if (!window.ghostbackup) {
      // Running in browser (dev without Electron) — assume backend is up
      setState("ready");
      return;
    }

    // Listen for backend ready event from main process
    const unsubReady = window.ghostbackup.onBackendReady(() => {
      setState("ready");
    });

    const unsubCrash = window.ghostbackup.onBackendCrashed(({ exitCode }) => {
      setState("crashed");
      setCrashCode(exitCode);
    });

    // Also poll in case we missed the event (renderer loaded after backend ready)
    const poll = setInterval(async () => {
      try {
        const status = await window.ghostbackup.backendStatus();
        if (status.ready) {
          clearInterval(poll);
          setState("ready");
        }
      } catch {}
    }, 800);

    return () => {
      unsubReady?.();
      unsubCrash?.();
      clearInterval(poll);
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
          <>
            <div className="error">
              ✕ The backup service stopped unexpectedly (exit code: {crashCode}).
              <br /><br />
              Check that Python 3.10+ is installed and run:
              <br />
              <code>pip install -r backend/requirements.txt</code>
            </div>
          </>
        )}
      </div>
    </>
  );
}

createRoot(document.getElementById("root")).render(<BackendProvider />);
