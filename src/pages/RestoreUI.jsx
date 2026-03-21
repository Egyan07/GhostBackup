import { useState, useEffect } from "react";
import api from "../api-client.js";
import StatusPill from "../components/StatusPill.jsx";
import ErrBanner from "../components/ErrBanner.jsx";
import LoadingState from "../components/LoadingState.jsx";

export default function RestoreUI() {
  const [runs, setRuns]         = useState([]);
  const [sel, setSel]           = useState(null);
  const [selLib, setSelLib]     = useState(null);
  const [dry, setDry]           = useState(true);
  const [dest, setDest]         = useState("C:\\GhostBackup\\Restore");
  const [restoring, setRestoring] = useState(false);
  const [result, setResult]     = useState(null);
  const [error, setError]       = useState(null);
  const [loading, setLoading]   = useState(true);
  const [loadingRun, setLoadingRun] = useState(false);

  useEffect(() => {
    api.getRuns(20)
      .then(d => {
        const ok = d.filter(r => r.status !== "failed");
        setRuns(ok);
        if (ok[0]) selectRun(ok[0]);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const selectRun = async (r) => {
    setSelLib(null); setResult(null); setLoadingRun(true);
    try { const full = await api.getRun(r.id); setSel(full); }
    catch { setSel(r); }
    finally { setLoadingRun(false); }
  };

  const pickFolder = async () => {
    if (window.ghostbackup?.openDirectory) {
      const p = await window.ghostbackup.openDirectory();
      if (p) setDest(p);
    }
  };

  const doRestore = async () => {
    if (!sel || !selLib) { setError("Select a backup and library first"); return; }
    setRestoring(true); setResult(null); setError(null);
    try {
      const r = await api.restore({ run_id: sel.id, library: selLib, destination: dest, dry_run: dry });
      setResult(r);
    }
    catch (e) { setError(e.message); }
    finally { setRestoring(false); }
  };

  const libs = Object.keys(sel?.folder_summary || sel?.library_summary || {});

  return (
    <div>
      <div className="alert alert-warn mb-16">
        <span className="alert-icon">⚠</span>
        <span>Restored files are copied back to the path you choose below. Original source folders are not modified.</span>
      </div>
      <ErrBanner error={error} onDismiss={() => setError(null)} />

      <div className="grid-2 mb-16">
        <div className="card">
          <div className="card-title">Select Backup Date</div>
          {loading ? <LoadingState /> : runs.length === 0
            ? <div className="empty"><div className="empty-icon">📅</div>No successful backups yet</div>
            : (
              <div className="scroll-panel">
                {runs.map(r => (
                  <div key={r.id} className={`run-item ${sel?.id === r.id ? "selected" : ""}`} onClick={() => selectRun(r)}>
                    <div className="flex justify-between items-center mb-4">
                      <span style={{ fontWeight: 600 }}>Run #{r.id} · {r.started_at?.slice(0, 10)}</span>
                      <StatusPill status={r.status} />
                    </div>
                    <div className="text-xs text-tertiary mono">{r.files_transferred} files · {r.bytes_human}</div>
                  </div>
                ))}
              </div>
            )}
        </div>

        <div className="card">
          <div className="card-title">Select Library</div>
          {!sel
            ? <div className="empty" style={{ padding: "24px 0" }}><div className="empty-icon">←</div>Choose a backup date first</div>
            : loadingRun ? <LoadingState />
            : libs.length === 0 ? <div className="empty">No library data</div>
            : libs.map(name => (
              <div key={name} className={`tree-item ${selLib === name ? "selected" : ""}`} onClick={() => setSelLib(selLib === name ? null : name)}>
                <span>📁</span>
                <span style={{ flex: 1, fontWeight: 500 }}>{name}</span>
                <span className="text-xs text-tertiary">{(sel.folder_summary || sel.library_summary)?.[name]?.files_transferred || 0} files</span>
              </div>
            ))
          }
        </div>
      </div>

      <div className="card">
        <div className="card-title">Restore Options</div>
        <div className="grid-2 mb-16" style={{ gap: 12 }}>
          <div className="fg" style={{ marginBottom: 0 }}>
            <label className="input-label">Destination path</label>
            <div className="flex gap-8">
              <input className="fi flex-1" value={dest} onChange={e => setDest(e.target.value)} />
              <button className="btn btn-secondary btn-sm" onClick={pickFolder}>Browse</button>
            </div>
          </div>
          <div className="fg" style={{ marginBottom: 0 }}>
            <label className="input-label">Selected library</label>
            <input className="fi" value={selLib || "None selected"} readOnly style={{ color: "var(--text-tertiary)" }} />
          </div>
        </div>

        <div className="flex items-center gap-12 mb-16">
          <label className="toggle" style={{ cursor: "pointer" }}>
            <input type="checkbox" checked={dry} onChange={e => { setDry(e.target.checked); setResult(null); }} />
            <span className="toggle-track" /><span className="toggle-thumb" />
          </label>
          <div>
            <div style={{ fontWeight: 600, fontSize: 13 }}>Dry-run mode <span style={{ color: dry ? "var(--green)" : "var(--red)", fontSize: 11 }}>{dry ? "(enabled)" : "(disabled)"}</span></div>
            <div className="text-xs text-tertiary">{dry ? "Preview only — no files will be written" : "Files will be written to the destination path"}</div>
          </div>
        </div>

        {!dry && (
          <div className="alert alert-warn mb-12">
            <span className="alert-icon">⚠</span>
            <span>Dry-run is off. Files will be written to <strong>{dest}</strong>.</span>
          </div>
        )}

        {result && (
          <div style={{ marginBottom: 12 }}>
            <div className="alert alert-ok mb-8">
              <span className="alert-icon">✓</span>
              <span>
                {result.dry_run
                  ? `Dry-run complete — ${result.files_to_restore} files would be restored to ${result.destination}`
                  : `✓ Restore complete — ${result.files_count} files written to ${result.destination}`}
              </span>
            </div>
            {result.dry_run && result.files?.length > 0 && (
              <div style={{ maxHeight: 220, overflowY: "auto", border: "1px solid var(--border-subtle)", borderRadius: "var(--r-md)", background: "var(--bg-raised)" }}>
                {result.files.map((f, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 12px", borderBottom: i < result.files.length - 1 ? "1px solid var(--border-subtle)" : "none", fontSize: 12 }}>
                    <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{f.name}</span>
                    <span style={{ color: "var(--text-tertiary)", marginLeft: 12, whiteSpace: "nowrap" }}>{f.size > 0 ? (f.size / 1048576).toFixed(2) + " MB" : "0 MB"}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <button className={`btn ${dry ? "btn-secondary" : "btn-primary"}`} onClick={doRestore} disabled={restoring || !sel || !selLib}>
          {restoring ? "Running…" : dry ? "Run Dry-Run Preview" : "Restore Files"}
        </button>
      </div>
    </div>
  );
}
