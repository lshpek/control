from datetime import timedelta

from sqlalchemy import select

from app import service_monitor
from app.database import SessionLocal
from app.models import ActivityEvent, Service, utcnow


def _add_service(*, status="unknown", last_checked_at=None):
    with SessionLocal() as db:
        service = Service(
            name="Monitor test service", type="api", url="https://example.com/health",
            status=status, status_source="manual", desired_check_interval_seconds=60,
            last_checked_at=last_checked_at,
        )
        db.add(service)
        db.commit()
        db.refresh(service)
        return service.id


def _mock_alerts(monkeypatch):
    sent = []
    monkeypatch.setattr(service_monitor.settings, "telegram_bot_token", "123456:test-token")
    monkeypatch.setattr(service_monitor.settings, "telegram_alert_chat_id", "123456789")
    monkeypatch.setattr(service_monitor, "_send_telegram_alert", lambda message: sent.append(message) or True)
    return sent


def test_monitor_records_down_status_and_sends_alert(monkeypatch):
    sent = _mock_alerts(monkeypatch)
    service_id = _add_service()
    monkeypatch.setattr(service_monitor, "_probe_target", lambda _target: ("down", "Ошибка соединения или таймаут"))
    assert service_monitor.run_due_service_checks() == 1
    with SessionLocal() as db:
        service = db.get(Service, service_id)
        assert service.status == "down"
        assert service.status_source == "probe"
        assert service.last_checked_at is not None
        event = db.scalar(select(ActivityEvent).where(ActivityEvent.entity_type == "service", ActivityEvent.entity_id == service_id, ActivityEvent.action == "probed"))
        assert event is not None
        assert "Автомониторинг" in event.summary
    assert len(sent) == 1
    assert "Проблема с сервисом" in sent[0]
    assert "Monitor test service" in sent[0]


def test_monitor_does_not_repeat_alert_for_unchanged_failure(monkeypatch):
    sent = _mock_alerts(monkeypatch)
    _add_service(status="down", last_checked_at=utcnow() - timedelta(seconds=600))
    monkeypatch.setattr(service_monitor, "_probe_target", lambda _target: ("down", "Ошибка соединения или таймаут"))
    assert service_monitor.run_due_service_checks() == 1
    assert sent == []


def test_monitor_sends_recovery_alert(monkeypatch):
    sent = _mock_alerts(monkeypatch)
    _add_service(status="down", last_checked_at=utcnow() - timedelta(seconds=600))
    monkeypatch.setattr(service_monitor, "_probe_target", lambda _target: ("healthy", "HTTP 200"))
    assert service_monitor.run_due_service_checks() == 1
    assert len(sent) == 1
    assert "Сервис восстановлен" in sent[0]
    assert "Работает" in sent[0]


def test_monitor_skips_service_until_its_check_interval(monkeypatch):
    _add_service(status="healthy", last_checked_at=utcnow())
    called = []
    monkeypatch.setattr(service_monitor, "_probe_target", lambda target: called.append(target) or ("healthy", "HTTP 200"))
    assert service_monitor.run_due_service_checks() == 0
    assert called == []


def test_monitor_rejects_local_or_private_urls(monkeypatch):
    for url in ("http://127.0.0.1/health", "http://localhost/health", "file:///etc/passwd", "https://user:pass@example.com/health"):
        try:
            service_monitor._validate_public_url(url)
        except ValueError:
            pass
        else:
            assert False, f"Unsafe URL was accepted: {url}"
