import { useState, useEffect } from "react";
import api from "../api-client";
import ErrBanner from "../components/ErrBanner";
import LoadingState from "../components/LoadingState";
import type { BackupConfig as BackupConfigType, SsdStorage } from "../types";

function SsdDriveStatus({ path }: { path?: string }) {
  const [status, setStatus] = useState<SsdStorage | null>(null);

  useEffect(() => {
    if (!path) { setStatus(null); return; }
    api.ssdStatus().then(setStatus).catch(() => setStatus(null));
  }, [path]);

  if (!path) return (
    <div className="alert alert-warn">
      <span className="alert-icon">⚠</span>
      <span>No SSD destination configured. Set a path above and save.</span>
    </div>
  );

  if (!status) return null;

  const pct  = status.total_gb > 0 ? (status.used_gb / status.total_gb * 100) : 0;
  const free = status.available_gb?.toFixed(1) ?? "—";
  const isOk = status.status === "ok";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "12px 14px", background: "var(--bg-raised)", border: `1px solid ${isOk ? "var(--border-subtle)" : "rgba(248,113,113,0.25)"}`, borderRadius: "var(--r-md)" }}>
      <div style={{ fontSize: 28 }}>{isOk ? "💾" : "⚠️"}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: isOk ? "var(--text-primary)" : "var(--red)", marginBottom: 6 }}>
          {isOk ? "SSD Connected" : "SSD Unavailable"}
          <span style={{ fontSize: 11, fontWeight: 400, color: "var(--text-tertiary)", marginLeft: 8, fontFamily: "var(--font-mono)" }}>{path}</span>
        </div>
        {isOk && (
          <>
            <div className="prog-track" style={{ marginBottom: 5 }}>
              <div className={`prog-fill ${pct > 85 ? "" : "success"}`}
                style={{ width: `${pct}%`, background: pct > 85 ? "var(--red)" : pct > 65 ? "var(--amber)" : undefined }} />
            </div>
            <div className="text-xs text-tertiary">
              {status.used_gb?.toFixed(1)} GB used · <span style={{ color: "var(--green)" }}>{free} GB free</span> · {status.total_gb?.toFixed(0)} GB total
            </div>
          </>
        )}
        {!isOk && <div className="text-xs text-red">{status.error || "Drive not found or inaccessible"}</div>}
      </div>
      {isOk && (
        <div style={{ flexShrink: 0, textAlign: "right" }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: pct > 85 ? "var(--red)" : "var(--text-primary)", letterSpacing: -1 }}>{pct.toFixed(0)}%</div>
          <div className="text-xs text-tertiary">used</div>
        </div>
      )}
    </div>
  );
}

export default function BackupConfig() {
  const [cfg, setCfg]         = useState<BackupConfigType | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [saved, setSaved]     = useState(false);
  const [error, setError]     = useState<Error | null>(null);
  const [newEx, setNewEx]     = useState("");
  const [addingFolder, setAddingFolder]   = useState(false);
  const [newFolder, setNewFolder]         = useState({ label: "", path: "", enabled: true });

  useEffect(() => {
    api.getConfig()
      .then(d => { setCfg(d); setLoading(false); })
      .catch(e => { setError(e as Error); setLoading(false); });
  }, []);

  if (loading) return <LoadingState />;
  if (!cfg) return <ErrBanner error={error} />;

  const buildPayload = (c: BackupConfigType) => ({
    ssd_path:         c.ssd_path,
    schedule_time:    c.schedule?.time,
    timezone:         c.schedule?.timezone,
    concurrency:      c.performance?.concurrency,
    max_file_size_gb: c.performance?.max_file_size_gb,
    verify_checksums: c.backup?.verify_checksums,
    exclude_patterns: c.backup?.exclude_patterns,
  });

  const save = async () => {
    setSaving(true); setError(null);
    try {
      await api.updateConfig(buildPayload(cfg));
      setSaved(true); setTimeout(() => setSaved(false), 2500);
    } catch (e) { setError(e as Error); }
    finally { setSaving(false); }
  };

  const pickSsd = async () => {
    if (!window.ghostbackup?.openDirectory) return;
    const p = await window.ghostbackup.openDirectory();
    if (!p) return;
    const updated = { ...cfg, ssd_path: p };
    setCfg(updated);
    setSaving(true); setError(null);
    try {
      await api.updateConfig(buildPayload(updated));
      setSaved(true); setTimeout(() => setSaved(false), 2500);
    } catch (e) { setError(e as Error); }
    finally { setSaving(false); }
  };

  const pickFolderPath = async () => {
    if (!window.ghostbackup?.openDirectory) return;
    const p = await window.ghostbackup.openDirectory();
    if (p) setNewFolder(f => ({ ...f, path: p, label: f.label || p.split(/[\\/]/).pop() || p }));
  };

  const addFolder = async () => {
    if (!newFolder.label || !newFolder.path) return;
    try {
      const { config } = await api.addSite(newFolder);
      setCfg(config);
      setNewFolder({ label: "", path: "", enabled: true });
      setAddingFolder(false);
    } catch (e) { setError(e as Error); }
  };

  const removeFolder = async (label: string) => {
    try {
      const { config } = await api.removeSite(label);
      setCfg(config);
    } catch (e) { setError(e as Error); }
  };

  const toggleFolder = async (label: string, enabled: boolean) => {
    setError(null);
    try {
      const { source } = await api.updateSite(label, { enabled });
      setCfg(c => c ? ({
        ...c,
        sources: (c.sources || []).map(s => (s.label === label || s.name === label ? source : s)),
      }) : c);
    } catch (e) { setError(e as Error); }
  };

  const addEx = () => {
    if (!newEx.trim()) return;
    if ((cfg.backup?.exclude_patterns || []).includes(newEx.trim())) return;
    setCfg(c => c ? ({ ...c, backup: { ...c.backup, exclude_patterns: [...(c.backup?.exclude_patterns || []), newEx.trim()] } }) : c);
    setNewEx("");
  };

  const remEx = (p: string) => setCfg(c => c ? ({ ...c, backup: { ...c.backup, exclude_patterns: (c.backup?.exclude_patterns || []).filter(e => e !== p) } }) : c);

  const sources = cfg.sources || cfg.sites || [];

  return (
    <div>
      <ErrBanner error={error} onDismiss={() => setError(null)} />

      <div className="card mb-16">
        <div className="card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span>💾</span> Backup Destination — Local SSD
        </div>
        <div className="flex gap-10 items-center mb-12">
          <input className="fi flex-1" value={cfg.ssd_path || ""}
            onChange={e => setCfg(c => c ? ({ ...c, ssd_path: e.target.value }) : c)}
            placeholder="e.g. D:\GhostBackup  or  E:\Backups\RedParrot" />
          <button className="btn btn-secondary btn-sm" onClick={pickSsd}>Browse…</button>
          <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
        </div>
        <SsdDriveStatus path={cfg.ssd_path} />
      </div>

      <div className="grid-2 mb-16">
        <div className="card">
          <div className="card-title">Schedule</div>
          <div className="fg">
            <label className="input-label">Daily backup time</label>
            <input className="fi" type="time" value={cfg.schedule?.time || "08:00"}
              onChange={e => setCfg(c => c ? ({ ...c, schedule: { ...c.schedule, time: e.target.value } }) : c)} />
          </div>
          <div className="fg">
            <label className="input-label">Timezone</label>
            <select className="fi" value={cfg.schedule?.timezone || "Europe/London"}
              onChange={e => setCfg(c => c ? ({ ...c, schedule: { ...c.schedule, timezone: e.target.value } }) : c)}>
              <option value="Europe/London">Europe/London (GMT/BST)</option>
              <option value="UTC">UTC</option>
              <option value="Europe/Dublin">Europe/Dublin (IST)</option>
              <option value="Europe/Paris">Europe/Paris (CET)</option>
              <option value="Europe/Berlin">Europe/Berlin (CET)</option>
              <option value="Europe/Amsterdam">Europe/Amsterdam (CET)</option>
              <option value="Europe/Zurich">Europe/Zurich (CET)</option>
              <option value="America/New_York">America/New_York (EST/EDT)</option>
              <option value="America/Chicago">America/Chicago (CST/CDT)</option>
              <option value="America/Los_Angeles">America/Los_Angeles (PST/PDT)</option>
              <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
              <option value="Asia/Kathmandu">Asia/Kathmandu (UTC+5:45)</option>
              <option value="Asia/Singapore">Asia/Singapore (SGT)</option>
              <option value="Australia/Sydney">Australia/Sydney (AEST)</option>
            </select>
          </div>
        </div>

        <div className="card">
          <div className="card-title">Performance</div>
          <div className="fg">
            <label className="input-label">Copy threads — <span className="text-accent">{cfg.performance?.concurrency || 4}</span></label>
            <input className="fi" type="range" min="1" max="16"
              value={cfg.performance?.concurrency || 4}
              onChange={e => setCfg(c => c ? ({ ...c, performance: { ...c.performance, concurrency: +e.target.value } }) : c)} />
          </div>
          <div className="fg">
            <label className="input-label">Max file size (GB)</label>
            <input className="fi" type="number" min="1" max="100"
              value={cfg.performance?.max_file_size_gb || 5}
              onChange={e => setCfg(c => c ? ({ ...c, performance: { ...c.performance, max_file_size_gb: +e.target.value } }) : c)} />
          </div>
          <div className="flex items-center gap-12">
            <label className="toggle">
              <input type="checkbox" checked={cfg.backup?.verify_checksums ?? true}
                onChange={e => setCfg(c => c ? ({ ...c, backup: { ...c.backup, verify_checksums: e.target.checked } }) : c)} />
              <span className="toggle-track" /><span className="toggle-thumb" />
            </label>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Verify checksums after copy</div>
              <div className="text-xs text-tertiary">Slower but detects corruption. Recommended.</div>
            </div>
          </div>
        </div>
      </div>

      <div className="card mb-16">
        <div className="flex justify-between items-center mb-16">
          <div className="card-title" style={{ marginBottom: 0, display: "flex", alignItems: "center", gap: 8 }}>
            <span>📁</span> Source Folders
            <span style={{ background: "var(--bg-overlay)", border: "1px solid var(--border-subtle)", borderRadius: "var(--r-sm)", padding: "1px 8px", fontSize: 11, color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
              {sources.filter(s => s.enabled !== false).length} active
            </span>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => setAddingFolder(v => !v)}>
            {addingFolder ? "Cancel" : "+ Add Folder"}
          </button>
        </div>

        {addingFolder && (
          <div style={{ background: "var(--bg-raised)", border: "1px solid var(--border-default)", borderRadius: "var(--r-md)", padding: "16px", marginBottom: 12 }}>
            <div className="fg mb-8">
              <label className="input-label">Display label</label>
              <input className="fi" placeholder="e.g. Client Documents" value={newFolder.label}
                onChange={e => setNewFolder(f => ({ ...f, label: e.target.value }))} />
            </div>
            <div className="fg" style={{ marginBottom: 12 }}>
              <label className="input-label">Folder path</label>
              <div className="flex gap-8">
                <input className="fi flex-1 mono" placeholder="C:\Users\Shared\Documents" value={newFolder.path}
                  onChange={e => setNewFolder(f => ({ ...f, path: e.target.value }))} />
                <button className="btn btn-secondary btn-sm" onClick={pickFolderPath}>Browse…</button>
              </div>
            </div>
            <div className="flex gap-8">
              <button className="btn btn-primary btn-sm" onClick={addFolder} disabled={!newFolder.label || !newFolder.path}>Add Folder</button>
              <button className="btn btn-ghost btn-sm" onClick={() => { setAddingFolder(false); setNewFolder({ label: "", path: "", enabled: true }); }}>Cancel</button>
            </div>
          </div>
        )}

        {sources.length === 0 ? (
          <div className="empty" style={{ padding: "24px 0" }}><div className="empty-icon">📁</div>No source folders added yet. Add a folder to start backing up.</div>
        ) : sources.map(s => (
          <div className="site-row" key={s.label || s.name} style={{ opacity: s.enabled !== false ? 1 : 0.5 }}>
            <label className="toggle">
              <input type="checkbox" checked={s.enabled !== false} onChange={e => toggleFolder(s.label || s.name || "", e.target.checked)} />
              <span className="toggle-track" /><span className="toggle-thumb" />
            </label>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{s.label || s.name}</div>
              <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 2, fontFamily: "var(--font-mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.path}</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => removeFolder(s.label || s.name || "")} style={{ color: "var(--red)", flexShrink: 0 }}>Remove</button>
          </div>
        ))}
      </div>

      <div className="card mb-16">
        <div className="card-title">Exclusion Patterns</div>
        <div className="text-sm text-secondary mb-12">Files or folders matching these patterns will be skipped. Supports wildcards.</div>
        <div className="flex gap-8">
          <input className="fi flex-1 mono" placeholder="e.g.  ~$*  or  *.tmp  or  Thumbs.db" value={newEx}
            onChange={e => setNewEx(e.target.value)} onKeyDown={e => e.key === "Enter" && addEx()} />
          <button className="btn btn-secondary btn-sm" onClick={addEx}>Add</button>
        </div>
        <div className="tag-list">
          {(cfg.backup?.exclude_patterns || []).map(p => (
            <span className="tag" key={p}>{p}<span className="tag-x" onClick={() => remEx(p)}>×</span></span>
          ))}
        </div>
      </div>

      <div className="flex gap-10">
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : saved ? "✓ Saved" : "Save Configuration"}
        </button>
        <button className="btn btn-secondary" onClick={() => api.startRun({ full: true })}>
          ▶ Run Full Backup Now
        </button>
      </div>
    </div>
  );
}
