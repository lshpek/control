from __future__ import annotations
import hashlib, hmac, json, time
from urllib.parse import parse_qsl

def validate_telegram_init_data(init_data: str, bot_token: str, max_age_seconds: int, now: int | None = None) -> dict:
    if not init_data or len(init_data) > 16_384:
        raise ValueError("initData отсутствует или слишком велик")
    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    values: dict[str, str] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("initData содержит повторяющийся параметр")
        values[key] = value
    received_hash = values.pop("hash", None)
    if not received_hash or len(received_hash) != 64:
        raise ValueError("hash отсутствует или имеет неверный формат")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise ValueError("Подпись Telegram initData не прошла проверку")
    try:
        auth_date = int(values["auth_date"])
    except (KeyError, ValueError) as exc:
        raise ValueError("auth_date отсутствует или некорректен") from exc
    current = int(time.time()) if now is None else now
    if auth_date > current + 60 or current - auth_date > max_age_seconds:
        raise ValueError("Telegram initData просрочен или имеет дату из будущего")
    try:
        user = json.loads(values["user"])
        user_id = str(user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("В initData отсутствует корректный user.id") from exc
    return {"user_id": user_id, "user": user, "auth_date": auth_date}
