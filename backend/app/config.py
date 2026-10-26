from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env", override=False)

def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}

class Settings:
    app_name = os.getenv("APP_NAME", "BOTVEX Control Center")
    app_version = os.getenv("APP_VERSION", "0.1.0")
    debug = _bool("DEBUG", False)
    local_dev_mode = _bool("LOCAL_DEV_MODE", False)
    bind_host = os.getenv("BIND_HOST", "127.0.0.1")
    database_url = os.getenv("DATABASE_URL", "sqlite:///./backend/botvex.db")
    cors_origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",") if x.strip()]
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_init_data_max_age_seconds = int(os.getenv("TELEGRAM_INIT_DATA_MAX_AGE_SECONDS", "3600"))
    session_cookie_name = os.getenv("SESSION_COOKIE_NAME", "botvex_session").strip() or "botvex_session"
    session_ttl_seconds = int(os.getenv("SESSION_TTL_SECONDS", "28800"))
    login_window_seconds = int(os.getenv("LOGIN_WINDOW_SECONDS", "900"))
    login_max_per_identity = int(os.getenv("LOGIN_MAX_PER_IDENTITY", "5"))
    login_max_per_ip = int(os.getenv("LOGIN_MAX_PER_IP", "20"))
    bootstrap_owner_username = os.getenv("BOOTSTRAP_OWNER_USERNAME", "lshpek").strip().casefold()
    bootstrap_owner_password = os.getenv("BOOTSTRAP_OWNER_PASSWORD", "")

    def validate(self) -> None:
        if self.local_dev_mode:
            if not (self.debug and self.bind_host in {"127.0.0.1", "localhost", "::1"}):
                raise RuntimeError("LOCAL_DEV_MODE разрешён только при DEBUG=true и bind на loopback-интерфейс.")
        else:
            if "*" in self.cors_origins:
                raise RuntimeError("Wildcard CORS запрещён в production.")
        if self.telegram_init_data_max_age_seconds < 60:
            raise RuntimeError("TELEGRAM_INIT_DATA_MAX_AGE_SECONDS должен быть не меньше 60.")
        if not 900 <= self.session_ttl_seconds <= 86400:
            raise RuntimeError("SESSION_TTL_SECONDS должен быть в диапазоне 900..86400.")
        if not 60 <= self.login_window_seconds <= 3600:
            raise RuntimeError("LOGIN_WINDOW_SECONDS должен быть в диапазоне 60..3600.")
        if not 1 <= self.login_max_per_identity <= 20 or not 1 <= self.login_max_per_ip <= 100:
            raise RuntimeError("Лимиты попыток входа находятся вне допустимого диапазона.")

settings = Settings()
