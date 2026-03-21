export default function StatusPill({ status }) {
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
