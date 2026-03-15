"""
reporter.py — GhostBackup Reporter  (Phase 2)

Phase 2 additions:
  - AlertManager  : in-memory alert store with severity levels,
                    read + dismiss from the /alerts API endpoint
  - Desktop notification hook : fires an HTTP callback so Electron
                    main process can show a Windows toast
  - Richer failure emails : per-library table, error list, retry context
  - Watchdog alert email : stall + kill scenario
  - alert_and_notify()  : one call to log alert + email + toast
"""

import asyncio
import logging
import smtplib
import ssl
from collections import deque
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Literal, Optional

from config import ConfigManager

logger = logging.getLogger("reporter")
REPORT_DIR = Path("reports")
AlertLevel = Literal["info", "warn", "error", "critical"]


class Alert:
    _id_counter = 0

    def __init__(self, level: AlertLevel, title: str, body: str, run_id: Optional[int] = None):
        Alert._id_counter += 1
        self.id        = Alert._id_counter
        self.level     = level
        self.title     = title
        self.body      = body
        self.run_id    = run_id
        self.ts        = datetime.now(timezone.utc).isoformat()
        self.dismissed = False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "level": self.level, "title": self.title,
            "body": self.body, "run_id": self.run_id,
            "ts": self.ts, "dismissed": self.dismissed,
        }


class AlertManager:
    MAX_ALERTS = 200

    def __init__(self):
        self._alerts: deque[Alert] = deque(maxlen=self.MAX_ALERTS)

    def add(self, level: AlertLevel, title: str, body: str,
            run_id: Optional[int] = None) -> Alert:
        alert = Alert(level, title, body, run_id)
        self._alerts.appendleft(alert)
        logger.info(f"[alert:{level}] {title}")
        return alert

    def get_all(self, include_dismissed: bool = False) -> list[dict]:
        alerts = list(self._alerts)
        if not include_dismissed:
            alerts = [a for a in alerts if not a.dismissed]
        return [a.to_dict() for a in alerts]

    def dismiss(self, alert_id: int) -> bool:
        for a in self._alerts:
            if a.id == alert_id:
                a.dismissed = True
                return True
        return False

    def dismiss_all(self) -> int:
        count = sum(1 for a in self._alerts if not a.dismissed)
        for a in self._alerts:
            a.dismissed = True
        return count

    def unread_count(self) -> int:
        return sum(1 for a in self._alerts if not a.dismissed)


class Reporter:
    def __init__(self, config: ConfigManager):
        self._config = config
        self.alerts  = AlertManager()
        self._notify_callback = None  # async (title, body) -> None
        REPORT_DIR.mkdir(parents=True, exist_ok=True)

    def set_notify_callback(self, fn):
        self._notify_callback = fn

    # ── Master alert ──────────────────────────────────────────────────────────

    async def alert_and_notify(self, level: AlertLevel, title: str, body: str,
                                run_id: Optional[int] = None,
                                send_email: bool = True) -> Alert:
        alert = self.alerts.add(level, title, body, run_id=run_id)
        tasks = []
        if send_email and self._config.smtp_recipients:
            tasks.append(self._send_alert_email(title, body, level, run_id))
        if self._notify_callback:
            tasks.append(self._notify_callback(title, body))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"alert_and_notify task failed: {r}")
        return alert

    # ── Run report ────────────────────────────────────────────────────────────

    async def send_run_report(self, run_state: dict) -> None:
        status = run_state.get("status", "unknown")
        run_id = run_state.get("run_id")

        if status == "failed":
            errors = run_state.get("errors", [])
            await self.alert_and_notify(
                level="error",
                title=f"Backup failed \u2014 Run #{run_id}",
                body=f"{len(errors)} error(s). Check Logs for details.",
                run_id=run_id, send_email=False,
            )
        elif status == "partial":
            failed = run_state.get("files_failed", 0)
            await self.alert_and_notify(
                level="warn",
                title=f"Backup partial \u2014 Run #{run_id}",
                body=f"{failed} file(s) failed to transfer.",
                run_id=run_id, send_email=False,
            )
        else:
            self.alerts.add("info", f"Backup complete \u2014 Run #{run_id}",
                            f"{run_state.get('files_transferred', 0)} files transferred.", run_id=run_id)

        if not self._config.smtp_recipients:
            return
        subject    = f"[GhostBackup] Run #{run_id} \u2014 {status.upper()}"
        body_html  = self._build_run_email_html(run_state)
        body_plain = self._build_run_email_plain(run_state)
        try:
            await asyncio.to_thread(self._send_email, subject, body_html, body_plain)
            logger.info(f"Run report email sent for run #{run_id}")
        except Exception as e:
            logger.error(f"Failed to send run report email: {e}")

    # ── Alert email ───────────────────────────────────────────────────────────

    async def send_alert(self, subject: str, message: str) -> None:
        await self.alert_and_notify(level="error", title=subject, body=message, send_email=True)

    async def _send_alert_email(self, title: str, body: str,
                                 level: AlertLevel, run_id: Optional[int]) -> None:
        level_color = {"info": "#60a5fa", "warn": "#fbbf24",
                       "error": "#f87171", "critical": "#ff4757"}.get(level, "#8b8fa8")
        level_icon  = {"info": "\u2139", "warn": "\u26a0", "error": "\u2716",
                       "critical": "\U0001f6a8"}.get(level, "\u2022")
        run_tag  = f" \u00b7 Run #{run_id}" if run_id else ""
        subject  = f"[GhostBackup {level.upper()}] {title}{run_tag}"
        ts       = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        html = f"""<!DOCTYPE html><html><body style="font-family:'Segoe UI',Arial,sans-serif;background:#0e0f11;color:#e8eaf0;padding:0;margin:0">
<div style="max-width:560px;margin:32px auto;background:#13141a;border:1px solid #1e2030;border-radius:12px;overflow:hidden">
  <div style="background:#1a1d26;padding:20px 24px;border-bottom:1px solid #1e2030">
    <div style="font-size:16px;font-weight:700;color:#f0f1f5">GhostBackup</div>
    <div style="font-size:11px;color:#555872;letter-spacing:1px;text-transform:uppercase">Red Parrot Accounting</div>
  </div>
  <div style="padding:20px 24px;border-left:4px solid {level_color}">
    <div style="font-size:11px;font-weight:600;color:{level_color};text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">{level_icon} {level.upper()} ALERT{run_tag}</div>
    <div style="font-size:18px;font-weight:700;color:#f0f1f5;margin-bottom:8px">{title}</div>
    <div style="font-size:14px;color:#8b8fa8;line-height:1.6">{body}</div>
  </div>
  <div style="padding:14px 24px;border-top:1px solid #1e2030;display:flex;justify-content:space-between">
    <div style="font-size:11px;color:#555872;font-family:monospace">{ts}</div>
    <div style="font-size:11px;color:#555872">GhostBackup v1.0</div>
  </div>
</div></body></html>"""
        plain = f"[GhostBackup {level.upper()}] {title}\n{body}\n\nTime: {ts}"
        try:
            await asyncio.to_thread(self._send_email, subject, html, plain)
        except Exception as e:
            logger.error(f"Alert email failed: {e}")

    # ── Specific alert helpers ────────────────────────────────────────────────

    async def send_watchdog_alert(self, elapsed_minutes: int, max_minutes: int,
                                   run_id: Optional[int] = None) -> None:
        await self.alert_and_notify(
            level="critical",
            title=f"Backup stalled \u2014 running {elapsed_minutes}m (limit {max_minutes}m)",
            body=(f"The backup job has been running for {elapsed_minutes} minutes, "
                  f"exceeding the limit of {max_minutes} minutes. Check Logs and restart if needed."),
            run_id=run_id, send_email=True,
        )

    async def send_circuit_breaker_alert(self, library: str, fail_rate_pct: float,
                                          run_id: Optional[int] = None) -> None:
        await self.alert_and_notify(
            level="error",
            title=f"Circuit breaker tripped \u2014 {library}",
            body=(f"Library '{library}' exceeded the failure threshold ({fail_rate_pct:.0f}% failed). "
                  "The library was skipped to protect the backup."),
            run_id=run_id, send_email=True,
        )

    async def send_retry_alert(self, attempt: int, max_attempts: int,
                                error: str, run_id: Optional[int] = None) -> None:
        final = (attempt == max_attempts)
        await self.alert_and_notify(
            level="critical" if final else "warn",
            title=(f"All {max_attempts} backup attempts failed"
                   if final else f"Backup attempt {attempt} failed \u2014 retrying"),
            body=(f"GhostBackup exhausted all retry attempts. Last error: {error}"
                  if final else f"Error: {error}. Attempt {attempt} of {max_attempts}."),
            run_id=run_id, send_email=final,
        )

    # ── Test email ────────────────────────────────────────────────────────────

    async def send_test_email(self) -> None:
        ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        html = f"""<!DOCTYPE html><html><body style="font-family:'Segoe UI',Arial,sans-serif;background:#0e0f11;color:#e8eaf0;padding:0;margin:0">
<div style="max-width:560px;margin:32px auto;background:#13141a;border:1px solid #1e2030;border-radius:12px;overflow:hidden">
  <div style="background:#1a1d26;padding:20px 24px;border-bottom:1px solid #1e2030">
    <div style="font-size:16px;font-weight:700;color:#f0f1f5">GhostBackup</div>
    <div style="font-size:11px;color:#555872;letter-spacing:1px;text-transform:uppercase">Red Parrot Accounting</div>
  </div>
  <div style="padding:24px;border-left:4px solid #34d399">
    <div style="font-size:18px;font-weight:700;color:#34d399;margin-bottom:8px">\u2713 SMTP Verified</div>
    <div style="font-size:14px;color:#8b8fa8;line-height:1.6">Your email configuration is working. GhostBackup will send run summaries and failure alerts to this address.</div>
  </div>
  <div style="padding:14px 24px;border-top:1px solid #1e2030"><div style="font-size:11px;color:#555872;font-family:monospace">{ts}</div></div>
</div></body></html>"""
        await asyncio.to_thread(self._send_email,
            "[GhostBackup] SMTP Test \u2014 Configuration Verified", html,
            "GhostBackup SMTP test successful.")

    # ── Rich run report HTML ──────────────────────────────────────────────────

    def _build_run_email_html(self, run: dict) -> str:
        status     = run.get("status", "unknown")
        run_id     = run.get("run_id", "?")
        started    = run.get("started_at", "")[:19].replace("T", " ")
        finished   = run.get("finished_at", "")[:19].replace("T", " ")
        files_ok   = run.get("files_transferred", 0)
        files_fail = run.get("files_failed", 0)
        bytes_tx   = _fmt_bytes(run.get("bytes_transferred", 0))
        errors     = run.get("errors", [])
        status_color = {"success": "#34d399", "partial": "#fbbf24",
                        "failed":  "#f87171"}.get(status, "#8b8fa8")
        status_icon  = {"success": "\u2713", "partial": "\u26a0",
                        "failed": "\u2716"}.get(status, "\u2022")

        lib_rows = ""
        for lib_name, lib_data in run.get("libraries", {}).items():
            lib_s = lib_data.get("status", "unknown")
            lc = {"success": "#34d399", "partial": "#fbbf24", "failed": "#f87171"}.get(lib_s, "#8b8fa8")
            lib_rows += (f'<tr><td style="padding:10px 14px;border-bottom:1px solid #1e2030;color:#f0f1f5;font-weight:500">{lib_name}</td>'
                         f'<td style="padding:10px 14px;border-bottom:1px solid #1e2030;color:{lc};font-weight:600;font-size:11px;text-transform:uppercase">{lib_s}</td>'
                         f'<td style="padding:10px 14px;border-bottom:1px solid #1e2030;color:#8b8fa8;font-family:monospace">{lib_data.get("files_transferred",0)}</td>'
                         f'<td style="padding:10px 14px;border-bottom:1px solid #1e2030;color:{"#f87171" if lib_data.get("files_failed") else "#555872"};font-family:monospace">{lib_data.get("files_failed",0)}</td></tr>')

        err_html = ""
        if errors:
            items = "".join(
                f'<li style="color:#f87171;margin-bottom:5px;font-size:12px;font-family:monospace"><span style="color:#8b8fa8">{e.get("file","?")}</span> \u2014 {e.get("error","?")}</li>'
                for e in errors[:10]
            )
            more = f'<li style="color:#555872;font-size:11px">\u2026and {len(errors)-10} more</li>' if len(errors) > 10 else ""
            err_html = f'<div style="padding:0 24px"><div style="background:#1a1010;border:1px solid rgba(248,113,113,0.2);border-left:4px solid #f87171;border-radius:8px;padding:16px;margin-top:0"><div style="color:#f87171;font-weight:700;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:10px">\u2716 Errors ({len(errors)})</div><ul style="margin:0;padding-left:16px">{items}{more}</ul></div></div>'

        stats = "".join(
            f'<div style="flex:1;padding:16px 20px;border-right:1px solid #1e2030"><div style="font-size:10px;color:#555872;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:5px">{label}</div><div style="font-size:22px;font-weight:800;color:{color};letter-spacing:-0.5px">{val}</div></div>'
            for label, val, color in [
                ("Files OK", str(files_ok), "#34d399"),
                ("Failed",   str(files_fail), "#f87171" if files_fail else "#555872"),
                ("Data",     bytes_tx, "#8b8fa8"),
            ]
        )

        return f"""<!DOCTYPE html><html><body style="font-family:'Segoe UI',Arial,sans-serif;background:#0e0f11;color:#e8eaf0;padding:0;margin:0">
<div style="max-width:600px;margin:32px auto;background:#13141a;border:1px solid #1e2030;border-radius:12px;overflow:hidden">
  <div style="background:#1a1d26;padding:20px 24px;border-bottom:1px solid #1e2030;display:flex;align-items:center;gap:14px">
    <div style="width:40px;height:40px;background:linear-gradient(135deg,#7c6ff7,#5b52e0);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px">👻</div>
    <div><div style="font-size:17px;font-weight:800;color:#f0f1f5">GhostBackup</div><div style="font-size:11px;color:#555872;letter-spacing:1px;text-transform:uppercase">Red Parrot Accounting \u00b7 IT</div></div>
  </div>
  <div style="padding:24px;border-bottom:1px solid #1e2030;border-left:4px solid {status_color}">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
      <span style="font-size:22px;color:{status_color}">{status_icon}</span>
      <div style="font-size:20px;font-weight:800;color:#f0f1f5">Run #{run_id} \u2014 {status.upper()}</div>
    </div>
    <div style="font-size:12px;color:#555872;font-family:monospace">{started} \u2192 {finished} UTC</div>
  </div>
  <div style="display:flex;background:#1a1d26;border-bottom:1px solid #1e2030">{stats}</div>
  <div style="padding:20px 24px 16px">
    <div style="font-size:11px;font-weight:600;color:#555872;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:12px">Library Breakdown</div>
    <table style="width:100%;border-collapse:collapse;background:#1a1d26;border:1px solid #1e2030;border-radius:8px;overflow:hidden">
      <thead><tr style="background:#21253a">
        <th style="padding:8px 14px;text-align:left;font-size:10px;color:#555872;text-transform:uppercase;letter-spacing:0.5px">Library</th>
        <th style="padding:8px 14px;text-align:left;font-size:10px;color:#555872;text-transform:uppercase;letter-spacing:0.5px">Status</th>
        <th style="padding:8px 14px;text-align:left;font-size:10px;color:#555872;text-transform:uppercase;letter-spacing:0.5px">Transferred</th>
        <th style="padding:8px 14px;text-align:left;font-size:10px;color:#555872;text-transform:uppercase;letter-spacing:0.5px">Failed</th>
      </tr></thead>
      <tbody>{lib_rows if lib_rows else '<tr><td colspan="4" style="padding:12px 14px;color:#555872;text-align:center">No library data</td></tr>'}</tbody>
    </table>
  </div>
  {err_html}
  <div style="padding:16px 24px;border-top:1px solid #1e2030;margin-top:12px;display:flex;justify-content:space-between">
    <div style="font-size:11px;color:#555872;font-family:monospace">{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</div>
    <div style="font-size:11px;color:#555872">GhostBackup v1.0 \u00b7 Red Parrot IT</div>
  </div>
</div></body></html>"""

    def _build_run_email_plain(self, run: dict) -> str:
        status   = run.get("status", "unknown").upper()
        run_id   = run.get("run_id", "?")
        files_ok = run.get("files_transferred", 0)
        bytes_tx = _fmt_bytes(run.get("bytes_transferred", 0))
        errors   = run.get("errors", [])
        lines = [f"GhostBackup Run #{run_id} — {status}", "=" * 40,
                 f"Files transferred : {files_ok}", f"Data transferred  : {bytes_tx}",
                 f"Errors            : {len(errors)}", ""]
        if errors:
            lines.append("Errors:")
            for e in errors[:10]:
                lines.append(f"  - {e.get('file','?')}: {e.get('error','?')}")
        return "\n".join(lines)

    # ── SMTP ──────────────────────────────────────────────────────────────────

    def _send_email(self, subject: str, body_html: str, body_plain: str) -> None:
        host, port     = self._config.smtp_host, self._config.smtp_port
        user, password = self._config.smtp_user, self._config.smtp_password
        recipients     = self._config.smtp_recipients
        if not recipients or not user:
            return
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"GhostBackup <{user}>"
        msg["To"]      = ", ".join(recipients)
        msg.attach(MIMEText(body_plain, "plain"))
        msg.attach(MIMEText(body_html,  "html"))
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=15) as server:
            if self._config.smtp_use_tls:
                server.starttls(context=context)
            if password:
                server.login(user, password)
            server.sendmail(user, recipients, msg.as_string())

    # ── Health report ─────────────────────────────────────────────────────────

    def generate_health_report(self, runs: list[dict]) -> Path:
        rows = ""
        for r in runs:
            s = r.get("status", "unknown")
            c = {"success": "#34d399", "partial": "#fbbf24", "failed": "#f87171"}.get(s, "#8b8fa8")
            rows += (f'<tr><td>{r.get("id")}</td><td>{r.get("started_at","")[:10]}</td>'
                     f'<td style="color:{c}">{s.upper()}</td><td>{r.get("files_transferred",0)}</td>'
                     f'<td>{r.get("bytes_human","—")}</td><td>{r.get("duration_human","—")}</td>'
                     f'<td style="color:#f87171">{r.get("files_failed",0)}</td></tr>')
        html = (f'<!DOCTYPE html><html><head><title>GhostBackup Health</title>'
                f'<style>body{{font-family:monospace;background:#0e0f11;color:#e8eaf0;padding:24px;margin:0}}'
                f'h1{{color:#7c6ff7}}table{{width:100%;border-collapse:collapse;background:#13141a;border:1px solid #1e2030}}'
                f'th{{padding:8px 12px;border-bottom:1px solid #1e2030;text-align:left;color:#555872;font-size:9px;letter-spacing:2px;text-transform:uppercase}}'
                f'td{{padding:10px 12px;border-bottom:1px solid #1e2030;color:#8b8fa8;font-size:12px}}'
                f'tr:hover td{{background:#1a1d26}}</style></head>'
                f'<body><h1>GhostBackup \u2014 Health</h1>'
                f'<p style="color:#555872;font-size:11px">Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</p>'
                f'<table><thead><tr><th>#</th><th>Date</th><th>Status</th><th>Files</th><th>Data</th><th>Duration</th><th>Errors</th></tr></thead>'
                f'<tbody>{rows}</tbody></table></body></html>')
        path = REPORT_DIR / f"health_{datetime.now(timezone.utc).strftime('%Y%m%d')}.html"
        path.write_text(html, encoding="utf-8")
        return path


def _fmt_bytes(b: int) -> str:
    if b >= 1024 ** 3: return f"{b / 1024 ** 3:.1f} GB"
    if b >= 1024 ** 2: return f"{b / 1024 ** 2:.1f} MB"
    if b >= 1024:      return f"{b / 1024:.1f} KB"
    return f"{b} B"
