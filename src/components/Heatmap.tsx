import type { RunSummary } from "../types";

interface HeatmapProps {
  runs: RunSummary[];
}

export default function Heatmap({ runs }: HeatmapProps) {
  return (
    <div className="heatmap">
      {runs.map(r => (
        <div
          key={r.id}
          className={`hm-day ${r.status || "none"}`}
          title={`${r.started_at?.slice(0, 10)} — ${(r.status || "").toUpperCase()} — ${r.files_transferred || 0} files`}
        />
      ))}
    </div>
  );
}
