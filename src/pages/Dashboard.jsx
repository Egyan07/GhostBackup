import { useState, useEffect, useCallback } from "react";
import api from "../api-client.js";
import StatusPill from "../components/StatusPill.jsx";
import SsdGauge from "../components/SsdGauge.jsx";
import Heatmap from "../components/Heatmap.jsx";
import Countdown from "../components/Countdown.jsx";
import ErrBanner from "../components/ErrBanner.jsx";
import LoadingState from "../components/LoadingState.jsx";

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try { const d = await api.dashboard(); setData(d); setError(null); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  if (loading) return <LoadingState />;

  const runs    = data?.runs || [];
  const last    = data?.last_run;
  const storage = data?.ssd_storage || {};
  const active  = data?.active_run;
  const libs    = last?.folder_summary || {};
  const schedule = data?.schedule || {};

  return (
    <div>
      <ErrBanner error={error} onDismiss={() => setError(null)} />

      {active?.status === "running" && (
        <div className="alert alert-info mb-16 flex items-center gap-12">
          <span className="alert-icon">▶</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Backup in progress · {active.overall_pct?.toFixed(0)}%</div>
            <div className="prog-track"><div className="prog-fill" style={{ width: `${active.overall_pct || 0}%` }} /></div>
          </div>
          <span className="text-sm text-secondary">{active.files_transferred} files</span>
        </div>
      )}

      <div className="stat-strip">
        {[
          { label: "Files Last Run",     value: last?.files_transferred ?? "—", sub: last?.started_at?.slice(0, 10) || "No runs yet", icon: "📁" },
          { label: "Data Transferred",   value: last?.bytes_human ?? "—",        sub: "Last backup",                                 icon: "📦" },
          { label: "30-Day Success Rate",
            value: runs.length ? `${Math.round(runs.filter(r => r.status === "success").length / runs.length * 100)}%` : "—",
            sub: `${runs.filter(r => r.status === "success").length} / ${runs.length} runs`,                                          icon: "✅" },
          { label: "Last Run Duration",  value: last?.duration_human ?? "—",     sub: last ? <StatusPill status={last.status} /> : "No data", icon: "⏱" },
        ].map((s, i) => (
          <div className="stat-card" key={i}>
            <div className="stat-label"><span>{s.icon}</span> {s.label}</div>
            <div className="stat-value">{s.value}</div>
            <div className="stat-sub">{s.sub}</div>
          </div>
        ))}
      </div>

      <div className="grid-2-1 mb-20">
        <div className="card">
          <div className="flex justify-between items-center mb-16">
            <div className="card-title" style={{ marginBottom: 0 }}>Run History · Last 30 Days</div>
            <div className="flex gap-12 text-xs text-tertiary">
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--green)", display: "inline-block" }} /> Success</span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--amber)", display: "inline-block" }} /> Partial</span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--red)",   display: "inline-block" }} /> Failed</span>
            </div>
          </div>
          {runs.length > 0
            ? <Heatmap runs={runs} />
            : <div className="empty"><div className="empty-icon">📅</div>No backup runs yet</div>}
          <div className="divider" />
          <div className="flex gap-16">
            {[
              { label: "Last run", value: last?.started_at?.slice(0, 16).replace("T", " ") || "Never" },
              { label: "Status",   value: last ? <StatusPill status={last.status} /> : "—" },
              { label: "Files",    value: last?.files_transferred ?? "—" },
            ].map(item => (
              <div key={item.label}>
                <div className="text-xs text-tertiary mb-4">{item.label}</div>
                <div className="text-sm semibold text-primary">{item.value}</div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card">
            <div className="card-title">Next Scheduled Run</div>
            <Countdown
              nextRun={data?.next_run}
              scheduleLabel={schedule.label}
              scheduleTime={schedule.time}
              timezone={schedule.timezone}
            />
          </div>
          <div className="card" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
            <div className="card-title w-full" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span>💾</span> SSD Storage
              {storage.status === "disconnected" && <span className="pill pill-failed" style={{ marginLeft: "auto", fontSize: 10 }}>Disconnected</span>}
              {storage.status === "ok"           && <span className="pill pill-success" style={{ marginLeft: "auto", fontSize: 10 }}>Mounted</span>}
            </div>
            <SsdGauge used={storage.used_gb || 0} total={storage.total_gb || 100} />
            <div className="text-xs text-tertiary">{storage.available_gb?.toFixed(1) || "—"} GB free</div>
            {storage.path && (
              <div className="text-xs mono text-tertiary" style={{ maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {storage.path}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">Folder Status · Last Run</div>
        {Object.keys(libs).length === 0 ? (
          <div className="empty"><div className="empty-icon">📂</div>Run a backup to see folder status</div>
        ) : (
          <table className="table">
            <thead><tr><th>Source Folder</th><th>Status</th><th>Files</th><th>Errors</th></tr></thead>
            <tbody>
              {Object.entries(libs).map(([name, lib]) => (
                <tr key={name}>
                  <td style={{ color: "var(--text-primary)", fontWeight: 500 }}>{name}</td>
                  <td><StatusPill status={lib.status} /></td>
                  <td className="mono">{lib.files_transferred || 0}</td>
                  <td className="mono" style={{ color: lib.files_failed ? "var(--red)" : "var(--text-tertiary)" }}>{lib.files_failed || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
