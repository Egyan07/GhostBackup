import { useState, useEffect, useCallback } from "react";
import api from "../api-client.js";
import StatusPill from "../components/StatusPill.jsx";
import ErrBanner from "../components/ErrBanner.jsx";

export default function LiveRun() {
  const [status, setStatus] = useState(null);
  const [error, setError]   = useState(null);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);

  const poll = useCallback(async () => {
    try { const s = await api.runStatus(); setStatus(s); setError(null); }
    catch (e) { setError(e.message); }
  }, []);

  useEffect(() => {
    poll();
    const id = setInterval(poll, 1000);
    return () => clearInterval(id);
  }, [poll]);

  const startRun = async (full = false) => {
    setStarting(true); setError(null);
    try { await api.startRun({ full }); await poll(); }
    catch (e) { setError(e.message); }
    finally { setStarting(false); }
  };

  const stopRun = async () => {
    setStopping(true);
    try { await api.stopRun(); await poll(); }
    catch (e) { setError(e.message); }
    finally { setStopping(false); }
  };

  const isRunning = status?.status === "running";
  const pct  = status?.overall_pct || 0;
  const feed = status?.feed || [];
  const libs = status?.libraries || {};

  const elapsed = (() => {
    if (!status?.started_at || !isRunning) return null;
    const utcStr = status.started_at.endsWith("Z") ? status.started_at : status.started_at + "Z";
    const s = Math.floor((Date.now() - new Date(utcStr)) / 1000);
    if (s < 0) return null;
    return `${Math.floor(s / 60)}m ${s % 60}s elapsed`;
  })();

  return (
    <div>
      <ErrBanner error={error} onDismiss={() => setError(null)} />

      <div className="card mb-16">
        <div className="flex justify-between items-center mb-16">
          <div>
            <div className="card-title" style={{ marginBottom: 4 }}>Overall Progress</div>
            <div style={{ fontSize: 42, fontWeight: 800, letterSpacing: -2, lineHeight: 1, color: "var(--text-primary)" }}>
              {pct.toFixed(0)}<span style={{ fontSize: 20, color: "var(--text-tertiary)", letterSpacing: 0, marginLeft: 2 }}>%</span>
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <StatusPill status={status?.status || "idle"} />
            {elapsed && <div className="text-xs text-tertiary mt-4">{elapsed}</div>}
            {isRunning && (
              <div className="text-xs text-tertiary mt-4 mono">
                {status.files_transferred} transferred · {status.files_failed > 0 ? <span className="text-red">{status.files_failed} errors</span> : "0 errors"}
              </div>
            )}
          </div>
        </div>

        <div className="prog-track" style={{ height: 6, marginBottom: 20 }}>
          <div className="prog-fill" style={{ width: `${pct}%` }} />
        </div>

        <div className="flex gap-10">
          {!isRunning ? (
            <>
              <button className="btn btn-primary" onClick={() => startRun(false)} disabled={starting}>
                {starting ? "Starting…" : "▶ Run Incremental"}
              </button>
              <button className="btn btn-secondary" onClick={() => startRun(true)} disabled={starting}>
                ▶ Run Full Backup
              </button>
            </>
          ) : (
            <button className="btn btn-danger" onClick={stopRun} disabled={stopping}>
              {stopping ? "Stopping…" : "■ Stop"}
            </button>
          )}
        </div>
      </div>

      <div className="grid-2 mb-16">
        <div className="card">
          <div className="card-title">Per-Library Progress</div>
          {Object.keys(libs).length === 0 ? (
            <div className="empty" style={{ padding: "24px 0" }}><div className="empty-icon">📁</div>Start a backup run</div>
          ) : Object.entries(libs).map(([name, lib]) => (
            <div key={name} style={{ marginBottom: 16 }}>
              <div className="flex justify-between text-sm mb-8">
                <span style={{ fontWeight: 500 }}>{name}</span>
                <span className="text-tertiary mono">{lib.pct || 0}%</span>
              </div>
              <div className="prog-track">
                <div className={`prog-fill ${lib.pct === 100 ? "success" : ""}`} style={{ width: `${lib.pct || 0}%` }} />
              </div>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-title">Live Statistics</div>
          {[
            { label: "Files Transferred", value: status?.files_transferred ?? "—" },
            { label: "Files Failed",      value: status?.files_failed ?? "—" },
            { label: "Data Written",      value: status?.bytes_transferred ? `${(status.bytes_transferred / 1024 ** 3).toFixed(2)} GB` : "—" },
            { label: "Run Status",        value: <StatusPill status={status?.status || "idle"} /> },
          ].map(s => (
            <div key={s.label} className="flex justify-between items-center" style={{ padding: "10px 0", borderBottom: "1px solid var(--border-subtle)" }}>
              <span className="text-secondary text-sm">{s.label}</span>
              <span style={{ fontWeight: 600, fontSize: 14, fontFamily: "var(--font-mono)" }}>{s.value}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-title">Live File Feed</div>
        <div className="scroll-panel">
          {feed.length === 0 ? (
            <div className="empty" style={{ padding: "24px 0" }}><div className="empty-icon">📂</div>Awaiting backup activity…</div>
          ) : feed.map((f, i) => (
            <div className="feed-item" key={i}>
              <span style={{ fontSize: 10, color: "var(--text-tertiary)", width: 70, flexShrink: 0, fontFamily: "var(--font-mono)" }}>{f.time}</span>
              <span style={{ color: "var(--green)", fontSize: 12 }}>✓</span>
              <span style={{ flex: 1, fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.file}</span>
              <span style={{ fontSize: 11, color: "var(--text-tertiary)", flexShrink: 0, fontFamily: "var(--font-mono)" }}>{f.size_mb} MB</span>
              <span style={{ fontSize: 11, color: "var(--text-tertiary)", width: 110, textAlign: "right", flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{f.library}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
