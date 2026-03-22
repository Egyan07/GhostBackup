import { useState, useEffect } from "react";
import api from "../api-client.js";
import ErrBanner from "../components/ErrBanner.jsx";
import LoadingState from "../components/LoadingState.jsx";

const OVERLAY = {
  position: "fixed", inset: 0, zIndex: 1000,
  background: "rgba(0,0,0,0.6)", backdropFilter: "blur(3px)",
  display: "flex", alignItems: "center", justifyContent: "center",
};

function KeyRotationModal({ newKey, onConfirm, onCancel }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(newKey).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div style={OVERLAY} role="dialog" aria-modal="true" aria-labelledby="kr-title">
      <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", borderRadius: "var(--r-lg)", padding: 28, width: "min(480px, 92vw)", boxShadow: "0 24px 60px rgba(0,0,0,0.5)" }}>
        <div id="kr-title" style={{ fontSize: 16, fontWeight: 700, color: "var(--red)", marginBottom: 8 }}>⚠ Confirm Key Rotation</div>
        <p className="text-sm text-secondary" style={{ lineHeight: 1.6, marginBottom: 16 }}>
          A new encryption key has been generated. Before you continue:
        </p>
        <ul style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.8, paddingLeft: 18, marginBottom: 16 }}>
          <li>All <strong>future</strong> backups will be encrypted with the new key.</li>
          <li><strong>Existing</strong> backups on the SSD remain encrypted with the old key — keep the old key if you ever need to restore them.</li>
          <li>You <strong>must</strong> update <code style={{ fontFamily: "var(--font-mono)", fontSize: 12, background: "var(--bg-raised)", padding: "1px 5px", borderRadius: 3 }}>.env.local</code> with the new key before restarting GhostBackup.</li>
        </ul>
        <div style={{ background: "var(--bg-raised)", border: "1px solid var(--border-subtle)", borderRadius: "var(--r-md)", padding: "10px 14px", fontFamily: "var(--font-mono)", fontSize: 12, wordBreak: "break-all", marginBottom: 16, color: "var(--text-primary)" }}>
          {newKey}
        </div>
        <div className="flex gap-8 mb-16">
          <button className="btn btn-secondary btn-sm" onClick={copy}>{copied ? "✓ Copied" : "Copy Key"}</button>
        </div>
        <div className="flex gap-10">
          <button className="btn btn-danger" onClick={onConfirm}>I have saved the key — Activate</button>
          <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

export default function Settings() {
  const [cfg, setCfg]               = useState(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [testMsg, setTestMsg]       = useState(null);
  const [pruneMsg, setPruneMsg]     = useState(null);
  const [saving, setSaving]         = useState({});
  const [ssdStatus, setSsdStatus]   = useState(null);
  const [watcherStatus, setWatcherStatus] = useState(null);
  const [watcherMsg, setWatcherMsg] = useState(null);
  const [pendingKey, setPendingKey] = useState(null);
  const [keyMsg, setKeyMsg]         = useState(null);

  useEffect(() => {
    Promise.all([
      api.getConfig(),
      api.ssdStatus().catch(() => null),
      api.watcherStatus().catch(() => null),
    ]).then(([c, s, w]) => { setCfg(c); setSsdStatus(s); setWatcherStatus(w); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const refreshSsd     = () => api.ssdStatus().then(setSsdStatus).catch(() => {});
  const refreshWatcher = () => api.watcherStatus().then(setWatcherStatus).catch(() => {});

  if (loading) return <LoadingState />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <ErrBanner error={error} onDismiss={() => setError(null)} />

      {/* SSD Health */}
      <div className="card">
        <div className="card-title" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <span>💾</span> SSD Health & Status
          <button className="btn btn-ghost btn-sm" onClick={refreshSsd} style={{ marginLeft: "auto", fontSize: 12 }}>↺ Refresh</button>
        </div>
        {!ssdStatus || ssdStatus.status !== "ok" ? (
          <div className="alert alert-error">
            <span className="alert-icon">⚠</span>
            <div>
              <div style={{ fontWeight: 600, marginBottom: 3 }}>SSD Unavailable</div>
              <div style={{ fontSize: 12 }}>{ssdStatus?.error || "No SSD path configured or drive not mounted."}</div>
            </div>
          </div>
        ) : (
          <div>
            <div className="grid-3 mb-16" style={{ gap: 10 }}>
              {[
                { label: "Drive",       value: ssdStatus.path || "—",                     mono: true },
                { label: "Status",      value: <span className="pill pill-success">Mounted</span> },
                { label: "File System", value: ssdStatus.fs_type || "—",                  mono: true },
                { label: "Total",       value: `${ssdStatus.total_gb?.toFixed(1)} GB` },
                { label: "Used",        value: `${ssdStatus.used_gb?.toFixed(1)} GB` },
                { label: "Free",        value: `${ssdStatus.available_gb?.toFixed(1)} GB`,
                  color: ssdStatus.available_gb < 10 ? "var(--red)" : "var(--green)" },
              ].map(s => (
                <div key={s.label} style={{ padding: "10px 12px", background: "var(--bg-raised)", borderRadius: "var(--r-md)", border: "1px solid var(--border-subtle)" }}>
                  <div className="text-xs text-tertiary mb-4">{s.label}</div>
                  <div style={{ fontWeight: 700, fontSize: 14, color: s.color || "var(--text-primary)", fontFamily: s.mono ? "var(--font-mono)" : undefined, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.value}</div>
                </div>
              ))}
            </div>
            <div className="mb-8">
              <div className="flex justify-between text-xs text-tertiary mb-4">
                <span>Disk usage</span>
                <span>{((ssdStatus.used_gb / ssdStatus.total_gb) * 100).toFixed(1)}% used</span>
              </div>
              <div className="prog-track" style={{ height: 6 }}>
                <div className="prog-fill" style={{
                  width: `${(ssdStatus.used_gb / ssdStatus.total_gb) * 100}%`,
                  background: ssdStatus.used_gb / ssdStatus.total_gb > 0.85
                    ? "var(--red)" : ssdStatus.used_gb / ssdStatus.total_gb > 0.65
                    ? "var(--amber)" : undefined,
                }} />
              </div>
            </div>
            {ssdStatus.available_gb < 10 && (
              <div className="alert alert-warn mt-12">
                <span className="alert-icon">⚠</span>
                <span>Less than 10 GB free on backup drive. Consider pruning old backups or freeing space.</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Real-Time Watcher */}
      <div className="card">
        <div className="card-title" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <span>👁</span> Real-Time File Watcher
          <button className="btn btn-ghost btn-sm" onClick={refreshWatcher} style={{ marginLeft: "auto", fontSize: 12 }}>↺ Refresh</button>
        </div>
        <div className="text-sm text-secondary mb-16" style={{ lineHeight: 1.6 }}>
          When enabled, GhostBackup watches your source folders for changes and triggers an incremental backup automatically.
          Changes are debounced for <strong>{watcherStatus?.debounce_seconds ?? 15}s</strong> of silence before a backup fires,
          with a <strong>{watcherStatus?.cooldown_seconds ?? 120}s</strong> cooldown between runs per folder.
        </div>
        <div className="flex items-center gap-12 mb-16">
          <span className={`pill ${watcherStatus?.running ? "pill-success" : "pill-idle"}`}>
            {watcherStatus?.running ? "● Watching" : "○ Stopped"}
          </span>
          {watcherStatus?.running ? (
            <button className="btn btn-danger btn-sm" onClick={async () => {
              setWatcherMsg(null);
              try { const r = await api.watcherStop(); setWatcherStatus(r); setWatcherMsg("✓ Watcher stopped"); }
              catch (e) { setWatcherMsg(`✕ ${e.message}`); }
            }}>Stop Watcher</button>
          ) : (
            <button className="btn btn-primary btn-sm" onClick={async () => {
              setWatcherMsg(null);
              try { const r = await api.watcherStart(); setWatcherStatus(r); setWatcherMsg("✓ Watcher started"); }
              catch (e) { setWatcherMsg(`✕ ${e.message}`); }
            }}>Start Watcher</button>
          )}
          {watcherMsg && <span style={{ fontSize: 12, color: watcherMsg.startsWith("✓") ? "var(--green)" : "var(--red)" }}>{watcherMsg}</span>}
        </div>
        {watcherStatus?.sources?.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {watcherStatus.sources.map(s => (
              <div key={s.label} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "var(--bg-raised)", borderRadius: "var(--r-md)", border: "1px solid var(--border-subtle)", fontSize: 12 }}>
                <span style={{ fontWeight: 600, minWidth: 120, color: "var(--text-primary)" }}>{s.label}</span>
                <span className="text-tertiary" style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "var(--font-mono)", fontSize: 11 }}>{s.path}</span>
                {s.pending_changes > 0 && <span style={{ color: "var(--amber)", fontWeight: 600 }}>⏳ {s.pending_changes} pending</span>}
                {s.last_triggered && <span className="text-tertiary">Last triggered: {s.last_triggered}</span>}
              </div>
            ))}
          </div>
        ) : (
          <div className="alert alert-info">
            <span className="alert-icon">ℹ</span>
            <span>No sources are being watched. Add source folders in <strong>Backup Config</strong> first.</span>
          </div>
        )}
      </div>

      {/* Email Alerts */}
      <div className="card">
        <div className="card-title">Email Alerts</div>
        <div className="grid-2">
          {[{ label: "SMTP Host", key: "host" }, { label: "SMTP Port", key: "port", type: "number" }, { label: "From Address", key: "user" }].map(f => (
            <div className="fg" key={f.key}>
              <label className="input-label">{f.label}</label>
              <input className="fi" type={f.type || "text"} value={cfg?.smtp?.[f.key] || ""}
                onChange={e => setCfg(c => ({ ...c, smtp: { ...c.smtp, [f.key]: f.type === "number" ? +e.target.value : e.target.value } }))} />
            </div>
          ))}
          <div className="fg">
            <label className="input-label">Alert recipients (comma-separated)</label>
            <input className="fi"
              value={(cfg?.smtp?.recipients || []).join(", ")}
              onChange={e => setCfg(c => ({ ...c, smtp: { ...c.smtp, recipients: e.target.value.split(",").map(r => r.trim()).filter(Boolean) } }))} />
          </div>
        </div>
        <div className="flex gap-10 items-center">
          <button className="btn btn-secondary btn-sm"
            onClick={async () => {
              setSaving(s => ({ ...s, smtp: true }));
              try { await api.updateSmtp({ host: cfg.smtp?.host, port: cfg.smtp?.port, user: cfg.smtp?.user, recipients: cfg.smtp?.recipients }); }
              catch (e) { setError(e.message); }
              finally { setSaving(s => ({ ...s, smtp: false })); }
            }}
            disabled={saving.smtp}>{saving.smtp ? "Saving…" : "Save SMTP"}
          </button>
          <button className="btn btn-ghost btn-sm"
            onClick={async () => { setTestMsg(null); try { await api.testSmtp(); setTestMsg("✓ Test email sent successfully"); } catch (e) { setTestMsg(`✕ ${e.message}`); } }}>
            Send Test Email
          </button>
          {testMsg && <span style={{ fontSize: 12, color: testMsg.startsWith("✓") ? "var(--green)" : "var(--red)" }}>{testMsg}</span>}
        </div>
      </div>

      {/* Retention */}
      <div className="card">
        <div className="card-title">Retention Policy</div>
        <div className="grid-3 mb-16">
          {[
            { k: "daily_days",  label: "Keep daily backups",    min: 7,  max: 365  },
            { k: "weekly_days", label: "Keep weekly snapshots", min: 2555, max: 3650 },
            { k: "guard_days",  label: "Safety guard window",   min: 7,  max: 30   },
          ].map(f => (
            <div className="fg" style={{ marginBottom: 0 }} key={f.k}>
              <label className="input-label">{f.label}</label>
              <input className="fi" type="number" min={f.min} max={f.max}
                value={cfg?.retention?.[f.k] || f.min}
                onChange={e => setCfg(c => ({ ...c, retention: { ...c.retention, [f.k]: +e.target.value } }))} />
            </div>
          ))}
        </div>
        <div className="alert alert-info mb-12">
          <span className="alert-icon">🔒</span>
          <span>Backups within the <strong>{cfg?.retention?.guard_days || 7}-day</strong> safety window are never pruned automatically.</span>
        </div>
        <div className="flex gap-10 items-center">
          <button className="btn btn-secondary btn-sm"
            onClick={async () => {
              setSaving(s => ({ ...s, ret: true }));
              try { await api.updateRetention({ daily_days: cfg.retention?.daily_days, weekly_days: cfg.retention?.weekly_days, guard_days: cfg.retention?.guard_days }); }
              catch (e) { setError(e.message); }
              finally { setSaving(s => ({ ...s, ret: false })); }
            }}
            disabled={saving.ret}>{saving.ret ? "Saving…" : "Save Retention"}
          </button>
          <button className="btn btn-danger btn-sm"
            onClick={async () => { setPruneMsg(null); try { await api.runPrune(); setPruneMsg("✓ Prune job started"); } catch (e) { setPruneMsg(`✕ ${e.message}`); } }}>
            Run Prune Now
          </button>
          {pruneMsg && <span style={{ fontSize: 12, color: pruneMsg.startsWith("✓") ? "var(--amber)" : "var(--red)" }}>{pruneMsg}</span>}
        </div>
      </div>

      {/* Encryption */}
      <div className="card">
        <div className="card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span>🔑</span> Encryption
        </div>
        <div className="text-sm text-secondary mb-16" style={{ lineHeight: 1.6 }}>
          GhostBackup encrypts all backup files with AES-256-GCM (streaming). The key lives exclusively in
          <code style={{ fontFamily: "var(--font-mono)", fontSize: 12, background: "var(--bg-raised)", padding: "1px 5px", borderRadius: 3, margin: "0 4px" }}>.env.local</code>
          and is never written to disk or sent over the network.
        </div>
        <div className="flex items-center gap-12 mb-16">
          <span className={`pill ${cfg?.encryption_active ? "pill-success" : "pill-idle"}`}>
            {cfg?.encryption_active ? "● Encryption Active" : "○ Encryption Inactive"}
          </span>
          {!cfg?.encryption_active && (
            <div className="alert alert-warn" style={{ flex: 1, marginBottom: 0 }}>
              <span className="alert-icon">⚠</span>
              <span>No encryption key found in environment. Set <code style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>GHOSTBACKUP_ENCRYPTION_KEY</code> in <code style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>.env.local</code> to enable encryption.</span>
            </div>
          )}
        </div>
        <div className="flex gap-10 items-center">
          <button
            className="btn btn-secondary btn-sm"
            onClick={async () => {
              setKeyMsg(null);
              try {
                const { key } = await api.generateEncryptionKey();
                setPendingKey(key);
              } catch (e) { setKeyMsg(`✕ ${e.message}`); }
            }}
          >
            Generate New Key
          </button>
          {keyMsg && <span style={{ fontSize: 12, color: "var(--red)" }}>{keyMsg}</span>}
        </div>
      </div>

      {pendingKey && (
        <KeyRotationModal
          newKey={pendingKey}
          onConfirm={() => { setPendingKey(null); setKeyMsg("✓ New key activated — restart GhostBackup to apply"); }}
          onCancel={() => setPendingKey(null)}
        />
      )}

      {/* Danger Zone */}
      <div className="danger-zone">
        <div style={{ fontWeight: 700, color: "var(--red)", marginBottom: 6 }}>Danger Zone</div>
        <div className="text-sm text-secondary mb-12">These actions are irreversible. Proceed with caution.</div>
        <button className="btn btn-danger btn-sm"
          onClick={() => { if (confirm("Reset all config to defaults? This cannot be undone.\n\nBackup files on the SSD will not be deleted — only app configuration is reset.")) api.resetConfig().then(() => window.location.reload()); }}>
          Reset All Configuration
        </button>
        <div className="text-xs text-tertiary mt-8">Note: Backup files on the SSD will not be deleted — only app configuration is reset.</div>
      </div>
    </div>
  );
}
