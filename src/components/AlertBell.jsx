import { useState, useEffect, useCallback, useRef } from "react";
import api from "../api-client.js";

const ALERT_LEVEL_CONFIG = {
  info:     { color: "var(--blue)",  bg: "var(--blue-soft)",  icon: "ℹ" },
  warn:     { color: "var(--amber)", bg: "var(--amber-soft)", icon: "⚠" },
  error:    { color: "var(--red)",   bg: "var(--red-soft)",   icon: "✖" },
  critical: { color: "var(--red)",   bg: "var(--red-soft)",   icon: "🚨" },
};

export default function AlertBell() {
  const [open,    setOpen]    = useState(false);
  const [alerts,  setAlerts]  = useState([]);
  const [unread,  setUnread]  = useState(0);
  const [loading, setLoading] = useState(false);
  const panelRef = useRef(null);

  const fetchAlerts = useCallback(async () => {
    try {
      const data = await api.getAlerts();
      setAlerts(data.alerts || []);
      setUnread(data.unread_count || 0);
    } catch (e) { console.warn("AlertBell:", e); }
  }, []);

  useEffect(() => {
    fetchAlerts();
    const id = setInterval(fetchAlerts, 15000);
    return () => clearInterval(id);
  }, [fetchAlerts]);

  useEffect(() => {
    const handler = () => fetchAlerts();
    window.addEventListener("ghostbackup-alert", handler);
    return () => window.removeEventListener("ghostbackup-alert", handler);
  }, [fetchAlerts]);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const dismiss = async (id) => {
    try {
      await api.dismissAlert(id);
      setAlerts(a => a.map(x => x.id === id ? { ...x, dismissed: true } : x));
      setUnread(u => Math.max(0, u - 1));
    } catch (e) { console.warn("AlertBell:", e); }
  };

  const dismissAll = async () => {
    setLoading(true);
    try {
      await api.dismissAllAlerts();
      setAlerts(a => a.map(x => ({ ...x, dismissed: true })));
      setUnread(0);
    } catch (e) { console.warn("AlertBell:", e); }
    setLoading(false);
  };

  const topAlert = alerts.find(a => !a.dismissed && (a.level === "critical" || a.level === "error"));

  return (
    <div ref={panelRef} style={{ position: "relative" }}>
      <button
        onClick={() => { setOpen(v => !v); if (!open) fetchAlerts(); }}
        style={{
          position: "relative", width: 34, height: 34,
          background: open ? "var(--accent-soft)" : "var(--bg-raised)",
          border: `1px solid ${open ? "rgba(124,111,247,0.3)" : "var(--border-default)"}`,
          borderRadius: "var(--r-md)", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 15, transition: "all var(--t-fast) var(--ease)",
          color: open ? "var(--accent-hover)" : "var(--text-secondary)",
        }}
      >
        🔔
        {unread > 0 && (
          <span style={{
            position: "absolute", top: -4, right: -4,
            background: topAlert ? "var(--red)" : "var(--accent)",
            color: "#fff", borderRadius: "99px",
            fontSize: 10, fontWeight: 700, lineHeight: 1,
            minWidth: 16, height: 16, padding: "0 4px",
            display: "flex", alignItems: "center", justifyContent: "center",
            border: "2px solid var(--bg-surface)",
            animation: topAlert ? "pulse-dot 1.5s ease-in-out infinite" : "none",
          }}>
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 8px)", right: 0,
          width: 360, maxHeight: 480,
          background: "var(--bg-surface)", border: "1px solid var(--border-default)",
          borderRadius: "var(--r-lg)", boxShadow: "var(--shadow-lg)",
          zIndex: 999, display: "flex", flexDirection: "column",
          animation: "fadeSlide 0.15s var(--ease)",
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderBottom: "1px solid var(--border-subtle)" }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: "var(--text-primary)" }}>
              Alerts {unread > 0 && <span style={{ color: "var(--accent-hover)", fontSize: 11 }}>· {unread} unread</span>}
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn btn-ghost btn-sm" onClick={dismissAll} disabled={loading || unread === 0} style={{ fontSize: 11, padding: "3px 8px" }}>Clear all</button>
              <button className="btn btn-ghost btn-sm" onClick={fetchAlerts} style={{ fontSize: 11, padding: "3px 8px" }}>↺</button>
            </div>
          </div>

          <div style={{ overflowY: "auto", flex: 1 }}>
            {alerts.filter(a => !a.dismissed).length === 0 ? (
              <div className="empty" style={{ padding: "32px 20px" }}>
                <div className="empty-icon">🔔</div>
                No active alerts
              </div>
            ) : alerts.filter(a => !a.dismissed).map(a => {
              const lvl = ALERT_LEVEL_CONFIG[a.level] || ALERT_LEVEL_CONFIG.info;
              return (
                <div key={a.id}
                  style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "12px 16px", borderBottom: "1px solid var(--border-subtle)", background: "transparent", transition: "background var(--t-fast)", cursor: "default" }}
                  onMouseEnter={e => e.currentTarget.style.background = "var(--bg-hover)"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                  <div style={{ width: 28, height: 28, borderRadius: "var(--r-sm)", background: lvl.bg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, flexShrink: 0, marginTop: 1 }}>
                    {lvl.icon}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 12, color: "var(--text-primary)", marginBottom: 2, lineHeight: 1.3 }}>{a.title}</div>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.4, marginBottom: 4 }}>{a.body}</div>
                    <div style={{ fontSize: 10, color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                      {a.ts ? new Date(a.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
                      {a.run_id && <span style={{ marginLeft: 6 }}>· Run #{a.run_id}</span>}
                    </div>
                  </div>
                  <button onClick={() => dismiss(a.id)}
                    style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-tertiary)", fontSize: 14, padding: "2px 4px", borderRadius: 4, lineHeight: 1, flexShrink: 0, transition: "color var(--t-fast)" }}
                    onMouseEnter={e => e.currentTarget.style.color = "var(--text-primary)"}
                    onMouseLeave={e => e.currentTarget.style.color = "var(--text-tertiary)"}
                  >×</button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
