"""
tests/test_reporter.py — Unit tests for AlertManager and Reporter

Run with:  pytest backend/tests/test_reporter.py -v
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reporter import Alert, AlertManager, Reporter


# ── Alert ─────────────────────────────────────────────────────────────────────

class TestAlert:
    def test_alert_has_unique_id(self):
        a1 = Alert("info",  "Title 1", "Body 1")
        a2 = Alert("error", "Title 2", "Body 2")
        assert a1.id != a2.id

    def test_alert_ids_increment(self):
        a1 = Alert("info", "A", "B")
        a2 = Alert("info", "A", "B")
        assert a2.id == a1.id + 1

    def test_alert_to_dict_contains_required_keys(self):
        a = Alert("warn", "Disk full", "Less than 10 GB free", run_id=5)
        d = a.to_dict()
        assert d["id"]    == a.id
        assert d["level"] == "warn"
        assert d["title"] == "Disk full"
        assert d["body"]  == "Less than 10 GB free"
        assert d["run_id"] == 5
        assert d["dismissed"] is False
        assert "ts" in d

    def test_alert_not_dismissed_by_default(self):
        assert Alert("info", "T", "B").dismissed is False

    def test_alert_run_id_defaults_to_none(self):
        assert Alert("info", "T", "B").run_id is None


# ── AlertManager ──────────────────────────────────────────────────────────────

class TestAlertManager:
    def setup_method(self):
        self.mgr = AlertManager()

    def test_add_returns_alert(self):
        a = self.mgr.add("info", "Hello", "World")
        assert isinstance(a, Alert)

    def test_get_all_returns_added_alerts(self):
        self.mgr.add("info",  "A", "B")
        self.mgr.add("error", "C", "D")
        results = self.mgr.get_all()
        assert len(results) == 2

    def test_get_all_most_recent_first(self):
        self.mgr.add("info", "First",  "B")
        self.mgr.add("info", "Second", "B")
        results = self.mgr.get_all()
        assert results[0]["title"] == "Second"

    def test_dismiss_returns_true_for_valid_id(self):
        a = self.mgr.add("warn", "T", "B")
        assert self.mgr.dismiss(a.id) is True

    def test_dismiss_marks_alert_as_dismissed(self):
        a = self.mgr.add("warn", "T", "B")
        self.mgr.dismiss(a.id)
        assert self.mgr.get_all() == []  # excluded by default filter

    def test_dismiss_returns_false_for_unknown_id(self):
        assert self.mgr.dismiss(9999) is False

    def test_dismissed_alerts_excluded_by_default(self):
        a = self.mgr.add("info", "T", "B")
        self.mgr.dismiss(a.id)
        assert self.mgr.get_all(include_dismissed=False) == []

    def test_dismissed_alerts_included_when_flag_set(self):
        a = self.mgr.add("info", "T", "B")
        self.mgr.dismiss(a.id)
        assert len(self.mgr.get_all(include_dismissed=True)) == 1

    def test_dismiss_all_returns_count_of_undismissed(self):
        self.mgr.add("info",  "A", "B")
        self.mgr.add("error", "C", "D")
        assert self.mgr.dismiss_all() == 2

    def test_dismiss_all_does_not_double_count_already_dismissed(self):
        a = self.mgr.add("info",  "A", "B")
        self.mgr.add("error", "C", "D")
        self.mgr.dismiss(a.id)
        assert self.mgr.dismiss_all() == 1

    def test_unread_count_reflects_undismissed(self):
        self.mgr.add("info",  "A", "B")
        self.mgr.add("error", "C", "D")
        assert self.mgr.unread_count() == 2

    def test_unread_count_decreases_after_dismiss(self):
        a = self.mgr.add("info", "A", "B")
        self.mgr.dismiss(a.id)
        assert self.mgr.unread_count() == 0

    def test_max_alerts_cap(self):
        # Fill past the 200-alert deque cap — oldest should be evicted
        for i in range(AlertManager.MAX_ALERTS + 10):
            self.mgr.add("info", f"Alert {i}", "B")
        assert len(self.mgr.get_all()) == AlertManager.MAX_ALERTS


# ── Reporter ──────────────────────────────────────────────────────────────────

def _make_config(recipients=None):
    cfg = MagicMock()
    cfg.smtp_recipients = recipients or []
    cfg.smtp_host       = "smtp.test.com"
    cfg.smtp_port       = 587
    cfg.smtp_use_tls    = True
    cfg.smtp_user       = "test@test.com"
    cfg.smtp_password   = "secret"
    return cfg


class TestReporter:
    def test_alert_and_notify_creates_alert(self):
        reporter = Reporter(_make_config())
        result = asyncio.run(reporter.alert_and_notify(
            level="warn", title="Test alert", body="Something happened",
            send_email=False,
        ))
        assert isinstance(result, Alert)
        assert reporter.alerts.unread_count() == 1

    def test_alert_and_notify_does_not_send_email_when_no_recipients(self):
        reporter  = Reporter(_make_config(recipients=[]))
        send_mock = AsyncMock()
        reporter._send_email = send_mock
        asyncio.run(reporter.alert_and_notify(
            level="error", title="T", body="B", send_email=True,
        ))
        send_mock.assert_not_called()

    def test_alert_and_notify_calls_notify_callback(self):
        reporter = Reporter(_make_config())
        called   = []

        async def cb(title, body):
            called.append((title, body))

        reporter.set_notify_callback(cb)
        asyncio.run(reporter.alert_and_notify(
            level="info", title="Done", body="All good", send_email=False,
        ))
        assert len(called) == 1
        assert called[0][0] == "Done"

    def test_send_run_report_success_adds_info_alert(self):
        reporter = Reporter(_make_config())
        asyncio.run(reporter.send_run_report({
            "status": "success", "run_id": 1,
            "files_transferred": 42, "errors": [],
        }))
        assert reporter.alerts.unread_count() == 1
        alert = reporter.alerts.get_all()[0]
        assert alert["level"] == "info"
        assert "42" in alert["body"]

    def test_send_run_report_failed_adds_error_alert(self):
        reporter = Reporter(_make_config())
        asyncio.run(reporter.send_run_report({
            "status": "failed", "run_id": 2,
            "files_transferred": 0,
            "errors": [{"file": "x.xlsx", "error": "locked"}],
        }))
        alert = reporter.alerts.get_all()[0]
        assert alert["level"] == "error"
        assert "#2" in alert["title"]

    def test_send_run_report_partial_adds_warn_alert(self):
        reporter = Reporter(_make_config())
        asyncio.run(reporter.send_run_report({
            "status": "partial", "run_id": 3,
            "files_transferred": 5, "files_failed": 2, "errors": [],
        }))
        alert = reporter.alerts.get_all()[0]
        assert alert["level"] == "warn"
        assert "2" in alert["body"]

    def test_set_notify_callback_replaces_previous(self):
        reporter = Reporter(_make_config())
        calls_a  = []
        calls_b  = []

        async def cb_a(t, b): calls_a.append(t)
        async def cb_b(t, b): calls_b.append(t)

        reporter.set_notify_callback(cb_a)
        reporter.set_notify_callback(cb_b)
        asyncio.run(reporter.alert_and_notify(
            "info", "Title", "Body", send_email=False
        ))
        assert calls_a == []
        assert calls_b == ["Title"]


# ── Reporter._send_email ──────────────────────────────────────────────────────

class TestSendEmail:
    def _make_config(self, recipients=None, user="test@example.com", password="secret"):
        cfg = MagicMock()
        cfg.smtp_host        = "smtp.example.com"
        cfg.smtp_port        = 587
        cfg.smtp_use_tls     = True
        cfg.smtp_user        = user
        cfg.smtp_password    = password
        cfg.smtp_recipients  = recipients or ["dest@example.com"]
        return cfg

    def test_send_email_skipped_when_no_recipients(self):
        cfg = self._make_config(recipients=[], user="")
        r   = Reporter(cfg)
        with patch("smtplib.SMTP") as mock_smtp:
            r._send_email("Subject", "<html/>", "plain")
            mock_smtp.assert_not_called()

    def test_send_email_skipped_when_no_user(self):
        cfg = self._make_config(user="")
        r   = Reporter(cfg)
        with patch("smtplib.SMTP") as mock_smtp:
            r._send_email("Subject", "<html/>", "plain")
            mock_smtp.assert_not_called()

    def test_send_email_calls_smtp(self):
        cfg = self._make_config()
        r   = Reporter(cfg)
        with patch("smtplib.SMTP") as mock_smtp:
            ctx = mock_smtp.return_value.__enter__.return_value
            r._send_email("Subject", "<html/>", "plain")
            assert ctx.sendmail.called

    def test_send_email_uses_starttls(self):
        cfg = self._make_config()
        r   = Reporter(cfg)
        with patch("smtplib.SMTP") as mock_smtp:
            ctx = mock_smtp.return_value.__enter__.return_value
            r._send_email("Subject", "<html/>", "plain")
            assert ctx.starttls.called

    def test_send_email_logs_in_when_password_set(self):
        cfg = self._make_config()
        r   = Reporter(cfg)
        with patch("smtplib.SMTP") as mock_smtp:
            ctx = mock_smtp.return_value.__enter__.return_value
            r._send_email("Subject", "<html/>", "plain")
            assert ctx.login.called

    def test_send_email_skips_login_when_no_password(self):
        cfg = self._make_config(password="")
        r   = Reporter(cfg)
        with patch("smtplib.SMTP") as mock_smtp:
            ctx = mock_smtp.return_value.__enter__.return_value
            r._send_email("Subject", "<html/>", "plain")
            ctx.login.assert_not_called()

    def test_send_test_email_calls_send_email(self):
        cfg = self._make_config()
        r   = Reporter(cfg)
        with patch.object(r, "_send_email") as mock_send:
            asyncio.run(r.send_test_email())
            assert mock_send.called
            assert "SMTP" in mock_send.call_args[0][0] or "Test" in mock_send.call_args[0][0]


# ── Reporter.generate_health_report ───────────────────────────────────────────

class TestHealthReport:
    def test_health_report_returns_path(self, tmp_path):
        cfg = MagicMock()
        r   = Reporter.__new__(Reporter)
        r._config = cfg
        r.alerts  = AlertManager()
        r._notify_cb = None
        tmp_path.mkdir(parents=True, exist_ok=True)
        with patch("reporter.REPORT_DIR", tmp_path):
            path = r.generate_health_report([])
            assert path.exists()

    def test_health_report_contains_html(self, tmp_path):
        cfg = MagicMock()
        r   = Reporter.__new__(Reporter)
        r._config = cfg
        r.alerts  = AlertManager()
        r._notify_cb = None
        tmp_path.mkdir(parents=True, exist_ok=True)
        with patch("reporter.REPORT_DIR", tmp_path):
            path = r.generate_health_report([{"id": 1, "status": "success", "started_at": "2026-01-01", "files_transferred": 5, "bytes_human": "10 MB", "duration_human": "1m", "files_failed": 0}])
            content = path.read_text()
            assert "GhostBackup" in content
            assert "SUCCESS" in content
