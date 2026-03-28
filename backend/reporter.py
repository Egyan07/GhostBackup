"""
reporter.py — GhostBackup Reporter

Manages in-process alerts (AlertManager), desktop notification forwarding
to the Electron main process, and email delivery via SMTP for backup run
summaries and failure notifications.
"""

import asyncio
import logging
import smtplib
import ssl
import threading
from collections import deque
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Callable, Coroutine, Literal, Optional

from config import ConfigManager
from utils import fmt_bytes as _fmt_bytes

logger = logging.getLogger("reporter")

REPORT_DIR = Path(__file__).parent / "reports"

_HEALTH_REPORT_TEMPLATE = (
    '<!DOCTYPE html><html><head><title>GhostBackup Health</title>'
    '<style>'
    'body{font-family:monospace;background:#0e0f11;color:#e8eaf0;padding:24px;margin:0}'
    'h1{color:#7c6ff7}'
    'table{width:100%;border-collapse:collapse;background:#13141a;border:1px solid #1e2030}'
    'th{padding:8px 12px;border-bottom:1px solid #1e2030;text-align:left;'
    'color:#555872;font-size:9px;letter-spacing:2px;text-transform:uppercase}'
    'td{padding:10px 12px;border-bottom:1px solid #1e2030;color:#8b8fa8;font-size:12px}'
    'tr:hover td{background:#1a1d26}'
    '</style></head>'
    '<body><h1>GhostBackup \u2014 Health</h1>'
    '<p style="color:#555872;font-size:11px">Generated: {generated}</p>'
    '<table><thead><tr>'
    '<th>#</th><th>Date</th><th>Status</th><th>Files</th>'
    '<th>Data</th><th>Duration</th><th>Errors</th>'
    '</tr></thead><tbody>{rows}</tbody></table></body></html>'
)

AlertLevel = Literal["info", "warn", "error", "critical"]

_LEVEL_COLOURS = {
    "info":     "#60a5fa",
    "warn":     "#fbbf24",
    "error":    "#f87171",
    "critical": "#ff4757",
}
_LEVEL_ICONS = {
    "info":     "ℹ",
    "warn":     "⚠",
    "error":    "✖",
    "critical": "🚨",
}


# ── Alert ─────────────────────────────────────────────────────────────────────

_alert_id_lock    = threading.Lock()
_alert_id_counter = 0


def _next_alert_id() -> int:
    global _alert_id_counter
    with _alert_id_lock:
        _alert_id_counter += 1
        return _alert_id_counter


class Alert:
    def __init__(
        self,
        level: AlertLevel,
        title: str,
        body: str,
        run_id: Optional[int] = None,
    ):
        self.id        = _next_alert_id()
        self.level     = level
        self.title     = title
        self.body      = body
        self.run_id    = run_id
        self.ts        = datetime.now(timezone.utc).isoformat()
        self.dismissed = False

    def to_dict(self) -> dict:
        return {
            "id":        self.id,
            "level":     self.level,
            "title":     self.title,
            "body":      self.body,
            "run_id":    self.run_id,
            "ts":        self.ts,
            "dismissed": self.dismissed,
        }


# ── AlertManager ──────────────────────────────────────────────────────────────

class AlertManager:
    MAX_ALERTS = 200

    def __init__(self):
        self._alerts: deque[Alert] = deque(maxlen=self.MAX_ALERTS)

    def add(
        self,
        level: AlertLevel,
        title: str,
        body: str,
        run_id: Optional[int] = None,
    ) -> Alert:
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


# ── Reporter ──────────────────────────────────────────────────────────────────

class Reporter:
    def __init__(self, config: ConfigManager):
        self._config = config
        self.alerts  = AlertManager()
        self._notify_cb: Optional[Callable[[str, str], Coroutine]] = None
        REPORT_DIR.mkdir(parents=True, exist_ok=True)

    def set_notify_callback(
        self, fn: Callable[[str, str], Coroutine]
    ) -> None:
        """Register an async callback(title, body) to forward desktop notifications."""
        self._notify_cb = fn

    # ── Master alert ──────────────────────────────────────────────────────────

    async def alert_and_notify(
        self,
        level: AlertLevel,
        title: str,
        body: str,
        run_id: Optional[int] = None,
        send_email: bool = True,
    ) -> Alert:
        """Log alert, optionally send email, and forward a desktop toast."""
        alert = self.alerts.add(level, title, body, run_id=run_id)
        tasks = []
        if send_email and self._config.smtp_recipients:
            tasks.append(self._send_alert_email(title, body, level, run_id))
        if self._notify_cb:
            tasks.append(self._notify_cb(title, body))
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
                title=f"Backup failed — Run #{run_id}",
                body=f"{len(errors)} error(s). Check Logs for details.",
                run_id=run_id, send_email=False,
            )
        elif status == "partial":
            failed = run_state.get("files_failed", 0)
            await self.alert_and_notify(
                level="warn",
                title=f"Backup partial — Run #{run_id}",
                body=f"{failed} file(s) failed to transfer.",
                run_id=run_id, send_email=False,
            )
        else:
            self.alerts.add(
                "info",
                f"Backup complete — Run #{run_id}",
                f"{run_state.get('files_transferred', 0)} files transferred.",
                run_id=run_id,
            )

        if not self._config.smtp_recipients:
            return

        subject    = f"[GhostBackup] Run #{run_id} — {status.upper()}"
        body_html  = self._build_run_email_html(run_state)
        body_plain = self._build_run_email_plain(run_state)
        try:
            await asyncio.to_thread(self._send_email, subject, body_html, body_plain)
            logger.info(f"Run report email sent for run #{run_id}")
        except Exception as e:
            logger.error(f"Failed to send run report email: {e}")

    # ── Alert email ───────────────────────────────────────────────────────────

    async def _send_alert_email(
        self,
        title: str,
        body: str,
        level: AlertLevel,
        run_id: Optional[int],
    ) -> None:
        colour = _LEVEL_COLOURS.get(level, "#8b8fa8")
        icon   = _LEVEL_ICONS.get(level, "•")
        tag    = f" · Run #{run_id}" if run_id else ""
        subject = f"[GhostBackup {level.upper()}] {title}{tag}"
        ts      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        html = f"""<!DOCTYPE html><html><body style="font-family:'Segoe UI',Arial,sans-serif;background:#0e0f11;color:#e8eaf0;padding:0;margin:0">
<div style="max-width:560px;margin:32px auto;background:#13141a;border:1px solid #1e2030;border-radius:12px;overflow:hidden">
  <div style="background:#1a1d26;padding:20px 24px;border-bottom:1px solid #1e2030">
    <div style="font-size:16px;font-weight:700;color:#f0f1f5">GhostBackup</div>
    <div style="font-size:11px;color:#555872;letter-spacing:1px;text-transform:uppercase">Red Parrot Accounting</div>
  </div>
  <div style="padding:20px 24px;border-left:4px solid {colour}">
    <div style="font-size:11px;font-weight:600;color:{colour};text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">{icon} {level.upper()} ALERT{tag}</div>
    <div style="font-size:18px;font-weight:700;color:#f0f1f5;margin-bottom:8px">{title}</div>
    <div style="font-size:14px;color:#8b8fa8;line-height:1.6">{body}</div>
  </div>
  <div style="padding:14px 24px;border-top:1px solid #1e2030">
    <div style="font-size:11px;color:#555872;font-family:monospace">{ts}</div>
  </div>
</div></body></html>"""
        plain = f"[GhostBackup {level.upper()}] {title}\n{body}\n\nTime: {ts}"
        try:
            await asyncio.to_thread(self._send_email, subject, html, plain)
        except Exception as e:
            logger.error(f"Alert email failed: {e}")

    # ── Specific alert helpers ────────────────────────────────────────────────

    async def send_watchdog_alert(
        self,
        elapsed_minutes: int,
        max_minutes: int,
        run_id: Optional[int] = None,
    ) -> None:
        await self.alert_and_notify(
            level="critical",
            title=f"Backup stalled — running {elapsed_minutes}m (limit {max_minutes}m)",
            body=(
                f"The backup job has been running for {elapsed_minutes} minutes, "
                f"exceeding the {max_minutes}-minute limit. "
                "Check the Logs tab and restart if the job is frozen."
            ),
            run_id=run_id, send_email=True,
        )

    async def send_circuit_breaker_alert(
        self,
        library: str,
        fail_rate_pct: float,
        run_id: Optional[int] = None,
    ) -> None:
        await self.alert_and_notify(
            level="error",
            title=f"Circuit breaker tripped — {library}",
            body=(
                f"Library '{library}' exceeded the failure threshold "
                f"({fail_rate_pct:.0f}% of files failed). "
                "The library was skipped to protect the rest of the backup."
            ),
            run_id=run_id, send_email=True,
        )

    async def send_retry_alert(
        self,
        attempt: int,
        max_attempts: int,
        error: str,
        run_id: Optional[int] = None,
    ) -> None:
        final = attempt == max_attempts
        await self.alert_and_notify(
            level="critical" if final else "warn",
            title=(
                f"All {max_attempts} backup attempts failed"
                if final
                else f"Backup attempt {attempt} failed — retrying"
            ),
            body=(
                f"GhostBackup exhausted all retry attempts. Last error: {error}"
                if final
                else f"Error: {error}. Attempt {attempt} of {max_attempts}."
            ),
            run_id=run_id, send_email=final,
        )

    # ── Test email ────────────────────────────────────────────────────────────

    async def send_test_email(self) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        html = f"""<!DOCTYPE html><html><body style="font-family:'Segoe UI',Arial,sans-serif;background:#0e0f11;color:#e8eaf0;padding:0;margin:0">
<div style="max-width:560px;margin:32px auto;background:#13141a;border:1px solid #1e2030;border-radius:12px;overflow:hidden">
  <div style="background:#1a1d26;padding:20px 24px;border-bottom:1px solid #1e2030">
    <div style="font-size:16px;font-weight:700;color:#f0f1f5">GhostBackup</div>
    <div style="font-size:11px;color:#555872;letter-spacing:1px;text-transform:uppercase">Red Parrot Accounting</div>
  </div>
  <div style="padding:24px;border-left:4px solid #34d399">
    <div style="font-size:18px;font-weight:700;color:#34d399;margin-bottom:8px">✓ SMTP Verified</div>
    <div style="font-size:14px;color:#8b8fa8;line-height:1.6">Email configuration is working. GhostBackup will send run summaries and failure alerts to this address.</div>
  </div>
  <div style="padding:14px 24px;border-top:1px solid #1e2030">
    <div style="font-size:11px;color:#555872;font-family:monospace">{ts}</div>
  </div>
</div></body></html>"""
        await asyncio.to_thread(
            self._send_email,
            "[GhostBackup] SMTP Test — Configuration Verified",
            html,
            "GhostBackup SMTP test successful.",
        )

    # ── Rich run report HTML ──────────────────────────────────────────────────

    def _build_run_email_html(self, run: dict) -> str:
        status     = run.get("status", "unknown")
        run_id     = run.get("run_id", "?")
        started    = run.get("started_at",  "")[:19].replace("T", " ")
        finished   = run.get("finished_at", "")[:19].replace("T", " ")
        files_ok   = run.get("files_transferred", 0)
        files_fail = run.get("files_failed", 0)
        bytes_tx   = _fmt_bytes(run.get("bytes_transferred", 0))
        errors     = run.get("errors", [])

        status_colour = {"success": "#34d399", "partial": "#fbbf24", "failed": "#f87171"}.get(
            status, "#8b8fa8"
        )
        status_icon = {"success": "✓", "partial": "⚠", "failed": "✖"}.get(status, "•")

        _status_colours = {"success": "#34d399", "partial": "#fbbf24", "failed": "#f87171"}
        lib_rows = "".join(
            '<tr>'
            f'<td style="padding:10px 14px;border-bottom:1px solid #1e2030;color:#f0f1f5;font-weight:500">{lib_name}</td>'
            f'<td style="padding:10px 14px;border-bottom:1px solid #1e2030;color:{_status_colours.get(lib_data.get("status",""), "#8b8fa8")};font-weight:600;font-size:11px;text-transform:uppercase">{lib_data.get("status", "unknown")}</td>'
            f'<td style="padding:10px 14px;border-bottom:1px solid #1e2030;color:#8b8fa8;font-family:monospace">{lib_data.get("files_transferred", 0)}</td>'
            f'<td style="padding:10px 14px;border-bottom:1px solid #1e2030;color:{"#f87171" if lib_data.get("files_failed") else "#555872"};font-family:monospace">{lib_data.get("files_failed", 0)}</td>'
            '</tr>'
            for lib_name, lib_data in run.get("libraries", {}).items()
        ) or '<tr><td colspan="4" style="padding:12px 14px;color:#555872;text-align:center">No library data</td></tr>'

        err_items = "".join(
            f'<li style="color:#f87171;margin-bottom:5px;font-size:12px;font-family:monospace">'
            f'<span style="color:#8b8fa8">{e.get("file","?")}</span> — {e.get("error","?")}'
            f'</li>'
            for e in errors[:10]
        )
        overflow = (
            f'<li style="color:#555872;font-size:11px">…and {len(errors)-10} more</li>'
            if len(errors) > 10 else ""
        )
        err_html = (
            f'<div style="padding:0 24px">'
            f'<div style="background:#1a1010;border:1px solid rgba(248,113,113,0.2);'
            f'border-left:4px solid #f87171;border-radius:8px;padding:16px;margin-top:0">'
            f'<div style="color:#f87171;font-weight:700;font-size:12px;text-transform:uppercase;'
            f'letter-spacing:0.5px;margin-bottom:10px">✖ Errors ({len(errors)})</div>'
            f'<ul style="margin:0;padding-left:16px">{err_items}{overflow}</ul></div></div>'
        ) if errors else ""

        stats = "".join(
            f'<div style="flex:1;padding:16px 20px;border-right:1px solid #1e2030">'
            f'<div style="font-size:10px;color:#555872;text-transform:uppercase;'
            f'letter-spacing:0.8px;margin-bottom:5px">{label}</div>'
            f'<div style="font-size:22px;font-weight:800;color:{colour};letter-spacing:-0.5px">{val}</div>'
            f'</div>'
            for label, val, colour in [
                ("Files OK", str(files_ok),   "#34d399"),
                ("Failed",   str(files_fail), "#f87171" if files_fail else "#555872"),
                ("Data",     bytes_tx,        "#8b8fa8"),
            ]
        )

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (
            f'<!DOCTYPE html><html><body style="font-family:\'Segoe UI\',Arial,sans-serif;'
            f'background:#0e0f11;color:#e8eaf0;padding:0;margin:0">'
            f'<div style="max-width:600px;margin:32px auto;background:#13141a;'
            f'border:1px solid #1e2030;border-radius:12px;overflow:hidden">'
            f'<div style="background:#1a1d26;padding:20px 24px;border-bottom:1px solid #1e2030">'
            f'<div style="font-size:17px;font-weight:800;color:#f0f1f5">GhostBackup</div>'
            f'<div style="font-size:11px;color:#555872;letter-spacing:1px;text-transform:uppercase">'
            f'Red Parrot Accounting</div></div>'
            f'<div style="padding:24px;border-bottom:1px solid #1e2030;border-left:4px solid {status_colour}">'
            f'<div style="font-size:20px;font-weight:800;color:#f0f1f5">'
            f'{status_icon} Run #{run_id} — {status.upper()}</div>'
            f'<div style="font-size:12px;color:#555872;font-family:monospace">'
            f'{started} → {finished} UTC</div></div>'
            f'<div style="display:flex;background:#1a1d26;border-bottom:1px solid #1e2030">{stats}</div>'
            f'<div style="padding:20px 24px 16px">'
            f'<div style="font-size:11px;font-weight:600;color:#555872;text-transform:uppercase;'
            f'letter-spacing:0.8px;margin-bottom:12px">Library Breakdown</div>'
            f'<table style="width:100%;border-collapse:collapse;background:#1a1d26;'
            f'border:1px solid #1e2030;border-radius:8px;overflow:hidden">'
            f'<thead><tr style="background:#21253a">'
            f'<th style="padding:8px 14px;text-align:left;font-size:10px;color:#555872;'
            f'text-transform:uppercase;letter-spacing:0.5px">Library</th>'
            f'<th style="padding:8px 14px;text-align:left;font-size:10px;color:#555872;'
            f'text-transform:uppercase;letter-spacing:0.5px">Status</th>'
            f'<th style="padding:8px 14px;text-align:left;font-size:10px;color:#555872;'
            f'text-transform:uppercase;letter-spacing:0.5px">Transferred</th>'
            f'<th style="padding:8px 14px;text-align:left;font-size:10px;color:#555872;'
            f'text-transform:uppercase;letter-spacing:0.5px">Failed</th>'
            f'</tr></thead><tbody>{lib_rows}</tbody></table></div>'
            f'{err_html}'
            f'<div style="padding:16px 24px;border-top:1px solid #1e2030">'
            f'<div style="font-size:11px;color:#555872;font-family:monospace">{ts}</div>'
            f'</div></div></body></html>'
        )

    def _build_run_email_plain(self, run: dict) -> str:
        status   = run.get("status", "unknown").upper()
        run_id   = run.get("run_id", "?")
        files_ok = run.get("files_transferred", 0)
        bytes_tx = _fmt_bytes(run.get("bytes_transferred", 0))
        errors   = run.get("errors", [])
        lines = [
            f"GhostBackup Run #{run_id} — {status}",
            "=" * 40,
            f"Files transferred : {files_ok}",
            f"Data transferred  : {bytes_tx}",
            f"Errors            : {len(errors)}",
            "",
        ]
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
        _run_colours = {"success": "#34d399", "partial": "#fbbf24", "failed": "#f87171"}
        rows = "".join(
            '<tr>'
            f'<td>{r.get("id")}</td>'
            f'<td>{r.get("started_at", "")[:10]}</td>'
            f'<td style="color:{_run_colours.get(r.get("status", ""), "#8b8fa8")}">'
            f'{r.get("status", "unknown").upper()}</td>'
            f'<td>{r.get("files_transferred", 0)}</td>'
            f'<td>{r.get("bytes_human", "—")}</td>'
            f'<td>{r.get("duration_human", "—")}</td>'
            f'<td style="color:#f87171">{r.get("files_failed", 0)}</td>'
            '</tr>'
            for r in runs
        )
        ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        html = _HEALTH_REPORT_TEMPLATE.format(rows=rows, generated=ts)
        path = REPORT_DIR / f"health_{datetime.now(timezone.utc).strftime('%Y%m%d')}.html"
        path.write_text(html, encoding="utf-8")
        return path


