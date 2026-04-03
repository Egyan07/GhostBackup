import { useState, useEffect } from "react";

interface CountdownProps {
  nextRun?: string | null;
  scheduleLabel?: string;
  scheduleTime?: string;
  timezone?: string;
}

function buildScheduleLabel(scheduleLabel?: string, scheduleTime?: string, timezone?: string): string {
  if (scheduleLabel) return scheduleLabel;
  if (scheduleTime && timezone) return `Daily at ${scheduleTime} ${timezone}`;
  if (scheduleTime) return `Daily at ${scheduleTime}`;
  if (timezone) return `Daily (${timezone})`;
  return "Daily schedule";
}

export default function Countdown({ nextRun, scheduleLabel, scheduleTime, timezone }: CountdownProps) {
  const [time, setTime] = useState("--:--:--");

  useEffect(() => {
    if (!nextRun) {
      setTime("--:--:--");
      return undefined;
    }

    const tick = () => {
      const target = new Date(nextRun);
      const diff = target.getTime() - new Date().getTime();
      if (diff <= 0) { setTime("00:00:00"); return; }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setTime(
        `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [nextRun]);

  return (
    <div>
      <div className="countdown">{time}</div>
      <div className="countdown-label">Until next backup · {buildScheduleLabel(scheduleLabel, scheduleTime, timezone)}</div>
    </div>
  );
}
