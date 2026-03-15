import { useState, useEffect, useCallback, useRef } from "react";
import api from "./api-client.js";

// ─── DESIGN TOKENS ────────────────────────────────────────────────────────────
const css = `
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@300;400;500&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    /* Base surfaces */
    --bg-base:    #0e0f11;
    --bg-surface: #13141a;
    --bg-raised:  #1a1d26;
    --bg-overlay: #21253a;
    --bg-hover:   rgba(255,255,255,0.04);
    --bg-active:  rgba(255,255,255,0.07);

    /* Borders */
    --border-subtle:  rgba(255,255,255,0.06);
    --border-default: rgba(255,255,255,0.10);
    --border-strong:  rgba(255,255,255,0.18);

    /* Text */
    --text-primary:   #f0f1f5;
    --text-secondary: #8b8fa8;
    --text-tertiary:  #555872;
    --text-disabled:  #363949;

    /* Accent — violet */
    --accent:         #7c6ff7;
    --accent-soft:    rgba(124,111,247,0.12);
    --accent-hover:   #9488fa;
    --accent-glow:    rgba(124,111,247,0.25);

    /* Semantic */
    --green:      #34d399;
    --green-soft: rgba(52,211,153,0.10);
    --amber:      #fbbf24;
    --amber-soft: rgba(251,191,36,0.10);
    --red:        #f87171;
    --red-soft:   rgba(248,113,113,0.10);
    --blue:       #60a5fa;
    --blue-soft:  rgba(96,165,250,0.10);

    /* Typography */
    --font-sans: 'Plus Jakarta Sans', -apple-system, sans-serif;
    --font-mono: 'DM Mono', monospace;

    /* Radii */
    --r-sm:  6px;
    --r-md:  10px;
    --r-lg:  14px;
    --r-xl:  20px;

    /* Shadows */
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3);
    --shadow-md: 0 4px 16px rgba(0,0,0,0.5), 0 1px 4px rgba(0,0,0,0.3);
    --shadow-lg: 0 8px 32px rgba(0,0,0,0.6), 0 2px 8px rgba(0,0,0,0.4);
    --shadow-accent: 0 0 0 1px var(--accent-glow), 0 4px 16px rgba(124,111,247,0.2);

    /* Transitions */
    --ease: cubic-bezier(0.16, 1, 0.3, 1);
    --t-fast: 120ms;
    --t-mid:  200ms;
    --t-slow: 350ms;
  }

  body {
    background: var(--bg-base);
    color: var(--text-primary);
    font-family: var(--font-sans);
    font-size: 13px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
    overflow: hidden;
  }

  /* ─── SCROLLBAR ─── */
  ::-webkit-scrollbar { width: 4px; height: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border-default); border-radius: 99px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--border-strong); }

  /* ─── APP SHELL ─── */
  .app { display: flex; height: 100vh; background: var(--bg-base); }

  /* ─── SIDEBAR ─── */
  .sidebar {
    width: 220px; min-width: 220px;
    background: var(--bg-surface);
    border-right: 1px solid var(--border-subtle);
    display: flex; flex-direction: column;
    padding: 0;
  }

  .sidebar-logo {
    padding: 20px 16px 16px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .logo-icon {
    width: 32px; height: 32px;
    background: linear-gradient(135deg, var(--accent), #5b52e0);
    border-radius: var(--r-md);
    display: flex; align-items: center; justify-content: center;
    font-size: 16px;
    box-shadow: var(--shadow-accent);
    margin-bottom: 10px;
  }

  .logo-name {
    font-size: 14px; font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.3px;
  }

  .logo-org {
    font-size: 11px; color: var(--text-tertiary);
    font-weight: 400; margin-top: 1px;
  }

  .sidebar-status {
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .status-row {
    display: flex; align-items: center; gap: 7px;
    font-size: 11px; color: var(--text-secondary);
  }

  .status-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 0 2px rgba(52,211,153,0.2);
    animation: pulse-dot 2.5s ease-in-out infinite;
    flex-shrink: 0;
  }
  .status-dot.idle { background: var(--text-tertiary); box-shadow: none; animation: none; }
  .status-dot.err  { background: var(--red); box-shadow: 0 0 0 2px rgba(248,113,113,0.2); animation: none; }

  @keyframes pulse-dot {
    0%, 100% { box-shadow: 0 0 0 2px rgba(52,211,153,0.2); }
    50%       { box-shadow: 0 0 0 4px rgba(52,211,153,0.08); }
  }

  .sidebar-section-label {
    font-size: 10px; font-weight: 600;
    color: var(--text-tertiary);
    letter-spacing: 0.6px; text-transform: uppercase;
    padding: 14px 16px 5px;
  }

  .sidebar-nav { flex: 1; padding: 6px 8px; overflow-y: auto; }

  .nav-item {
    display: flex; align-items: center; gap: 9px;
    padding: 7px 10px; border-radius: var(--r-md);
    cursor: pointer; font-size: 13px; font-weight: 500;
    color: var(--text-secondary);
    transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease);
    user-select: none; position: relative;
  }

  .nav-item:hover { background: var(--bg-hover); color: var(--text-primary); }

  .nav-item.active {
    background: var(--accent-soft);
    color: var(--accent-hover);
  }

  .nav-icon {
    width: 18px; height: 18px; opacity: 0.7;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; flex-shrink: 0;
    transition: opacity var(--t-fast);
  }

  .nav-item.active .nav-icon,
  .nav-item:hover .nav-icon { opacity: 1; }

  .sidebar-footer {
    padding: 12px 16px;
    border-top: 1px solid var(--border-subtle);
    font-size: 11px; color: var(--text-tertiary);
    display: flex; align-items: center; gap: 8px;
  }

  .version-chip {
    background: var(--bg-overlay);
    border: 1px solid var(--border-subtle);
    border-radius: var(--r-sm);
    padding: 2px 7px; font-size: 10px;
    color: var(--text-tertiary);
    font-family: var(--font-mono);
  }

  /* ─── MAIN AREA ─── */
  .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }

  .topbar {
    height: 52px; min-height: 52px;
    background: var(--bg-surface);
    border-bottom: 1px solid var(--border-subtle);
    display: flex; align-items: center;
    padding: 0 24px; gap: 12px;
  }

  .topbar-title {
    font-size: 15px; font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.3px;
    flex: 1;
  }

  .topbar-meta {
    display: flex; align-items: center; gap: 6px;
  }

  .meta-badge {
    display: flex; align-items: center; gap: 5px;
    background: var(--bg-raised);
    border: 1px solid var(--border-subtle);
    border-radius: var(--r-sm);
    padding: 4px 9px;
    font-size: 11px; color: var(--text-secondary);
    font-family: var(--font-mono);
  }

  .meta-badge .dot { width: 5px; height: 5px; border-radius: 50%; background: var(--green); }

  .content { flex: 1; overflow-y: auto; padding: 24px; }

  /* ─── CARDS ─── */
  .card {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--r-lg);
    padding: 20px;
    transition: border-color var(--t-mid) var(--ease);
  }

  .card:hover { border-color: var(--border-default); }

  .card-title {
    font-size: 11px; font-weight: 600;
    color: var(--text-tertiary);
    text-transform: uppercase; letter-spacing: 0.7px;
    margin-bottom: 16px;
  }

  /* ─── STAT STRIP ─── */
  .stat-strip { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 20px; }

  .stat-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--r-lg);
    padding: 18px 20px;
    transition: all var(--t-mid) var(--ease);
    position: relative; overflow: hidden;
  }

  .stat-card::before {
    content: ''; position: absolute;
    top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, var(--accent), transparent);
    opacity: 0; transition: opacity var(--t-mid);
  }

  .stat-card:hover { border-color: var(--border-default); }
  .stat-card:hover::before { opacity: 1; }

  .stat-label {
    font-size: 11px; color: var(--text-tertiary);
    font-weight: 500; margin-bottom: 8px;
    display: flex; align-items: center; gap: 6px;
  }

  .stat-value {
    font-size: 26px; font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.8px; line-height: 1;
  }

  .stat-sub {
    font-size: 11px; color: var(--text-tertiary);
    margin-top: 5px;
  }

  /* ─── GRIDS ─── */
  .grid-2   { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .grid-3   { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
  .grid-2-1 { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; }

  /* ─── HEATMAP ─── */
  .heatmap { display: flex; gap: 3px; flex-wrap: wrap; }

  .hm-day {
    width: 18px; height: 18px; border-radius: 4px;
    background: var(--bg-raised);
    cursor: pointer; position: relative;
    transition: transform var(--t-fast) var(--ease), opacity var(--t-fast);
  }

  .hm-day:hover { transform: scale(1.3); z-index: 5; }

  .hm-day.success { background: var(--green); opacity: 0.75; }
  .hm-day.success:hover { opacity: 1; }
  .hm-day.partial { background: var(--amber); opacity: 0.75; }
  .hm-day.partial:hover { opacity: 1; }
  .hm-day.failed  { background: var(--red); opacity: 0.75; }
  .hm-day.failed:hover  { opacity: 1; }

  /* ─── PROGRESS ─── */
  .prog-track {
    height: 4px; background: var(--bg-overlay);
    border-radius: 99px; overflow: hidden;
  }

  .prog-fill {
    height: 100%; border-radius: 99px;
    background: linear-gradient(90deg, var(--accent), var(--accent-hover));
    transition: width 0.5s var(--ease);
    position: relative;
  }

  .prog-fill.success { background: linear-gradient(90deg, #22c55e, #34d399); }

  /* ─── STATUS PILLS ─── */
  .pill {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 9px; border-radius: 99px;
    font-size: 11px; font-weight: 600;
    letter-spacing: 0.1px;
  }

  .pill-dot { width: 5px; height: 5px; border-radius: 50%; }

  .pill-success { background: var(--green-soft);  color: var(--green); }
  .pill-failed  { background: var(--red-soft);    color: var(--red); }
  .pill-partial { background: var(--amber-soft);  color: var(--amber); }
  .pill-running { background: var(--accent-soft); color: var(--accent-hover); }
  .pill-idle    { background: var(--bg-overlay);  color: var(--text-tertiary); }

  /* ─── TABLE ─── */
  .table { width: 100%; border-collapse: collapse; font-size: 13px; }

  .table th {
    font-size: 11px; font-weight: 600;
    color: var(--text-tertiary);
    text-align: left; padding: 8px 12px;
    border-bottom: 1px solid var(--border-subtle);
    letter-spacing: 0.3px;
  }

  .table td {
    padding: 11px 12px;
    border-bottom: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    transition: background var(--t-fast);
  }

  .table tr:last-child td { border-bottom: none; }

  .table tr:hover td { background: var(--bg-hover); color: var(--text-primary); }

  /* ─── BUTTONS ─── */
  .btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    padding: 8px 16px; border-radius: var(--r-md);
    font-family: var(--font-sans); font-size: 13px; font-weight: 600;
    cursor: pointer; border: none;
    transition: all var(--t-fast) var(--ease);
    letter-spacing: -0.1px;
    white-space: nowrap;
  }

  .btn:active { transform: scale(0.98); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }

  .btn-primary {
    background: var(--accent);
    color: #fff;
    box-shadow: 0 1px 3px rgba(124,111,247,0.4), 0 4px 12px rgba(124,111,247,0.2);
  }
  .btn-primary:hover:not(:disabled) {
    background: var(--accent-hover);
    box-shadow: 0 2px 6px rgba(124,111,247,0.5), 0 8px 20px rgba(124,111,247,0.25);
  }

  .btn-secondary {
    background: var(--bg-raised);
    color: var(--text-primary);
    border: 1px solid var(--border-default);
  }
  .btn-secondary:hover:not(:disabled) { background: var(--bg-overlay); border-color: var(--border-strong); }

  .btn-ghost {
    background: transparent;
    color: var(--text-secondary);
    border: 1px solid transparent;
  }
  .btn-ghost:hover:not(:disabled) { background: var(--bg-hover); color: var(--text-primary); border-color: var(--border-subtle); }

  .btn-danger {
    background: var(--red-soft);
    color: var(--red);
    border: 1px solid rgba(248,113,113,0.2);
  }
  .btn-danger:hover:not(:disabled) { background: rgba(248,113,113,0.18); }

  .btn-sm { padding: 5px 11px; font-size: 12px; }

  /* ─── INPUTS ─── */
  .input-label {
    font-size: 12px; font-weight: 600;
    color: var(--text-secondary);
    display: block; margin-bottom: 6px;
  }

  .fg { margin-bottom: 16px; }

  .fi {
    width: 100%;
    background: var(--bg-raised);
    border: 1px solid var(--border-default);
    border-radius: var(--r-md);
    padding: 8px 12px;
    font-family: var(--font-sans); font-size: 13px;
    color: var(--text-primary);
    outline: none;
    transition: border-color var(--t-fast) var(--ease), box-shadow var(--t-fast) var(--ease);
  }

  .fi:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .fi::placeholder { color: var(--text-disabled); }

  .fi[type=range] {
    padding: 6px 0; cursor: pointer;
    background: transparent; border: none;
    box-shadow: none;
    accent-color: var(--accent);
  }

  select.fi { cursor: pointer; }

  /* ─── TOGGLE ─── */
  .toggle { position: relative; width: 36px; height: 20px; display: inline-block; cursor: pointer; flex-shrink: 0; }
  .toggle input { opacity: 0; width: 0; height: 0; }

  .toggle-track {
    position: absolute; inset: 0;
    background: var(--bg-overlay);
    border: 1px solid var(--border-default);
    border-radius: 99px;
    transition: all var(--t-mid) var(--ease);
  }

  .toggle-thumb {
    position: absolute;
    width: 14px; height: 14px;
    top: 2px; left: 2px;
    background: var(--text-tertiary);
    border-radius: 50%;
    transition: all var(--t-mid) var(--ease);
    box-shadow: 0 1px 3px rgba(0,0,0,0.4);
  }

  .toggle input:checked ~ .toggle-track {
    background: var(--accent);
    border-color: var(--accent);
  }

  .toggle input:checked ~ .toggle-thumb {
    left: 20px; background: #fff;
    box-shadow: 0 1px 4px rgba(0,0,0,0.4);
  }

  /* ─── TAGS ─── */
  .tag-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }

  .tag {
    display: inline-flex; align-items: center; gap: 6px;
    background: var(--bg-overlay);
    border: 1px solid var(--border-default);
    border-radius: var(--r-sm);
    padding: 3px 9px;
    font-size: 12px; color: var(--text-secondary);
    font-family: var(--font-mono);
    transition: border-color var(--t-fast);
  }

  .tag:hover { border-color: var(--border-strong); }

  .tag-x {
    cursor: pointer; color: var(--text-tertiary);
    width: 14px; height: 14px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 3px; font-size: 12px;
    transition: all var(--t-fast);
  }
  .tag-x:hover { background: var(--red-soft); color: var(--red); }

  /* ─── ALERTS ─── */
  .alert {
    display: flex; gap: 10px; align-items: flex-start;
    padding: 12px 14px; border-radius: var(--r-md);
    font-size: 13px;
    border: 1px solid transparent;
  }

  .alert-icon { font-size: 14px; flex-shrink: 0; margin-top: 1px; }

  .alert-warn  { background: var(--amber-soft); border-color: rgba(251,191,36,0.2); color: var(--amber); }
  .alert-error { background: var(--red-soft);   border-color: rgba(248,113,113,0.2); color: var(--red); }
  .alert-info  { background: var(--blue-soft);  border-color: rgba(96,165,250,0.2);  color: var(--blue); }
  .alert-ok    { background: var(--green-soft); border-color: rgba(52,211,153,0.2);  color: var(--green); }

  /* ─── COUNTDOWN ─── */
  .countdown {
    font-size: 38px; font-weight: 800;
    color: var(--text-primary);
    letter-spacing: -1.5px; line-height: 1;
    font-family: var(--font-mono);
  }

  .countdown-label {
    font-size: 11px; color: var(--text-tertiary);
    font-weight: 500; margin-top: 5px; letter-spacing: 0.2px;
  }

  /* ─── GAUGE ─── */
  .gauge-wrap { position: relative; display: inline-block; }
  .gauge-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
  .gauge-val  { font-size: 22px; font-weight: 700; letter-spacing: -0.5px; line-height: 1; }
  .gauge-unit { font-size: 11px; color: var(--text-tertiary); margin-top: 3px; }

  /* ─── SITE ROW ─── */
  .site-row {
    display: flex; align-items: center; gap: 12px;
    padding: 12px 14px; margin-bottom: 6px;
    background: var(--bg-raised);
    border: 1px solid var(--border-subtle);
    border-radius: var(--r-md);
    transition: all var(--t-fast) var(--ease);
  }

  .site-row:hover { border-color: var(--border-default); background: var(--bg-overlay); }

  /* ─── FEED ─── */
  .feed-item {
    display: flex; gap: 10px; align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid var(--border-subtle);
    font-size: 12px;
    animation: fadeSlide 0.25s var(--ease);
  }

  @keyframes fadeSlide {
    from { opacity: 0; transform: translateY(-4px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .feed-item:last-child { border-bottom: none; }

  /* ─── RUN LIST ITEM ─── */
  .run-item {
    padding: 12px 14px; border-radius: var(--r-md);
    cursor: pointer; margin-bottom: 4px;
    border: 1px solid transparent;
    transition: all var(--t-fast) var(--ease);
  }

  .run-item:hover { background: var(--bg-hover); border-color: var(--border-subtle); }

  .run-item.selected {
    background: var(--accent-soft);
    border-color: rgba(124,111,247,0.25);
  }

  /* ─── TREE / FILE BROWSER ─── */
  .tree-item {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 12px; border-radius: var(--r-md);
    cursor: pointer; font-size: 13px;
    color: var(--text-secondary);
    transition: all var(--t-fast) var(--ease);
    user-select: none;
  }

  .tree-item:hover { background: var(--bg-hover); color: var(--text-primary); }
  .tree-item.selected { background: var(--accent-soft); color: var(--accent-hover); }

  /* ─── DANGER ZONE ─── */
  .danger-zone {
    background: var(--red-soft);
    border: 1px solid rgba(248,113,113,0.2);
    border-radius: var(--r-lg);
    padding: 20px;
  }

  /* ─── MISC UTILS ─── */
  .divider { height: 1px; background: var(--border-subtle); margin: 16px 0; }
  .scroll-panel { overflow-y: auto; max-height: 320px; }
  .empty { text-align: center; padding: 40px 20px; color: var(--text-tertiary); font-size: 13px; }
  .empty-icon { font-size: 28px; margin-bottom: 10px; opacity: 0.5; }
  .loading { text-align: center; padding: 40px; color: var(--text-tertiary); font-size: 13px; }

  .flex { display: flex; } .flex-col { flex-direction: column; }
  .items-center { align-items: center; }
  .justify-between { justify-content: space-between; }
  .gap-6{gap:6px} .gap-8{gap:8px} .gap-10{gap:10px} .gap-12{gap:12px} .gap-16{gap:16px}
  .flex-1{flex:1} .w-full{width:100%}
  .mt-4{margin-top:4px} .mt-8{margin-top:8px} .mt-12{margin-top:12px} .mt-16{margin-top:16px}
  .mb-4{margin-bottom:4px} .mb-8{margin-bottom:8px} .mb-12{margin-bottom:12px} .mb-16{margin-bottom:16px} .mb-20{margin-bottom:20px}
  .text-primary{color:var(--text-primary)} .text-secondary{color:var(--text-secondary)} .text-tertiary{color:var(--text-tertiary)}
  .text-green{color:var(--green)} .text-red{color:var(--red)} .text-amber{color:var(--amber)} .text-accent{color:var(--accent-hover)}
  .mono{font-family:var(--font-mono)}
  .bold{font-weight:700} .semibold{font-weight:600}
  .text-sm{font-size:12px} .text-xs{font-size:11px}
`;

// ─── SHARED COMPONENTS ────────────────────────────────────────────────────────

function StatusPill({ status }) {
  const config = {
    success:   { cls: "pill-success", dot: "var(--green)",         label: "Success"   },
    failed:    { cls: "pill-failed",  dot: "var(--red)",           label: "Failed"    },
    partial:   { cls: "pill-partial", dot: "var(--amber)",         label: "Partial"   },
    running:   { cls: "pill-running", dot: "var(--accent-hover)",  label: "Running"   },
    cancelled: { cls: "pill-partial", dot: "var(--amber)",         label: "Cancelled" },
    idle:      { cls: "pill-idle",    dot: "var(--text-tertiary)", label: "Idle"      },
  };
  const c = config[status] || { cls: "pill-idle", dot: "var(--text-tertiary)", label: status || "Unknown" };
  return (
    <span className={`pill ${c.cls}`}>
      <span className="pill-dot" style={{ background: c.dot }} />
      {c.label}
    </span>
  );
}

function SsdGauge({ used = 0, total = 100 }) {
  const pct  = total > 0 ? Math.min((used / total) * 100, 100) : 0;
  const r    = 46; const circ = 2 * Math.PI * r;
  const fill = circ - (pct / 100) * circ;
  const color = pct > 85 ? "var(--red)" : pct > 65 ? "var(--amber)" : "var(--accent)";
  return (
    <div className="gauge-wrap">
      <svg width="108" height="108" viewBox="0 0 108 108">
        <circle cx="54" cy="54" r={r} fill="none" stroke="var(--bg-overlay)" strokeWidth="7" />
        <circle cx="54" cy="54" r={r} fill="none" stroke={color} strokeWidth="7"
          strokeDasharray={circ} strokeDashoffset={fill} strokeLinecap="round"
          transform="rotate(-90 54 54)"
          style={{ transition: "stroke-dashoffset 0.6s cubic-bezier(0.16,1,0.3,1), stroke 0.4s" }} />
      </svg>
      <div className="gauge-center">
        <div className="gauge-val" style={{ color }}>{pct.toFixed(0)}<span style={{ fontSize: 12, fontWeight: 400 }}>%</span></div>
        <div className="gauge-unit">{used.toFixed(1)} / {total} GB</div>
      </div>
    </div>
  );
}

function Heatmap({ runs }) {
  return (
    <div className="heatmap">
      {runs.map(r => (
        <div key={r.id} className={`hm-day ${r.status || "none"}`}
          title={`${r.started_at?.slice(0, 10)} — ${(r.status || "").toUpperCase()} — ${r.files_transferred || 0} files`} />
      ))}
    </div>
  );
}

function Countdown({ nextRun }) {
  const [time, setTime] = useState("--:--:--");
  useEffect(() => {
    const tick = () => {
      const target = nextRun ? new Date(nextRun) : (() => {
        const d = new Date(); d.setHours(8, 0, 0, 0);
        if (new Date() >= d) d.setDate(d.getDate() + 1);
        return d;
      })();
      const diff = target - new Date();
      if (diff <= 0) { setTime("00:00:00"); return; }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setTime(`${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`);
    };
    tick(); const id = setInterval(tick, 1000); return () => clearInterval(id);
  }, [nextRun]);
  return (
    <div>
      <div className="countdown">{time}</div>
      <div className="countdown-label">Until next backup · Daily at 08:00 NPT</div>
    </div>
  );
}

function ErrBanner({ error, onDismiss }) {
  if (!error) return null;
  return (
    <div className="alert alert-error mb-12 flex justify-between items-center">
      <div className="flex items-center gap-8">
        <span className="alert-icon">⚠</span>
        <span>{error}</span>
      </div>
      {onDismiss && (
        <button onClick={onDismiss} className="btn btn-ghost btn-sm" style={{ padding: "2px 8px" }}>×</button>
      )}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="loading">
      <div style={{ fontSize: 20, marginBottom: 10, animation: "pulse-dot 1.2s ease-in-out infinite" }}>⟳</div>
      Loading…
    </div>
  );
}

// ─── DASHBOARD ────────────────────────────────────────────────────────────────
function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try { const d = await api.dashboard(); setData(d); setError(null); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id); }, [load]);

  if (loading) return <LoadingState />;

  const runs    = data?.runs || [];
  const last    = data?.last_run;
  const storage = data?.ssd_storage || {};
  const active  = data?.active_run;
  const libs    = last?.folder_summary || {};

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

      {/* Stats */}
      <div className="stat-strip">
        {[
          { label: "Files Last Run", value: last?.files_transferred ?? "—", sub: last?.started_at?.slice(0, 10) || "No runs yet", icon: "📁" },
          { label: "Data Transferred", value: last?.bytes_human ?? "—", sub: "Last backup", icon: "📦" },
          { label: "30-Day Success Rate", value: runs.length ? `${Math.round(runs.filter(r => r.status === "success").length / runs.length * 100)}%` : "—", sub: `${runs.filter(r => r.status === "success").length} / ${runs.length} runs`, icon: "✅" },
          { label: "Last Run Duration", value: last?.duration_human ?? "—", sub: last ? <StatusPill status={last.status} /> : "No data", icon: "⏱" },
        ].map((s, i) => (
          <div className="stat-card" key={i}>
            <div className="stat-label">
              <span>{s.icon}</span> {s.label}
            </div>
            <div className="stat-value">{s.value}</div>
            <div className="stat-sub">{s.sub}</div>
          </div>
        ))}
      </div>

      <div className="grid-2-1 mb-20">
        {/* Heatmap */}
        <div className="card">
          <div className="flex justify-between items-center mb-16">
            <div className="card-title" style={{ marginBottom: 0 }}>Run History · Last 30 Days</div>
            <div className="flex gap-12 text-xs text-tertiary">
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--green)", display: "inline-block" }} /> Success</span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--amber)", display: "inline-block" }} /> Partial</span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--red)", display: "inline-block" }} /> Failed</span>
            </div>
          </div>
          {runs.length > 0 ? <Heatmap runs={runs} /> : <div className="empty"><div className="empty-icon">📅</div>No backup runs yet</div>}
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

        {/* Right column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card">
            <div className="card-title">Next Scheduled Run</div>
            <Countdown nextRun={data?.next_run} />
          </div>
          <div className="card" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
            <div className="card-title w-full" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span>💾</span> SSD Storage
              {storage.status === "disconnected" && (
                <span className="pill pill-failed" style={{ marginLeft: "auto", fontSize: 10 }}>Disconnected</span>
              )}
              {storage.status === "ok" && (
                <span className="pill pill-success" style={{ marginLeft: "auto", fontSize: 10 }}>Mounted</span>
              )}
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

      {/* Library table */}
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

// ─── BACKUP CONFIG (Local SSD) ──────────────────────────────────────────────
function BackupConfig() {
  const [cfg, setCfg]         = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [saved, setSaved]     = useState(false);
  const [error, setError]     = useState(null);
  const [newEx, setNewEx]     = useState("");
  const [addingFolder, setAddingFolder] = useState(false);
  const [newFolder, setNewFolder]       = useState({ label: "", path: "", enabled: true });

  useEffect(() => {
    api.getConfig()
      .then(d => { setCfg(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  if (loading) return <LoadingState />;
  if (!cfg) return <ErrBanner error={error} />;

  // ── Save ──────────────────────────────────────────────────────────────────
  const save = async () => {
    setSaving(true); setError(null);
    try {
      await api.updateConfig({
        ssd_path:          cfg.ssd_path,
        schedule_time:     cfg.schedule?.time,
        timezone:          cfg.schedule?.timezone,
        concurrency:       cfg.performance?.concurrency,
        max_file_size_gb:  cfg.performance?.max_file_size_gb,
        verify_checksums:  cfg.backup?.verify_checksums,
        version_count:     cfg.backup?.version_count,
        exclude_patterns:  cfg.backup?.exclude_patterns,
      });
      setSaved(true); setTimeout(() => setSaved(false), 2500);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  // ── SSD path picker ────────────────────────────────────────────────────────
  const pickSsd = async () => {
    if (window.ghostbackup?.openDirectory) {
      const p = await window.ghostbackup.openDirectory();
      if (p) {
        // Update local state then immediately persist to backend
        const updated = { ...cfg, ssd_path: p };
        setCfg(updated);
        setSaving(true); setError(null);
        try {
          await api.updateConfig({
            ssd_path:         p,
            schedule_time:    updated.schedule?.time,
            timezone:         updated.schedule?.timezone,
            concurrency:      updated.performance?.concurrency,
            max_file_size_gb: updated.performance?.max_file_size_gb,
            verify_checksums: updated.backup?.verify_checksums,
            version_count:    updated.backup?.version_count,
            exclude_patterns: updated.backup?.exclude_patterns,
          });
          setSaved(true); setTimeout(() => setSaved(false), 2500);
        } catch (e) { setError(e.message); }
        finally { setSaving(false); }
      }
    }
  };

  // ── Source folders ─────────────────────────────────────────────────────────
  const pickFolderPath = async () => {
    if (window.ghostbackup?.openDirectory) {
      const p = await window.ghostbackup.openDirectory();
      if (p) setNewFolder(f => ({ ...f, path: p, label: f.label || p.split(/[\\/]/).pop() || p }));
    }
  };

  const addFolder = async () => {
    if (!newFolder.label || !newFolder.path) return;
    try {
      await api.addSite(newFolder);
      setCfg(c => ({ ...c, sources: [...(c.sources || []), newFolder] }));
      setNewFolder({ label: "", path: "", enabled: true });
      setAddingFolder(false);
    } catch (e) { setError(e.message); }
  };

  const removeFolder = async (label) => {
    try {
      await api.removeSite(label);
      setCfg(c => ({ ...c, sources: (c.sources || []).filter(s => s.label !== label) }));
    } catch (e) { setError(e.message); }
  };

  const toggleFolder = (label, enabled) => {
    setCfg(c => ({ ...c, sources: (c.sources || []).map(s => s.label === label ? { ...s, enabled } : s) }));
  };

  // ── Exclusions ─────────────────────────────────────────────────────────────
  const addEx = () => {
    if (!newEx.trim()) return;
    setCfg(c => ({ ...c, backup: { ...c.backup, exclude_patterns: [...(c.backup?.exclude_patterns || []), newEx.trim()] } }));
    setNewEx("");
  };
  const remEx = (p) => setCfg(c => ({ ...c, backup: { ...c.backup, exclude_patterns: c.backup.exclude_patterns.filter(e => e !== p) } }));

  const sources = cfg.sources || cfg.sites || [];

  return (
    <div>
      <ErrBanner error={error} onDismiss={() => setError(null)} />

      {/* SSD Target */}
      <div className="card mb-16">
        <div className="card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span>💾</span> Backup Destination — Local SSD
        </div>
        <div className="flex gap-10 items-center mb-12">
          <input
            className="fi flex-1"
            value={cfg.ssd_path || ""}
            onChange={e => setCfg(c => ({ ...c, ssd_path: e.target.value }))}
            placeholder="e.g. D:\GhostBackup  or  E:\Backups\RedParrot"
          />
          <button className="btn btn-secondary btn-sm" onClick={pickSsd}>Browse…</button>
          <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
        <SsdDriveStatus path={cfg.ssd_path} />
      </div>

      {/* Schedule + Performance */}
      <div className="grid-2 mb-16">
        <div className="card">
          <div className="card-title">Schedule</div>
          <div className="fg">
            <label className="input-label">Daily backup time</label>
            <input className="fi" type="time"
              value={cfg.schedule?.time || "08:00"}
              onChange={e => setCfg(c => ({ ...c, schedule: { ...c.schedule, time: e.target.value } }))} />
          </div>
          <div className="fg">
            <label className="input-label">Timezone</label>
            <select className="fi"
              value={cfg.schedule?.timezone || "Asia/Kathmandu"}
              onChange={e => setCfg(c => ({ ...c, schedule: { ...c.schedule, timezone: e.target.value } }))}>
              <option value="Asia/Kathmandu">Asia/Kathmandu (UTC+5:45)</option>
              <option value="Europe/London">Europe/London</option>
              <option value="UTC">UTC</option>
            </select>
          </div>
        </div>

        <div className="card">
          <div className="card-title">Performance</div>
          <div className="fg">
            <label className="input-label">Copy threads — <span className="text-accent">{cfg.performance?.concurrency || 4}</span></label>
            <input className="fi" type="range" min="1" max="16"
              value={cfg.performance?.concurrency || 4}
              onChange={e => setCfg(c => ({ ...c, performance: { ...c.performance, concurrency: +e.target.value } }))} />
          </div>
          <div className="fg">
            <label className="input-label">Max file size (GB)</label>
            <input className="fi" type="number" min="1" max="100"
              value={cfg.performance?.max_file_size_gb || 5}
              onChange={e => setCfg(c => ({ ...c, performance: { ...c.performance, max_file_size_gb: +e.target.value } }))} />
          </div>
          <div className="flex items-center gap-12">
            <label className="toggle">
              <input type="checkbox"
                checked={cfg.backup?.verify_checksums ?? true}
                onChange={e => setCfg(c => ({ ...c, backup: { ...c.backup, verify_checksums: e.target.checked } }))} />
              <span className="toggle-track" /><span className="toggle-thumb" />
            </label>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Verify checksums after copy</div>
              <div className="text-xs text-tertiary">Slower but detects corruption. Recommended.</div>
            </div>
          </div>
        </div>
      </div>

      {/* Source Folders */}
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
              <input className="fi" placeholder="e.g. Client Documents"
                value={newFolder.label}
                onChange={e => setNewFolder(f => ({ ...f, label: e.target.value }))} />
            </div>
            <div className="fg" style={{ marginBottom: 12 }}>
              <label className="input-label">Folder path</label>
              <div className="flex gap-8">
                <input className="fi flex-1 mono" placeholder="C:\Users\Shared\Documents"
                  value={newFolder.path}
                  onChange={e => setNewFolder(f => ({ ...f, path: e.target.value }))} />
                <button className="btn btn-secondary btn-sm" onClick={pickFolderPath}>Browse…</button>
              </div>
            </div>
            <div className="flex gap-8">
              <button className="btn btn-primary btn-sm" onClick={addFolder}
                disabled={!newFolder.label || !newFolder.path}>
                Add Folder
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => { setAddingFolder(false); setNewFolder({ label: "", path: "", enabled: true }); }}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {sources.length === 0 ? (
          <div className="empty" style={{ padding: "24px 0" }}>
            <div className="empty-icon">📁</div>
            No source folders added yet. Add a folder to start backing up.
          </div>
        ) : sources.map(s => (
          <div className="site-row" key={s.label || s.name} style={{ opacity: s.enabled !== false ? 1 : 0.5 }}>
            <label className="toggle">
              <input type="checkbox" checked={s.enabled !== false}
                onChange={e => toggleFolder(s.label || s.name, e.target.checked)} />
              <span className="toggle-track" /><span className="toggle-thumb" />
            </label>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{s.label || s.name}</div>
              <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 2, fontFamily: "var(--font-mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {s.path}
              </div>
            </div>
            {s.size_human && (
              <div style={{ fontSize: 11, color: "var(--text-tertiary)", fontFamily: "var(--font-mono)", flexShrink: 0 }}>
                {s.size_human}
              </div>
            )}
            <button className="btn btn-ghost btn-sm" onClick={() => removeFolder(s.label || s.name)}
              style={{ color: "var(--red)", flexShrink: 0 }}>
              Remove
            </button>
          </div>
        ))}
      </div>

      {/* Exclusion Patterns */}
      <div className="card mb-16">
        <div className="card-title">Exclusion Patterns</div>
        <div className="text-sm text-secondary mb-12">
          Files or folders matching these patterns will be skipped. Supports wildcards.
        </div>
        <div className="flex gap-8">
          <input className="fi flex-1 mono" placeholder="e.g.  ~$*  or  *.tmp  or  Thumbs.db"
            value={newEx}
            onChange={e => setNewEx(e.target.value)}
            onKeyDown={e => e.key === "Enter" && addEx()} />
          <button className="btn btn-secondary btn-sm" onClick={addEx}>Add</button>
        </div>
        <div className="tag-list">
          {(cfg.backup?.exclude_patterns || []).map(p => (
            <span className="tag" key={p}>
              {p}<span className="tag-x" onClick={() => remEx(p)}>×</span>
            </span>
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

// ─── SSD DRIVE STATUS (inline helper for BackupConfig) ───────────────────────
function SsdDriveStatus({ path }) {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    if (!path) { setStatus(null); return; }
    fetch("http://127.0.0.1:8765/ssd/status")
      .then(r => r.json()).then(setStatus).catch(() => setStatus(null));
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

// ─── LIVE RUN ─────────────────────────────────────────────────────────────────
function LiveRun() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);

  const poll = useCallback(async () => {
    try { const s = await api.runStatus(); setStatus(s); setError(null); } catch (e) { setError(e.message); }
  }, []);

  useEffect(() => { poll(); const id = setInterval(poll, 1000); return () => clearInterval(id); }, [poll]);

  const startRun = async (full = false) => {
    setStarting(true); setError(null);
    try { await api.startRun({ full }); await poll(); } catch (e) { setError(e.message); } finally { setStarting(false); }
  };

  const stopRun = async () => {
    setStopping(true);
    try { await api.stopRun(); await poll(); } catch (e) { setError(e.message); } finally { setStopping(false); }
  };

  const isRunning = status?.status === "running";
  const pct  = status?.overall_pct || 0;
  const feed = status?.feed || [];
  const libs = status?.libraries || {};

  const elapsed = (() => {
    if (!status?.started_at || !isRunning) return null;
    // Backend sends naive UTC strings without 'Z' — append it so JS parses correctly
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

// ─── LOGS ─────────────────────────────────────────────────────────────────────
function LogsViewer() {
  const [runs, setRuns]     = useState([]);
  const [sel, setSel]       = useState(null);
  const [logs, setLogs]     = useState([]);
  const [rd, setRd]         = useState(null);
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);

  useEffect(() => {
    api.getRuns(30).then(d => { setRuns(d); if (d[0]) setSel(d[0]); }).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!sel) return;
    Promise.all([api.getRunLogs(sel.id, filter === "ALL" ? undefined : filter), api.getRun(sel.id)])
      .then(([l, r]) => { setLogs(l); setRd(r); }).catch(e => setError(e.message));
  }, [sel, filter]);

  const filtered = search ? logs.filter(l => l.message?.toLowerCase().includes(search.toLowerCase())) : logs;

  const lvlColor = { INFO: "var(--text-secondary)", WARN: "var(--amber)", ERROR: "var(--red)" };

  const exportCsv = () => {
    const rows = [["Time", "Level", "Message"], ...filtered.map(l => [l.logged_at, l.level, l.message])];
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([rows.map(r => r.map(c => `"${c}"`).join(",")).join("\n")], { type: "text/csv" }));
    a.download = `run_${sel?.id}_logs.csv`; a.click();
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
            {!sel ? <div className="empty" style={{ padding: "24px 0" }}><div className="empty-icon">📋</div>Select a run from the right panel</div>
              : filtered.length === 0 ? <div className="empty" style={{ padding: "24px 0" }}><div className="empty-icon">🔍</div>No logs found</div>
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
                { k: "Transferred", v: rd.files_transferred }, { k: "Failed", v: rd.files_failed },
                { k: "Duration", v: rd.duration_human }, { k: "Data", v: rd.bytes_human },
                { k: "Status", v: <StatusPill status={rd.status} /> }, { k: "Run ID", v: `#${rd.id}` },
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

// ─── RESTORE ─────────────────────────────────────────────────────────────────
function RestoreUI() {
  const [runs, setRuns] = useState([]);
  const [sel, setSel]   = useState(null);
  const [selLib, setSelLib] = useState(null);
  const [dry, setDry]   = useState(true);
  const [dest, setDest] = useState("C:\\GhostBackup\\Restore");
  const [restoring, setRestoring] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError]   = useState(null);
  const [loading, setLoading] = useState(true);
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
    try {
      const full = await api.getRun(r.id);
      setSel(full);
    } catch {
      setSel(r);
    } finally {
      setLoadingRun(false);
    }
  };

  const pickFolder = async () => { if (window.ghostbackup?.openDirectory) { const p = await window.ghostbackup.openDirectory(); if (p) setDest(p); } };

  const doRestore = async () => {
    if (!sel || !selLib) { setError("Select a backup and library first"); return; }
    setRestoring(true); setResult(null); setError(null);
    try { const r = await api.restore({ run_id: sel.id, library: selLib, destination: dest, dry_run: dry }); setResult(r); }
    catch (e) { setError(e.message); } finally { setRestoring(false); }
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
          {loading ? <LoadingState /> : runs.length === 0 ? <div className="empty"><div className="empty-icon">📅</div>No successful backups yet</div> : (
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
          {!sel ? <div className="empty" style={{ padding: "24px 0" }}><div className="empty-icon">←</div>Choose a backup date first</div>
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

        {!dry && <div className="alert alert-warn mb-12"><span className="alert-icon">⚠</span><span>Dry-run is off. Files will be written to <strong>{dest}</strong>.</span></div>}

        {result && (
          <div style={{ marginBottom: 12 }}>
            <div className={`alert ${result.dry_run ? "alert-ok" : "alert-ok"} mb-8`}>
              <span className="alert-icon">✓</span>
              <span>
                {result.dry_run
                  ? `Dry-run complete — ${result.files_to_restore} files would be restored to ${result.destination}`
                  : `✓ Restore complete — ${result.files_count} files written to ${result.destination}`}
              </span>
            </div>
            {/* File list for dry-run preview */}
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

// ─── SETTINGS ────────────────────────────────────────────────────────────────
function Settings() {
  const [cfg, setCfg]         = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [testMsg, setTestMsg] = useState(null);
  const [pruneMsg, setPruneMsg] = useState(null);
  const [saving, setSaving]   = useState({});
  const [ssdStatus, setSsdStatus] = useState(null);
  const [watcherStatus, setWatcherStatus] = useState(null);
  const [watcherMsg, setWatcherMsg] = useState(null);

  useEffect(() => {
    Promise.all([
      api.getConfig(),
      fetch("http://127.0.0.1:8765/ssd/status").then(r => r.json()).catch(() => null),
      api.watcherStatus().catch(() => null),
    ]).then(([c, s, w]) => { setCfg(c); setSsdStatus(s); setWatcherStatus(w); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const refreshSsd = () => {
    fetch("http://127.0.0.1:8765/ssd/status").then(r => r.json()).then(setSsdStatus).catch(() => {});
  };

  const refreshWatcher = () => {
    api.watcherStatus().then(setWatcherStatus).catch(() => {});
  };

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
                { label: "Drive",      value: ssdStatus.path || "—",              mono: true  },
                { label: "Status",     value: <span className="pill pill-success">Mounted</span> },
                { label: "File System",value: ssdStatus.fs_type || "—",           mono: true  },
                { label: "Total",      value: `${ssdStatus.total_gb?.toFixed(1)} GB`           },
                { label: "Used",       value: `${ssdStatus.used_gb?.toFixed(1)} GB`            },
                { label: "Free",       value: `${ssdStatus.available_gb?.toFixed(1)} GB`,
                  color: ssdStatus.available_gb < 10 ? "var(--red)" : "var(--green)"           },
              ].map(s => (
                <div key={s.label} style={{ padding: "10px 12px", background: "var(--bg-raised)", borderRadius: "var(--r-md)", border: "1px solid var(--border-subtle)" }}>
                  <div className="text-xs text-tertiary mb-4">{s.label}</div>
                  <div style={{ fontWeight: 700, fontSize: 14, color: s.color || "var(--text-primary)", fontFamily: s.mono ? "var(--font-mono)" : undefined, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.value}</div>
                </div>
              ))}
            </div>

            {/* Space bar */}
            <div className="mb-8">
              <div className="flex justify-between text-xs text-tertiary mb-4">
                <span>Disk usage</span>
                <span>{((ssdStatus.used_gb / ssdStatus.total_gb) * 100).toFixed(1)}% used</span>
              </div>
              <div className="prog-track" style={{ height: 6 }}>
                <div className="prog-fill"
                  style={{
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
          When enabled, GhostBackup watches your source folders for changes and triggers an incremental backup automatically — no need to wait for the scheduled run.
          Changes are debounced for <strong>{watcherStatus?.debounce_seconds ?? 15}s</strong> of silence before a backup fires, with a <strong>{watcherStatus?.cooldown_seconds ?? 120}s</strong> cooldown between runs per folder.
        </div>

        {/* Running status pill + toggle */}
        <div className="flex items-center gap-12 mb-16">
          <span className={`pill ${watcherStatus?.running ? "pill-success" : "pill-neutral"}`}>
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

        {/* Per-source status table */}
        {watcherStatus?.sources?.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {watcherStatus.sources.map(s => (
              <div key={s.label} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "var(--bg-raised)", borderRadius: "var(--r-md)", border: "1px solid var(--border-subtle)", fontSize: 12 }}>
                <span style={{ fontWeight: 600, minWidth: 120, color: "var(--text-primary)" }}>{s.label}</span>
                <span className="text-tertiary" style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "var(--font-mono)", fontSize: 11 }}>{s.path}</span>
                {s.pending_changes > 0 && (
                  <span style={{ color: "var(--amber)", fontWeight: 600 }}>⏳ {s.pending_changes} pending</span>
                )}
                {s.last_triggered && (
                  <span className="text-tertiary">Last triggered: {s.last_triggered}</span>
                )}
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
              <input className="fi" type={f.type || "text"}
                value={cfg?.smtp?.[f.key] || ""}
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
            onClick={async () => { setSaving(s => ({ ...s, smtp: true })); try { await api.updateSmtp({ host: cfg.smtp?.host, port: cfg.smtp?.port, user: cfg.smtp?.user, recipients: cfg.smtp?.recipients }); } catch (e) { setError(e.message); } finally { setSaving(s => ({ ...s, smtp: false })); } }}
            disabled={saving.smtp}>{saving.smtp ? "Saving…" : "Save SMTP"}</button>
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
            { k: "daily_days",  label: "Keep daily backups",     min: 7,  max: 365  },
            { k: "weekly_days", label: "Keep weekly snapshots",  min: 30, max: 1825 },
            { k: "guard_days",  label: "Safety guard window",    min: 7,  max: 30   },
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
            onClick={async () => { setSaving(s => ({ ...s, ret: true })); try { await api.updateRetention({ daily_days: cfg.retention?.daily_days, weekly_days: cfg.retention?.weekly_days, guard_days: cfg.retention?.guard_days }); } catch (e) { setError(e.message); } finally { setSaving(s => ({ ...s, ret: false })); } }}
            disabled={saving.ret}>{saving.ret ? "Saving…" : "Save Retention"}</button>
          <button className="btn btn-danger btn-sm"
            onClick={async () => { setPruneMsg(null); try { await api.runPrune(); setPruneMsg("✓ Prune job started"); } catch (e) { setPruneMsg(`✕ ${e.message}`); } }}>
            Run Prune Now
          </button>
          {pruneMsg && <span style={{ fontSize: 12, color: pruneMsg.startsWith("✓") ? "var(--amber)" : "var(--red)" }}>{pruneMsg}</span>}
        </div>
      </div>

      {/* Danger Zone */}
      <div className="danger-zone">
        <div style={{ fontWeight: 700, color: "var(--red)", marginBottom: 6 }}>Danger Zone</div>
        <div className="text-sm text-secondary mb-12">These actions are irreversible. Proceed with caution.</div>
        <button className="btn btn-danger btn-sm"
          onClick={() => { if (confirm("Reset all config to defaults? This cannot be undone.")) api.updateConfig({}); }}>
          Reset All Configuration
        </button>
        <div className="text-xs text-tertiary mt-8">Note: Backup files on the SSD will not be deleted — only app configuration is reset.</div>
      </div>
    </div>
  );
}

// ─── APP SHELL ────────────────────────────────────────────────────────────────
const NAV = [
  { id: "dashboard", label: "Dashboard",    icon: "⊞", sec: "Monitor"   },
  { id: "liverun",   label: "Live Run",     icon: "▶", sec: "Monitor"   },
  { id: "logs",      label: "Logs",         icon: "≡", sec: "Monitor"   },
  { id: "config",    label: "Backup Config",icon: "⚙", sec: "Configure" },
  { id: "restore",   label: "Restore",      icon: "↩", sec: "Configure" },
  { id: "settings",  label: "Settings",     icon: "◈", sec: "Configure" },
];

const PAGE_TITLES = { dashboard: "Dashboard", liverun: "Live Run", logs: "Logs & History", config: "Backup Config", restore: "Restore", settings: "Settings" };

// ─── ALERT BELL ───────────────────────────────────────────────────────────────
const ALERT_LEVEL_CONFIG = {
  info:     { color: "var(--blue)",   bg: "var(--blue-soft)",  icon: "ℹ" },
  warn:     { color: "var(--amber)",  bg: "var(--amber-soft)", icon: "⚠" },
  error:    { color: "var(--red)",    bg: "var(--red-soft)",   icon: "✖" },
  critical: { color: "var(--red)",    bg: "var(--red-soft)",   icon: "🚨" },
};

function AlertBell() {
  const [open,     setOpen]     = useState(false);
  const [alerts,   setAlerts]   = useState([]);
  const [unread,   setUnread]   = useState(0);
  const [loading,  setLoading]  = useState(false);
  const panelRef = useRef(null);

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch("http://127.0.0.1:8765/alerts");
      if (!res.ok) return;
      const data = await res.json();
      setAlerts(data.alerts || []);
      setUnread(data.unread_count || 0);
    } catch {}
  }, []);

  // Poll every 15s
  useEffect(() => {
    fetchAlerts();
    const id = setInterval(fetchAlerts, 15000);
    return () => clearInterval(id);
  }, [fetchAlerts]);

  // Listen for instant push from Electron main (alert:new IPC)
  useEffect(() => {
    const handler = () => fetchAlerts();
    window.addEventListener("ghostbackup-alert", handler);
    return () => window.removeEventListener("ghostbackup-alert", handler);
  }, [fetchAlerts]);

  // Close panel on outside click
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
      await fetch(`http://127.0.0.1:8765/alerts/${id}/dismiss`, { method: "POST" });
      setAlerts(a => a.map(x => x.id === id ? { ...x, dismissed: true } : x));
      setUnread(u => Math.max(0, u - 1));
    } catch {}
  };

  const dismissAll = async () => {
    setLoading(true);
    try {
      await fetch("http://127.0.0.1:8765/alerts/dismiss-all", { method: "POST" });
      setAlerts(a => a.map(x => ({ ...x, dismissed: true })));
      setUnread(0);
    } catch {}
    setLoading(false);
  };

  const topAlert = alerts.find(a => !a.dismissed && (a.level === "critical" || a.level === "error"));

  return (
    <div ref={panelRef} style={{ position: "relative" }}>
      {/* Bell button */}
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

      {/* Panel */}
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 8px)", right: 0,
          width: 360, maxHeight: 480,
          background: "var(--bg-surface)", border: "1px solid var(--border-default)",
          borderRadius: "var(--r-lg)", boxShadow: "var(--shadow-lg)",
          zIndex: 999, display: "flex", flexDirection: "column",
          animation: "fadeSlide 0.15s var(--ease)",
        }}>
          {/* Panel header */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "12px 16px", borderBottom: "1px solid var(--border-subtle)",
          }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: "var(--text-primary)" }}>
              Alerts {unread > 0 && <span style={{ color: "var(--accent-hover)", fontSize: 11 }}>· {unread} unread</span>}
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn btn-ghost btn-sm" onClick={dismissAll} disabled={loading || unread === 0} style={{ fontSize: 11, padding: "3px 8px" }}>
                Clear all
              </button>
              <button className="btn btn-ghost btn-sm" onClick={fetchAlerts} style={{ fontSize: 11, padding: "3px 8px" }}>
                ↺
              </button>
            </div>
          </div>

          {/* Alert list */}
          <div style={{ overflowY: "auto", flex: 1 }}>
            {alerts.filter(a => !a.dismissed).length === 0 ? (
              <div className="empty" style={{ padding: "32px 20px" }}>
                <div className="empty-icon">🔔</div>
                No active alerts
              </div>
            ) : alerts.filter(a => !a.dismissed).map(a => {
              const cfg = ALERT_LEVEL_CONFIG[a.level] || ALERT_LEVEL_CONFIG.info;
              return (
                <div key={a.id} style={{
                  display: "flex", gap: 10, alignItems: "flex-start",
                  padding: "12px 16px", borderBottom: "1px solid var(--border-subtle)",
                  background: "transparent", transition: "background var(--t-fast)",
                  cursor: "default",
                }}
                  onMouseEnter={e => e.currentTarget.style.background = "var(--bg-hover)"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                  {/* Icon */}
                  <div style={{
                    width: 28, height: 28, borderRadius: "var(--r-sm)",
                    background: cfg.bg, display: "flex", alignItems: "center",
                    justifyContent: "center", fontSize: 13, flexShrink: 0, marginTop: 1,
                  }}>
                    {cfg.icon}
                  </div>
                  {/* Content */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 12, color: "var(--text-primary)", marginBottom: 2, lineHeight: 1.3 }}>
                      {a.title}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.4, marginBottom: 4 }}>
                      {a.body}
                    </div>
                    <div style={{ fontSize: 10, color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                      {a.ts ? new Date(a.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
                      {a.run_id && <span style={{ marginLeft: 6 }}>· Run #{a.run_id}</span>}
                    </div>
                  </div>
                  {/* Dismiss */}
                  <button onClick={() => dismiss(a.id)} style={{
                    background: "none", border: "none", cursor: "pointer",
                    color: "var(--text-tertiary)", fontSize: 14, padding: "2px 4px",
                    borderRadius: 4, lineHeight: 1, flexShrink: 0,
                    transition: "color var(--t-fast)",
                  }}
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

// ─── APP SHELL ────────────────────────────────────────────────────────────────
export default function App() {
  const [screen, setScreen] = useState("dashboard");
  const [health, setHealth] = useState(null);
  const [clock,  setClock]  = useState("");

  useEffect(() => {
    const tick = () => { const n = new Date(); setClock(`${String(n.getHours()).padStart(2,"0")}:${String(n.getMinutes()).padStart(2,"0")}:${String(n.getSeconds()).padStart(2,"0")}`); };
    tick(); const id = setInterval(tick, 1000); return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const check = () => api.health().then(setHealth).catch(() => setHealth(null));
    check(); const id = setInterval(check, 10000); return () => clearInterval(id);
  }, []);

  // Forward Electron alert:new IPC to DOM event so AlertBell can hear it
  useEffect(() => {
    if (!window.ghostbackup?.on) return;
    const unsub = window.ghostbackup.on("alert:new", () => {
      window.dispatchEvent(new Event("ghostbackup-alert"));
    });
    return () => unsub?.();
  }, []);

  const sections = [...new Set(NAV.map(n => n.sec))];
  const dotCls = health ? (health.scheduler_running ? "status-dot" : "status-dot idle") : "status-dot err";

  const render = () => {
    switch (screen) {
      case "dashboard": return <Dashboard />;
      case "liverun":   return <LiveRun />;
      case "logs":      return <LogsViewer />;
      case "config":    return <BackupConfig />;
      case "restore":   return <RestoreUI />;
      case "settings":  return <Settings />;
      default:          return <Dashboard />;
    }
  };

  return (
    <>
      <style>{css}</style>
      <div className="app">
        {/* Sidebar */}
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
                  <div key={n.id} className={`nav-item ${screen === n.id ? "active" : ""}`} onClick={() => setScreen(n.id)}>
                    <span className="nav-icon">{n.icon}</span>
                    {n.label}
                  </div>
                ))}
              </div>
            ))}
          </div>

          <div className="sidebar-footer">
            <span className="version-chip">v1.0.0</span>
            <span style={{ flex: 1 }}>Egyan · IT</span>
          </div>
        </div>

        {/* Main */}
        <div className="main">
          <div className="topbar">
            <div className="topbar-title">{PAGE_TITLES[screen]}</div>
            <div className="topbar-meta">
              <div className="meta-badge">
                <span className="dot" />
                {clock}
              </div>
              <div className="meta-badge">
                Next run: {health?.next_run ? new Date(health.next_run).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "08:00"}
              </div>
              <AlertBell />
            </div>
          </div>
          <div className="content">{render()}</div>
        </div>
      </div>
    </>
  );
}
