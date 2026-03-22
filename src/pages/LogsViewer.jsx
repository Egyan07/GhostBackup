import { useState, useEffect } from "react";
import api from "../api-client.js";
import StatusPill from "../components/StatusPill.jsx";
import ErrBanner from "../components/ErrBanner.jsx";
import LoadingState from "../components/LoadingState.jsx";

export default function LogsViewer() {
  const [runs, setRuns]     = useState([]);
  const [sel, setSel]       = useState(null);
  const [logs, setLogs]     = useState([]);
  const [rd, setRd]         = useState(null);
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);

  useEffect(() => {
    api.getRuns(30)
      .then(d => { setRuns(d); if (d[0]) setSel(d[0]); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!sel) return;
    Promise.all([
      api.getRunLogs(sel.id, filter === "ALL" ? undefined : filter),
      api.getRun(sel.id),
    ])
      .then(([l, r]) => { setLogs(l); setRd(r); })
      .catch(e => setError(e.message));
  }, [sel, filter]);

  const filtered = search
    ? logs.filter(l => l.message?.toLowerCase().includes(search.toLowerCase()))
    : logs;

  const lvlColor = { INFO: "var(--text-secondary)", WARN: "var(--amber)", ERROR: "var(--red)" };

  const exportCsv = () => {
    const escape = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const rows = [["Time", "Level", "Message"], ...filtered.map(l => [l.logged_at, l.level, l.message])];
    const blob = new Blob([rows.map(r => r.map(escape).join(",")).join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `run_${sel?.id}_logs.csv`;
    a.click();
  };

  return (
    <div className="grid-2-1" style={{ gap: 16, alignItems: "start" }}>
      <div>
        <ErrBanner error={error} onDismiss={() => setError(null)} />
        <div className="card mb-16">
          <div className="flex items-center gap-10 mb-12" style={{ flexWrap: "wrap" }}>
            <div className="card-title" style={{ marginBottom: 0, flex: 1 }}>
              {sel ? `Run #${sel.id} · ${sel.started_at?.slice(0, 10)}` : "Select a run"}
            </div>
            <div className="flex gap-6">
              {["ALL", "INFO", "WARN", "ERROR"].map(f => (
                <button key={f} className={`btn btn-sm ${filter === f ? "btn-primary" : "btn-ghost"}`} onClick={() => setFilter(f)}>{f}</button>
              ))}
              <button className="btn btn-secondary btn-sm" onClick={exportCsv} disabled={!sel}>Export</button>
            </div>
          </div>
          <input className="fi mb-12" placeholder="Search logs…" value={search} onChange={e => setSearch(e.target.value)} style={{ marginBottom: 12 }} />
          <div className="scroll-panel">
            {!sel
              ? <div className="empty" style={{ padding: "24px 0" }}><div className="empty-icon">📋</div>Select a run from the right panel</div>
              : filtered.length === 0
                ? <div className="empty" style={{ padding: "24px 0" }}><div className="empty-icon">🔍</div>No logs found</div>
                : (
                  <table className="table">
                    <thead><tr><th style={{ width: 80 }}>Time</th><th style={{ width: 60 }}>Level</th><th>Message</th></tr></thead>
                    <tbody>
                      {filtered.map((l, i) => (
                        <tr key={i}>
                          <td className="mono text-tertiary" style={{ fontSize: 11 }}>{l.logged_at?.slice(11, 19)}</td>
                          <td style={{ color: lvlColor[l.level] || "var(--text-secondary)", fontWeight: 600, fontSize: 11 }}>{l.level}</td>
                          <td style={{ color: lvlColor[l.level] || "var(--text-secondary)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{l.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
          </div>
        </div>

        {rd && (
          <div className="card">
            <div className="card-title">Run Summary</div>
            <div className="grid-3" style={{ gap: 10 }}>
              {[
                { k: "Transferred", v: rd.files_transferred }, { k: "Failed",   v: rd.files_failed },
                { k: "Duration",    v: rd.duration_human },    { k: "Data",     v: rd.bytes_human },
                { k: "Status",      v: <StatusPill status={rd.status} /> }, { k: "Run ID", v: `#${rd.id}` },
              ].map(s => (
                <div key={s.k} style={{ padding: "10px 12px", background: "var(--bg-raised)", borderRadius: "var(--r-md)" }}>
                  <div className="text-xs text-tertiary mb-4">{s.k}</div>
                  <div style={{ fontWeight: 700, fontSize: 16 }}>{s.v}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="card" style={{ position: "sticky", top: 0 }}>
        <div className="card-title">Run History</div>
        {loading ? <LoadingState /> : runs.length === 0 ? (
          <div className="empty" style={{ padding: "24px 0" }}><div className="empty-icon">📅</div>No runs yet</div>
        ) : (
          <div className="scroll-panel">
            {runs.map(r => (
              <div key={r.id} className={`run-item ${sel?.id === r.id ? "selected" : ""}`} onClick={() => setSel(r)}>
                <div className="flex justify-between items-center mb-4">
                  <span style={{ fontWeight: 600, fontSize: 13 }}>Run #{r.id}</span>
                  <StatusPill status={r.status} />
                </div>
                <div className="text-xs text-tertiary mono">{r.started_at?.slice(0, 16).replace("T", " ")} · {r.duration_human}</div>
                <div className="text-xs text-tertiary mt-4">{r.files_transferred} files transferred</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
