interface SsdGaugeProps {
  used?: number;
  total?: number;
}

export default function SsdGauge({ used = 0, total = 100 }: SsdGaugeProps) {
  const pct = total > 0 ? Math.min((used / total) * 100, 100) : 0;
  const r = 46;
  const circ = 2 * Math.PI * r;
  const fill = circ - (pct / 100) * circ;
  const color = pct > 85 ? "var(--red)" : pct > 65 ? "var(--amber)" : "var(--accent)";
  return (
    <div className="gauge-wrap">
      <svg width="108" height="108" viewBox="0 0 108 108">
        <circle cx="54" cy="54" r={r} fill="none" stroke="var(--bg-overlay)" strokeWidth="7" />
        <circle
          cx="54"
          cy="54"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="7"
          strokeDasharray={circ}
          strokeDashoffset={fill}
          strokeLinecap="round"
          transform="rotate(-90 54 54)"
          style={{ transition: "stroke-dashoffset 0.6s cubic-bezier(0.16,1,0.3,1), stroke 0.4s" }}
        />
      </svg>
      <div className="gauge-center">
        <div className="gauge-val" style={{ color }}>
          {pct.toFixed(0)}
          <span style={{ fontSize: 12, fontWeight: 400 }}>%</span>
        </div>
        <div className="gauge-unit">
          {used.toFixed(1)} / {total} GB
        </div>
      </div>
    </div>
  );
}
