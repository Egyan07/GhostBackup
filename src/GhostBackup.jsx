import { useState, useEffect } from "react";
import AlertBell    from "./components/AlertBell.jsx";
import Dashboard    from "./pages/Dashboard.jsx";
import LiveRun      from "./pages/LiveRun.jsx";
import LogsViewer   from "./pages/LogsViewer.jsx";
import BackupConfig from "./pages/BackupConfig.jsx";
import RestoreUI    from "./pages/RestoreUI.jsx";
import Settings     from "./pages/Settings.jsx";
import api          from "./api-client.js";

const NAV = [
  { id: "dashboard", label: "Dashboard",     icon: "⊞", sec: "Monitor"   },
  { id: "liverun",   label: "Live Run",      icon: "▶", sec: "Monitor"   },
  { id: "logs",      label: "Logs",          icon: "≡", sec: "Monitor"   },
  { id: "config",    label: "Backup Config", icon: "⚙", sec: "Configure" },
  { id: "restore",   label: "Restore",       icon: "↩", sec: "Configure" },
  { id: "settings",  label: "Settings",      icon: "◈", sec: "Configure" },
];

const PAGE_TITLES = {
  dashboard: "Dashboard",
  liverun:   "Live Run",
  logs:      "Logs & History",
  config:    "Backup Config",
  restore:   "Restore",
  settings:  "Settings",
};

const PAGES = {
  dashboard: Dashboard,
  liverun:   LiveRun,
  logs:      LogsViewer,
  config:    BackupConfig,
  restore:   RestoreUI,
  settings:  Settings,
};

function PageView({ screen }) {
  const Page = PAGES[screen] ?? Dashboard;
  return <Page />;
}

function formatNextRun(health) {
  if (!health?.next_run) return "—";
  return new Date(health.next_run).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function App() {
  const [screen, setScreen] = useState("dashboard");
  const [health, setHealth] = useState(null);
  const [clock,  setClock]  = useState("");
  const [appVersion, setAppVersion] = useState("v2.0.0");
  const [appAuthor,  setAppAuthor]  = useState("");
  const [theme, setTheme] = useState(() => localStorage.getItem("gb-theme") || "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("gb-theme", theme);
  }, [theme]);

  useEffect(() => {
    window.ghostbackup?.version?.().then(v => { if (v) setAppVersion("v" + v); });
    window.ghostbackup?.author?.().then(a => { if (a) setAppAuthor(a); });
  }, []);

  useEffect(() => {
    const tick = () => {
      const n = new Date();
      setClock(`${String(n.getHours()).padStart(2, "0")}:${String(n.getMinutes()).padStart(2, "0")}:${String(n.getSeconds()).padStart(2, "0")}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const check = () => api.health().then(setHealth).catch(() => setHealth(null));
    check();
    const id = setInterval(check, 10000);
    return () => clearInterval(id);
  }, []);

  // Forward Electron alert:new IPC to DOM event so AlertBell can hear it
  useEffect(() => {
    if (!window.ghostbackup?.onAlertNew) return;
    const unsub = window.ghostbackup.onAlertNew(() => {
      window.dispatchEvent(new Event("ghostbackup-alert"));
    });
    return () => unsub?.();
  }, []);

  const sections = [...new Set(NAV.map(n => n.sec))];
  const dotCls   = health ? (health.scheduler_running ? "status-dot" : "status-dot idle") : "status-dot err";

  return (
    <div className="app">
      <div className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-icon">👻</div>
          <div className="logo-name">GhostBackup</div>
          <div className="logo-org">Red Parrot Accounting</div>
        </div>

        <div className="sidebar-status">
          <div className="status-row">
            <div className={dotCls} />
            <span>{health ? (health.scheduler_running ? "Scheduler running" : "Scheduler paused") : "Connecting…"}</span>
          </div>
        </div>

        <div className="sidebar-nav">
          {sections.map(sec => (
            <div key={sec}>
              <div className="sidebar-section-label">{sec}</div>
              {NAV.filter(n => n.sec === sec).map(n => (
                <div key={n.id} className={`nav-item ${screen === n.id ? "active" : ""}`} onClick={() => setScreen(n.id)}
                     role="button" tabIndex={0}
                     onKeyDown={e => { if (e.key === "Enter" || e.key === " ") setScreen(n.id); }}>
                  <span className="nav-icon">{n.icon}</span>
                  {n.label}
                </div>
              ))}
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <span className="version-chip">{appVersion}</span>
          {appAuthor && <span style={{ flex: 1 }}>{appAuthor}</span>}
        </div>
      </div>

      <div className="main">
        <div className="topbar">
          <div className="topbar-title">{PAGE_TITLES[screen]}</div>
          <div className="topbar-meta">
            <div className="meta-badge"><span className="dot" />{clock}</div>
            <div className="meta-badge">
              Next run: {formatNextRun(health)}
            </div>
            <button
              className="btn btn-sm"
              onClick={() => setTheme(t => t === "dark" ? "light" : "dark")}
              title="Toggle theme"
              style={{ fontSize: 16, padding: "4px 8px" }}
            >{theme === "dark" ? "☀️" : "🌙"}</button>
            <AlertBell />
          </div>
        </div>
        <div className="content"><PageView screen={screen} /></div>
      </div>
    </div>
  );
}
