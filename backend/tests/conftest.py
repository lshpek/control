import os
import secrets
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DEBUG"] = "true"
os.environ["LOCAL_DEV_MODE"] = "true"
os.environ["BIND_HOST"] = "127.0.0.1"
os.environ["DATABASE_URL"] = "sqlite:///./test_botvex.db"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:5173,http://localhost:5173"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hash_password, token_digest
from app.bootstrap_owner import seed_authorization
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import AuthSession, Role, User, utcnow


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    token = secrets.token_urlsafe(32)
    now = utcnow()
    with SessionLocal() as db:
        seed_authorization(db)
        owner_role = db.scalar(select(Role).where(Role.slug == "owner"))
        user = User(
            username="test-owner",
            password_hash=hash_password("test-owner-password-long"),
            is_active=True,
            is_owner=True,
            must_change_password=False,
            roles=[owner_role],
        )
        db.add(user)
        db.flush()
        db.add(AuthSession(
            user_id=user.id,
            token_hash=token_digest(token),
            created_at=now,
            expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
        ))
        db.commit()
    with TestClient(app) as test_client:
        test_client.cookies.set(settings.session_cookie_name, token)
        yield test_client
