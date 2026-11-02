from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import time
from datetime import datetime
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select

from .config import settings
from .database import SessionLocal
from .models import ActivityEvent, Service, utcnow

logger = logging.getLogger("botvex.service_monitor")

STATUS_LABELS = {
    "healthy": "✅ Работает",
    "degraded": "⚠️ Работает с ошибками",
    "down": "🔴 Недоступен",
}


def _validate_public_url(url: str) -> str:
    """Accept only public HTTP(S) endpoints; reject private/local/reserved destinations."""
    parsed = urlsplit((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Разрешены только абсолютные HTTP/HTTPS URL без учётных данных")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("Некорректный порт")
    host = parsed.hostname.strip().rstrip(".")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError("Не удалось разрешить DNS-имя") from exc
        addresses = []
        for record in records:
            candidate = record[4][0]
            try:
                addresses.append(ipaddress.ip_address(candidate))
            except ValueError:
                continue
    if not addresses:
        raise ValueError("Не удалось определить IP-адрес узла")
    # A hostname is rejected if any answer is non-public, preventing mixed public/private DNS.
    for address in addresses:
        if (not address.is_global or address.is_private or address.is_loopback or address.is_link_local
                or address.is_multicast or address.is_reserved or address.is_unspecified):
            raise ValueError("Внутренние, локальные и зарезервированные адреса запрещены")
    return url.strip()


def _is_due(last_checked_at: datetime | None, interval_seconds: int, now: datetime) -> bool:
    if last_checked_at is None:
        return True
    last, current = last_checked_at, now
    if last.tzinfo is not None and current.tzinfo is None:
        last = last.replace(tzinfo=None)
    elif current.tzinfo is not None and last.tzinfo is None:
        current = current.replace(tzinfo=None)
    interval = min(86400, max(60, int(interval_seconds or 300)))
    return (current - last).total_seconds() >= interval


def _probe_target(target: str) -> tuple[str, str]:
    try:
        safe_url = _validate_public_url(target)
    except (ValueError, OSError):
        return "degraded", "Адрес не прошёл проверку безопасности или DNS"
    try:
        response = httpx.get(
            safe_url,
            timeout=settings.service_monitor_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": "BOTVEX-Control-Center-Monitor/1.0"},
        )
    except httpx.HTTPError:
        return "down", "Ошибка соединения или таймаут"
    if 200 <= response.status_code < 400:
        return "healthy", f"HTTP {response.status_code}"
    if 400 <= response.status_code < 500:
        return "degraded", f"HTTP {response.status_code}"
    return "down", f"HTTP {response.status_code}"


def _should_alert(previous: str, current: str) -> bool:
    if current in {"down", "degraded"}:
        return previous != current
    return current == "healthy" and previous in {"down", "degraded"}


def _send_telegram_alert(message: str) -> bool:
    token = settings.telegram_bot_token
    chat_id = settings.telegram_alert_chat_id
    if not token or not chat_id:
        return False
    if not chat_id.lstrip("-").isdigit():
        logger.warning("Telegram alerts disabled: TELEGRAM_ALERT_CHAT_ID must be a numeric chat ID")
        return False
    # The token is part of the API URL. Never log the URL or exception contents.
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message[:3900], "disable_web_page_preview": True}
    for attempt in range(3):
        try:
            response = httpx.post(endpoint, json=payload, timeout=5.0)
            response.raise_for_status()
            result = response.json()
            if isinstance(result, dict) and result.get("ok") is True:
                return True
            logger.warning("Telegram rejected a service-monitor alert")
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Telegram service-monitor delivery failed (%s)", type(exc).__name__)
        if attempt < 2:
            time.sleep(attempt + 1)
    return False


def _check_one_service(service_id: int) -> bool:
    with SessionLocal() as db:
        service = db.get(Service, service_id)
        if service is None or service.is_archived:
            return False
        target = (service.health_endpoint or service.url or "").strip()
        if not target:
            return False
        expected_last_checked = service.last_checked_at
        if not _is_due(expected_last_checked, service.desired_check_interval_seconds, utcnow()):
            return False
        service_name = service.name
        interval = service.desired_check_interval_seconds

    status, detail = _probe_target(target)

    with SessionLocal() as db:
        service = db.get(Service, service_id)
        if service is None or service.is_archived:
            return False
        current_target = (service.health_endpoint or service.url or "").strip()
        # Ignore stale responses if target/settings were changed while the request was running.
        if current_target != target or service.last_checked_at != expected_last_checked:
            return False
        previous = service.status
        service.status = status
        service.status_source = "probe"
        service.last_checked_at = utcnow()
        if previous != status:
            db.add(ActivityEvent(
                actor="service_monitor", entity_type="service", entity_id=service_id,
                action="probed", summary=f"Автомониторинг «{service_name}»: {previous} → {status} ({detail})"[:500],
            ))
        db.commit()

    if _should_alert(previous, status):
        event = "Сервис восстановлен" if status == "healthy" else "Проблема с сервисом"
        message = (
            f"BOTVEX Control Center\n{event}\n\n"
            f"Сервис: {service_name[:180]}\n"
            f"Статус: {STATUS_LABELS.get(status, status)}\n"
            f"Детали: {detail[:240]}\n"
            f"Интервал проверки: {min(86400, max(60, int(interval or 300)))} сек.\n"
            f"Время UTC: {utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if not _send_telegram_alert(message):
            logger.warning("Alert could not be delivered for service #%s; status is saved", service_id)
    return True


def run_due_service_checks() -> int:
    """Check due public HTTP endpoints and persist current status."""
    with SessionLocal() as db:
        ids = list(db.scalars(select(Service.id).where(Service.is_archived.is_(False)).order_by(Service.id.asc())).all())
    checked = 0
    for service_id in ids:
        try:
            checked += int(_check_one_service(service_id))
        except Exception:
            logger.exception("Unexpected error while checking service #%s", service_id)
    return checked


async def service_monitor_loop() -> None:
    logger.info("Service monitor started (poll=%ss, Telegram alerts=%s)",
                settings.service_monitor_poll_seconds,
                bool(settings.telegram_bot_token and settings.telegram_alert_chat_id))
    while True:
        try:
            await asyncio.to_thread(run_due_service_checks)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Service-monitor cycle failed")
        await asyncio.sleep(settings.service_monitor_poll_seconds)
