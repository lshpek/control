"""Authentication, opaque server-side sessions and deny-by-default RBAC."""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from .config import settings
from .database import get_db
from .models import AuthSession, Permission, Role, RolePermissionGrant, User, utcnow

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)
def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def set_session_cookie(response: Response, token: str, max_age: int | None = None) -> None:
    if max_age is None:
        max_age = settings.session_ttl_seconds
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=not settings.local_dev_mode,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=not settings.local_dev_mode,
        samesite="lax",
    )


def create_session(db: Session, user: User, request: Request) -> str:
    raw_token = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(AuthSession(
        user_id=user.id,
        token_hash=token_digest(raw_token),
        created_at=now,
        expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
        user_agent=(request.headers.get("user-agent") or "")[:250] or None,
    ))
    return raw_token


def _load_session_user(token: str, db: Session) -> tuple[User | None, AuthSession | None]:
    session_row = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(token)))
    if session_row is None:
        return None, None
    now = utcnow()
    if session_row.revoked_at is not None or session_row.expires_at <= now:
        if session_row.revoked_at is None:
            session_row.revoked_at = now
            db.commit()
        return None, session_row
    user = db.scalar(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.grants).selectinload(RolePermissionGrant.permission))
        .where(User.id == session_row.user_id)
    )
    if user is None or not user.is_active:
        session_row.revoked_at = now
        db.commit()
        return None, session_row
    return user, session_row


def current_session_row(request: Request, db: Session) -> tuple[User | None, AuthSession | None]:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None, None
    user, session_row = _load_session_user(token, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Сессия недействительна или истекла. Войди снова.")
    return user, session_row


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user, _ = current_session_row(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется вход в аккаунт")
    return user


def _effective_permission_scope(user: User, permission_key: str) -> str | None:
    if user.is_owner or any(role.slug == "owner" and role.is_active for role in user.roles):
        return "all"
    # Multiple roles are additive: the broadest explicitly granted scope wins.
    ranking = {"own_customer": 1, "assigned": 2, "all": 3}
    scopes: list[str] = []
    for role in user.roles:
        if not role.is_active:
            continue
        for grant in role.grants:
            if grant.permission.key == permission_key:
                scopes.append(grant.scope)
    return max(scopes, key=lambda s: ranking.get(s, 0), default=None)


def effective_permissions(user: User) -> dict[str, str]:
    if user.is_owner or any(role.slug == "owner" and role.is_active for role in user.roles):
        return {"*": "all"}
    result: dict[str, str] = {}
    ranking = {"own_customer": 1, "assigned": 2, "all": 3}
    for role in user.roles:
        if not role.is_active:
            continue
        for grant in role.grants:
            key = grant.permission.key
            if key not in result or ranking.get(grant.scope, 0) > ranking.get(result[key], 0):
                result[key] = grant.scope
    return result


@dataclass(frozen=True)
class AccessContext:
    user: User | None
    scope: str
    is_owner: bool = False

    @property
    def user_id(self) -> int | None:
        return self.user.id if self.user else None


def require_owner(request: Request, db: Session = Depends(get_db)) -> AccessContext:
    user, _ = current_session_row(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется вход в аккаунт владельца")
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Перед работой необходимо заменить временный пароль")
    if not user.is_owner and not any(role.slug == "owner" and role.is_active for role in user.roles):
        raise HTTPException(status_code=403, detail="Это действие доступно только владельцу")
    return AccessContext(user=user, scope="all", is_owner=True)


def require_permission(permission_key: str) -> Callable[..., AccessContext]:
    def dependency(user: User = Depends(get_current_user)) -> AccessContext:
        if user.must_change_password:
            raise HTTPException(status_code=403, detail="Перед работой необходимо заменить временный пароль")
        if any(role.slug == "client" and role.is_active for role in user.roles) and not permission_key.startswith("portal:"):
            raise HTTPException(status_code=403, detail="Клиентский аккаунт не имеет доступа к внутреннему API")
        scope = _effective_permission_scope(user, permission_key)
        if scope is None:
            raise HTTPException(status_code=403, detail="Недостаточно прав для этой операции")
        return AccessContext(user=user, scope=scope, is_owner=user.is_owner or any(role.slug == "owner" and role.is_active for role in user.roles))
    dependency.__name__ = f"require_permission_{permission_key.replace(':', '_')}"
    return dependency


def require_client_portal_user(user: User = Depends(get_current_user)) -> User:
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Перед работой необходимо заменить временный пароль")
    if user.customer_id is None or not any(role.slug == "client" and role.is_active for role in user.roles):
        raise HTTPException(status_code=403, detail="Для аккаунта не настроен доступ к клиентскому порталу")
    return user
