"""
scheduler.py — GhostBackup Backup Scheduler

Manages the daily scheduled backup job, a per-minute watchdog that detects
stalled runs, and an hourly missed-backup check that alerts when no successful
run has completed within the expected window.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Coroutine, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import ConfigManager

logger = logging.getLogger("scheduler")

JOB_ID          = "ghostbackup_daily"
WATCHDOG_JOB_ID = "ghostbackup_watchdog"
MISSED_JOB_ID   = "ghostbackup_missed_check"
DRILL_JOB_ID    = "ghostbackup_drill_check"

MISSED_BACKUP_HOURS = 36


class BackupScheduler:
    def __init__(
        self,
        config: ConfigManager,
        job_fn: Callable[..., Coroutine],
        reporter=None,
    ):
        self._config   = config
        self._job_fn   = job_fn
        self._reporter = reporter
        self._sched    = AsyncIOScheduler(timezone=config.timezone)
        self._running  = False

        self._job_start_time: Optional[datetime] = None
        self._current_run_id: Optional[int]      = None
        self._retry_count                         = 0
        self._stall_alerted  = False
        self._missed_alerted = False
        self._manifest_ref   = None

    def set_reporter(self, reporter) -> None:
        """Update the reporter reference after construction."""
        self._reporter = reporter

    def set_manifest(self, manifest) -> None:
        """Inject ManifestDB so the missed-backup check can query run history."""
        self._manifest_ref = manifest

    def reset_missed_alert(self) -> None:
        """Clear the missed-backup alert flag after a successful run."""
        self._missed_alerted = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._schedule_daily_job()
        self._schedule_watchdog()
        self._schedule_missed_backup_check()
        self._schedule_drill_check()
        self._sched.start()
        self._running = True
        logger.info(
            f"Scheduler started — daily run at {self._config.schedule_time} "
            f"({self._config.timezone})"
        )

    def stop(self) -> None:
        self._sched.shutdown(wait=False)
        self._running = False
        logger.info("Scheduler stopped")

    def is_running(self) -> bool:
        return self._running

    def next_run_time(self) -> Optional[str]:
        job = self._sched.get_job(JOB_ID)
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return None

    def set_current_run_id(self, run_id: Optional[int]) -> None:
        """Called by api.py so the watchdog can attach a run_id to stall alerts."""
        self._current_run_id = run_id

    # ── Scheduling ────────────────────────────────────────────────────────────

    def _schedule_daily_job(self) -> None:
        hour, minute = _parse_time(self._config.schedule_time)
        self._sched.add_job(
            self._run_with_retry,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=self._config.timezone),
            id=JOB_ID,
            name="GhostBackup Daily Run",
            replace_existing=True,
            misfire_grace_time=1800,
            coalesce=True,
        )
        logger.info(f"Daily job scheduled: {hour:02d}:{minute:02d} {self._config.timezone}")

    def _schedule_watchdog(self) -> None:
        self._sched.add_job(
            self._watchdog_check,
            trigger="interval",
            minutes=1,
            id=WATCHDOG_JOB_ID,
            name="GhostBackup Watchdog",
            replace_existing=True,
        )

    def _schedule_missed_backup_check(self) -> None:
        self._sched.add_job(
            self._missed_backup_check,
            trigger="interval",
            hours=1,
            id=MISSED_JOB_ID,
            name="GhostBackup Missed-Backup Check",
            replace_existing=True,
        )

    def reschedule(self, new_time: str, new_timezone: str) -> None:
        hour, minute = _parse_time(new_time)
        job = self._sched.get_job(JOB_ID)
        if job:
            job.reschedule(
                trigger=CronTrigger(hour=hour, minute=minute, timezone=new_timezone)
            )
        else:
            self._schedule_daily_job()
        logger.info(f"Job rescheduled to {new_time} ({new_timezone})")

    # ── Job runner with retry ─────────────────────────────────────────────────

    async def _run_with_retry(self) -> None:
        """
        Invoke the backup job and retry up to config.retry_count times on failure.
        Sends a retry alert on each failure and a critical alert after all attempts.
        """
        max_retries   = self._config.retry_count
        retry_delay_s = self._config.retry_delay_minutes * 60
        self._retry_count = 0

        for attempt in range(max_retries + 1):
            try:
                logger.info(f"Starting backup job (attempt {attempt + 1}/{max_retries + 1})")
                self._job_start_time = datetime.now(timezone.utc)
                self._stall_alerted  = False
                await self._job_fn()
                self._job_start_time = None
                self._retry_count    = 0
                self._current_run_id = None
                logger.info("Backup job completed successfully")
                return

            except Exception as e:
                error_str = str(e)
                logger.error(f"Backup job failed (attempt {attempt + 1}): {error_str}")
                self._retry_count = attempt + 1

                if self._reporter:
                    try:
                        await self._reporter.send_retry_alert(
                            attempt      = attempt + 1,
                            max_attempts = max_retries + 1,
                            error        = error_str,
                            run_id       = self._current_run_id,
                        )
                    except Exception as alert_err:
                        logger.error(f"Failed to send retry alert: {alert_err}")

                if attempt < max_retries:
                    logger.info(
                        f"Retrying in {self._config.retry_delay_minutes} minutes..."
                    )
                    await asyncio.sleep(retry_delay_s)
                else:
                    logger.error(
                        f"All {max_retries + 1} attempts failed. Manual intervention required."
                    )
                    self._job_start_time = None

    # ── Watchdog ──────────────────────────────────────────────────────────────

    async def _watchdog_check(self) -> None:
        """
        Alert once if the backup job has been running longer than max_job_minutes.
        Resets on the next successful job start.
        """
        if not self._job_start_time:
            return

        elapsed_minutes = int(
            (datetime.now(timezone.utc) - self._job_start_time).total_seconds() // 60
        )
        max_minutes = self._config.max_job_minutes

        if elapsed_minutes >= max_minutes - 10:
            logger.warning(
                f"Watchdog: job running {elapsed_minutes}m "
                f"(limit {max_minutes}m) — approaching timeout"
            )

        if elapsed_minutes >= max_minutes and not self._stall_alerted:
            logger.critical(
                f"Watchdog: job exceeded {max_minutes}m — flagging as stalled"
            )
            self._stall_alerted  = True
            self._job_start_time = None

            if self._reporter:
                try:
                    await self._reporter.send_watchdog_alert(
                        elapsed_minutes = elapsed_minutes,
                        max_minutes     = max_minutes,
                        run_id          = self._current_run_id,
                    )
                except Exception as alert_err:
                    logger.error(f"Failed to send watchdog alert: {alert_err}")

    # ── Missed-backup check ───────────────────────────────────────────────────

    async def _missed_backup_check(self) -> None:
        """
        Alert once if no successful backup has completed in MISSED_BACKUP_HOURS.
        Resets automatically when a fresh successful run is detected.
        Catches the case where the machine is off at the scheduled time every day.
        """
        if not self._reporter or not self._manifest_ref:
            return

        try:
            last = self._manifest_ref.get_latest_successful_run()
            if not last:
                return

            last_dt   = datetime.fromisoformat(last["started_at"])
            # Ensure last_dt is timezone-aware — stored timestamps may be naive UTC
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            now_utc   = datetime.now(timezone.utc)
            hours_ago = (now_utc - last_dt).total_seconds() / 3600

            if hours_ago >= MISSED_BACKUP_HOURS and not self._missed_alerted:
                self._missed_alerted = True
                logger.warning(
                    f"No successful backup in {hours_ago:.1f}h "
                    f"(threshold: {MISSED_BACKUP_HOURS}h)"
                )
                await self._reporter.alert_and_notify(
                    level="error",
                    title=f"No backup in {int(hours_ago)} hours",
                    body=(
                        f"GhostBackup has not completed a successful backup run in "
                        f"{int(hours_ago)} hours (last: {last['started_at'][:16]} UTC). "
                        f"Verify the machine was running at the scheduled time and "
                        f"that the backup drive is connected."
                    ),
                    send_email=True,
                )
            elif hours_ago < MISSED_BACKUP_HOURS:
                self._missed_alerted = False

        except Exception as e:
            logger.error(f"Missed-backup check error: {e}")

    # ── Restore drill check ──────────────────────────────────────────────────

    _DRILL_DUE_DAYS = 30
    _DRILL_WARN_DAYS = 37
    _DRILL_CRITICAL_DAYS = 44
    _drill_alerted_level: Optional[str] = None

    def _schedule_drill_check(self) -> None:
        self._sched.add_job(
            self._restore_drill_check,
            trigger="interval",
            hours=24,
            id=DRILL_JOB_ID,
            name="GhostBackup Restore Drill Check",
            replace_existing=True,
        )

    async def _restore_drill_check(self) -> None:
        """
        Escalating reminders for monthly restore drills.
        - 30 days: info-level alert
        - 37 days: warning + email
        - 44 days: critical + email
        Resets when a drill is completed (days < 30).
        """
        if not self._reporter or not self._manifest_ref:
            return

        try:
            last = self._manifest_ref.get_last_drill_completion()
            if not last:
                # No drill ever recorded — treat as overdue from day one
                days_since = self._DRILL_CRITICAL_DAYS
            else:
                last_dt = datetime.fromisoformat(last)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                days_since = (datetime.now(timezone.utc) - last_dt).days

            if days_since < self._DRILL_DUE_DAYS:
                # Drill is current — reset alert level
                self._drill_alerted_level = None
                return

            if days_since >= self._DRILL_CRITICAL_DAYS and self._drill_alerted_level != "critical":
                self._drill_alerted_level = "critical"
                logger.critical(
                    f"Restore drill CRITICAL overdue: {days_since} days since last drill"
                )
                await self._reporter.alert_and_notify(
                    level="error",
                    title=f"Restore drill critically overdue ({days_since} days)",
                    body=(
                        f"No restore drill has been completed in {days_since} days. "
                        f"Monthly test restores are required for compliance. "
                        f"Please perform a test restore immediately."
                    ),
                    send_email=True,
                )
            elif days_since >= self._DRILL_WARN_DAYS and self._drill_alerted_level not in ("warn", "critical"):
                self._drill_alerted_level = "warn"
                logger.warning(
                    f"Restore drill overdue: {days_since} days since last drill"
                )
                await self._reporter.alert_and_notify(
                    level="warning",
                    title=f"Restore drill overdue ({days_since} days)",
                    body=(
                        f"No restore drill has been completed in {days_since} days. "
                        f"Monthly test restores are recommended for compliance."
                    ),
                    send_email=True,
                )
            elif days_since >= self._DRILL_DUE_DAYS and self._drill_alerted_level is None:
                self._drill_alerted_level = "info"
                logger.info(
                    f"Restore drill due: {days_since} days since last drill"
                )
                self._reporter.alerts.add(
                    "info",
                    "Restore drill due",
                    f"It has been {days_since} days since the last restore drill. "
                    f"Consider performing a test restore.",
                )

        except Exception as e:
            logger.error(f"Restore drill check error: {e}")

    # ── Utilities ─────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "running":         self._running,
            "next_run":        self.next_run_time(),
            "schedule_time":   self._config.schedule_time,
            "timezone":        self._config.timezone,
            "retry_count":     self._retry_count,
            "job_start_time":  (
                self._job_start_time.isoformat() if self._job_start_time else None
            ),
            "max_job_minutes": self._config.max_job_minutes,
        }


# ── Module-level utilities ────────────────────────────────────────────────────

def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse HH:MM time string. Returns (8, 0) and logs a warning on invalid input."""
    try:
        parts  = time_str.strip().split(":")
        hour   = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        return hour, minute
    except (ValueError, IndexError):
        logger.warning(f"Invalid schedule time '{time_str}' — defaulting to 08:00")
        return 8, 0
