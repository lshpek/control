from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from argon2.exceptions import VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from .auth import (
    AccessContext, _effective_permission_scope, clear_session_cookie, create_session, get_current_user,
    effective_permissions, hash_password, password_hasher, require_permission, set_session_cookie,
    token_digest, verify_password,
)
from .config import settings
from .bootstrap_owner import OWNER_ONLY_PERMISSION_KEYS
from .database import get_db
from .models import (
    ActivityEvent, AuthSession, Client, LoginAttempt, Permission, Project,
    ProjectAssignment, Role, RolePermissionGrant, User, utcnow,
)
from .schemas import (
    AdminSessionListRead, AdminUserCreate, AdminUserCreateResult, AdminUserListRead, AdminUserRead,
    AdminUserUpdate, ChangePasswordRequest, LoginRequest, RoleCreate, RoleRead,
    RoleUpdate, UserProfileRead, ProjectAssignmentCreate, ProjectAssignmentRead,
)
from .security import validate_telegram_init_data

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["owner administration"])

# A precomputed dummy Argon2id hash keeps the unknown-username path from skipping
# password verification. It is never a valid account credential.
_DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))


def _profile(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "roles": sorted(role.slug for role in user.roles if role.is_active),
        "permissions": effective_permissions(user),
        "customer_id": user.customer_id,
        "telegram_user_id": user.telegram_user_id,
        "is_owner": user.is_owner,
        "must_change_password": user.must_change_password,
        "last_login_at": user.last_login_at,
    }


def _admin_user(user: User) -> dict:
    return {
        **_profile(user),
        "is_active": user.is_active,
        "created_at": user.created_at,
    }


def _verify_request_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in settings.cors_origins:
        raise HTTPException(status_code=403, detail="Источник запроса не разрешён")


def _login_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _check_login_rate_limit(db: Session, ip_hash: str, username_hash: str, now) -> None:
    cutoff = now - timedelta(seconds=settings.login_window_seconds)
    same_identity = db.scalar(select(func.count(LoginAttempt.id)).where(
        LoginAttempt.ip_hash == ip_hash,
        LoginAttempt.username_hash == username_hash,
        LoginAttempt.attempted_at >= cutoff,
    )) or 0
    same_ip = db.scalar(select(func.count(LoginAttempt.id)).where(
        LoginAttempt.ip_hash == ip_hash,
        LoginAttempt.attempted_at >= cutoff,
    )) or 0
    if same_identity >= settings.login_max_per_identity or (same_ip >= settings.login_max_per_ip and same_identity >= 1):
        raise HTTPException(status_code=429, detail="Превышен лимит попыток аутентификации. Повторите запрос позже.")


def _record_failed_login(db: Session, user: User | None, ip_hash: str, username_hash: str, now) -> None:
    db.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < now - timedelta(days=1)))
    db.add(LoginAttempt(ip_hash=ip_hash, username_hash=username_hash, attempted_at=now))
    if user is not None:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 10:
            user.locked_until = now + timedelta(minutes=15)
            user.failed_login_attempts = 0
    db.commit()


@router.post("/login", response_model=UserProfileRead)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    _verify_request_origin(request)
    now = utcnow()
    username = payload.username.strip().casefold()
    username_hash = _login_hash(username)
    ip = request.client.host if request.client else "unknown"
    ip_hash = _login_hash(ip)
    _check_login_rate_limit(db, ip_hash, username_hash, now)
    user = db.scalar(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.grants).selectinload(RolePermissionGrant.permission))
        .where(User.username == username)
    )
    hash_to_verify = user.password_hash if user is not None else _DUMMY_HASH
    password_ok = verify_password(hash_to_verify, payload.password)
    is_locked = bool(user and user.locked_until and user.locked_until > now)
    if user is None or not password_ok or not user.is_active or is_locked:
        _record_failed_login(db, user, ip_hash, username_hash, now)
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    user.last_login_at = now
    user.failed_login_attempts = 0
    user.locked_until = None
    db.execute(delete(LoginAttempt).where(
        LoginAttempt.ip_hash == ip_hash,
        LoginAttempt.username_hash == username_hash,
    ))
    token = create_session(db, user, request)
    db.commit()
    set_session_cookie(response, token, settings.session_ttl_seconds)
    return _profile(user)


@router.post("/telegram", response_model=UserProfileRead)
def telegram_login(request: Request, response: Response, init_data: str = Header(..., alias="X-Telegram-Init-Data", min_length=1, max_length=16384), db: Session = Depends(get_db)):
    """Exchange signed Telegram initData for an account-bound server session.

    Telegram identity is accepted only when an existing user explicitly has that
    Telegram ID linked. Opening the Mini App alone never provisions or elevates an account.
    """
    _verify_request_origin(request)
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Вход через Telegram не настроен")
    try:
        identity = validate_telegram_init_data(
            init_data, settings.telegram_bot_token, settings.telegram_init_data_max_age_seconds
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Telegram initData не прошёл проверку") from exc
    user = db.scalar(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.grants).selectinload(RolePermissionGrant.permission))
        .where(User.telegram_user_id == identity["user_id"])
    )
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="Этот Telegram-аккаунт не привязан к пользователю BOTVEX")
    user.last_login_at = utcnow()
    token = create_session(db, user, request)
    db.commit()
    set_session_cookie(response, token, settings.session_ttl_seconds)
    return _profile(user)


@router.get("/me", response_model=UserProfileRead)
def me(user: User = Depends(get_current_user)):
    return _profile(user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    _verify_request_origin(request)
    raw = request.cookies.get(settings.session_cookie_name)
    if raw:
        row = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(raw)))
        if row is not None and row.revoked_at is None:
            row.revoked_at = utcnow()
            db.commit()
    clear_session_cookie(response)
    return {"ok": True}


@router.post("/change-password", response_model=UserProfileRead)
def change_password(payload: ChangePasswordRequest, request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _verify_request_origin(request)
    if not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(status_code=400, detail="Текущий пароль указан неверно")
    try:
        if password_hasher.verify(user.password_hash, payload.new_password):
            raise HTTPException(status_code=422, detail="Новый пароль должен отличаться от текущего")
    except VerifyMismatchError:
        pass
    except VerificationError:
        # The current hash has already been checked above; this is defensive only.
        raise HTTPException(status_code=400, detail="Не удалось проверить текущий пароль")

    now = utcnow()
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.failed_login_attempts = 0
    user.locked_until = None
    token = request.cookies.get(settings.session_cookie_name)
    current_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(token))) if token else None
    if current_session is None or current_session.revoked_at is not None or current_session.expires_at <= now:
        raise HTTPException(status_code=401, detail="Сессия истекла. Войди снова.")
    db.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.id != current_session.id, AuthSession.revoked_at.is_(None)).update({AuthSession.revoked_at: now}, synchronize_session=False)
    new_token = secrets.token_urlsafe(32)
    current_session.token_hash = token_digest(new_token)
    current_session.created_at = now
    current_session.expires_at = now + timedelta(seconds=settings.session_ttl_seconds)
    db.add(ActivityEvent(actor=user.username, entity_type="security", entity_id=user.id, action="password_changed", summary="Пароль аккаунта изменён"))
    db.commit()
    set_session_cookie(response, new_token, settings.session_ttl_seconds)
    return _profile(user)


def _role_read(role: Role) -> dict:
    return {
        "id": role.id,
        "slug": role.slug,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "is_active": role.is_active,
        "users_count": len(role.users),
        "permissions": {grant.permission.key: grant.scope for grant in role.grants},
    }


def _resolve_roles(db: Session, slugs: list[str], *, allow_privileged: bool = False) -> list[Role]:
    normalized = sorted(set(slug.strip().casefold() for slug in slugs))
    if not normalized:
        raise HTTPException(status_code=422, detail="Назначь хотя бы одну роль")
    roles = list(db.scalars(
        select(Role)
        .options(selectinload(Role.grants).selectinload(RolePermissionGrant.permission))
        .where(Role.slug.in_(normalized), Role.is_active.is_(True))
    ).all())
    if {role.slug for role in roles} != set(normalized):
        raise HTTPException(status_code=422, detail="Одна или несколько ролей не найдены или отключены")
    if any(role.slug == "client" for role in roles) and len(roles) > 1:
        raise HTTPException(status_code=422, detail="Клиентская роль несовместима с внутренними ролями сотрудников")
    if any(role.slug == "owner" for role in roles):
        raise HTTPException(status_code=403, detail="Роль владельца нельзя назначить через обычное управление аккаунтами")
    if not allow_privileged and any(not role.is_system for role in roles):
        raise HTTPException(status_code=403, detail="Пользовательские роли назначает только владелец")
    if not allow_privileged and any(
        OWNER_ONLY_PERMISSION_KEYS.intersection(grant.permission.key for grant in role.grants)
        for role in roles
    ):
        raise HTTPException(status_code=403, detail="Эту роль может назначить только владелец")
    return roles


def _assign_permissions(db: Session, role: Role, permissions: dict[str, str], *, allow_privileged: bool = False) -> None:
    keys = set(permissions)
    existing = set(db.scalars(select(Permission.key).where(Permission.key.in_(keys))).all()) if keys else set()
    unknown = keys - existing
    if unknown:
        raise HTTPException(status_code=422, detail=f"Неизвестные права: {', '.join(sorted(unknown))}")
    privileged = keys & OWNER_ONLY_PERMISSION_KEYS
    if privileged and not allow_privileged:
        raise HTTPException(status_code=403, detail="Административные, security- и внутренние права может делегировать только владелец")
    role.grants.clear()
    for key, scope in permissions.items():
        permission = db.scalar(select(Permission).where(Permission.key == key))
        if permission is not None:
            role.grants.append(RolePermissionGrant(permission=permission, scope=scope))


@admin_router.get("/users", response_model=AdminUserListRead)
def list_users(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
    _owner: AccessContext = Depends(require_permission("admin:users:view")),
    db: Session = Depends(get_db),
):
    query = select(User).options(selectinload(User.roles)).order_by(User.created_at.desc(), User.id.desc())
    count_query = select(func.count(User.id))
    if q and q.strip():
        pattern = f"%{q.strip()[:100]}%"
        query = query.where(User.username.ilike(pattern))
        count_query = count_query.where(User.username.ilike(pattern))
    return {
        "items": [_admin_user(item) for item in db.scalars(query.limit(limit).offset(offset)).all()],
        "total": db.scalar(count_query) or 0,
        "limit": limit,
        "offset": offset,
    }


@admin_router.post("/users", response_model=AdminUserCreateResult, status_code=201)
def create_user(
    payload: AdminUserCreate,
    _owner: AccessContext = Depends(require_permission("admin:users:create")),
    db: Session = Depends(get_db),
):
    username = payload.username.strip().casefold()
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise HTTPException(status_code=409, detail="Имя пользователя уже занято")
    roles = _resolve_roles(db, payload.role_slugs, allow_privileged=_owner.is_owner)
    has_client_role = any(role.slug == "client" for role in roles)
    if has_client_role and payload.customer_id is None:
        raise HTTPException(status_code=422, detail="Для клиентской роли необходимо привязать запись клиента")
    if payload.customer_id is not None and db.get(Client, payload.customer_id) is None:
        raise HTTPException(status_code=422, detail="Клиент не найден")
    if payload.telegram_user_id and db.scalar(select(User.id).where(User.telegram_user_id == payload.telegram_user_id)) is not None:
        raise HTTPException(status_code=409, detail="Этот Telegram ID уже привязан к другому аккаунту")

    temporary_password = secrets.token_urlsafe(18)
    user = User(
        username=username,
        password_hash=hash_password(temporary_password),
        is_active=True,
        is_owner=False,
        must_change_password=True,
        customer_id=payload.customer_id,
        telegram_user_id=payload.telegram_user_id,
        roles=roles,
    )
    db.add(user)
    db.flush()
    db.add(ActivityEvent(actor="owner", entity_type="user", entity_id=user.id, action="created", summary=f"Создан аккаунт {user.username}; временный пароль выдан однократно"))
    db.commit()
    db.refresh(user)
    return {
        "user": _admin_user(user),
        "temporary_password": temporary_password,
        "message": "Сохрани временный пароль сейчас: повторно он не показывается. При первом входе пользователь должен заменить его.",
    }


@admin_router.patch("/users/{user_id}", response_model=AdminUserRead)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    owner: AccessContext = Depends(require_permission("admin:users:edit")),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).options(selectinload(User.roles)).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    changes = payload.model_dump(exclude_unset=True)
    if user.is_owner and not owner.is_owner:
        raise HTTPException(status_code=403, detail="Аккаунт владельца может изменять только сам владелец")
    if user.is_owner:
        if changes.get("is_active") is False or "role_slugs" in changes or ("customer_id" in changes and changes["customer_id"] is not None):
            raise HTTPException(status_code=403, detail="Защищённый аккаунт владельца нельзя отключить или лишить роли через этот интерфейс")
    if "is_active" in changes and changes["is_active"] is not None and changes["is_active"] != user.is_active:
        if not owner.is_owner and (owner.user is None or _effective_permission_scope(owner.user, "admin:users:suspend") is None):
            raise HTTPException(status_code=403, detail="Отключение и активация аккаунтов требуют права admin:users:suspend")
    if changes.get("is_active") is False:
        if owner.user and owner.user.id == user.id:
            raise HTTPException(status_code=422, detail="Нельзя отключить собственный активный сеанс; используй отдельный аккаунт владельца")
        active_owners = db.scalar(select(func.count(User.id)).where(User.is_owner.is_(True), User.is_active.is_(True))) or 0
        if user.is_owner and active_owners <= 1:
            raise HTTPException(status_code=422, detail="Нельзя отключить последнего владельца")
        now = utcnow()
        db.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).update({AuthSession.revoked_at: now}, synchronize_session=False)
    if "role_slugs" in changes and changes["role_slugs"] is not None:
        user.roles = _resolve_roles(db, changes["role_slugs"], allow_privileged=owner.is_owner)
        if any(role.slug == "client" for role in user.roles) and user.customer_id is None and changes.get("customer_id") is None:
            raise HTTPException(status_code=422, detail="Для клиентской роли необходимо привязать запись клиента")
    if "telegram_user_id" in changes:
        telegram_user_id = changes["telegram_user_id"]
        if telegram_user_id and db.scalar(select(User.id).where(User.telegram_user_id == telegram_user_id, User.id != user.id)) is not None:
            raise HTTPException(status_code=409, detail="Этот Telegram ID уже привязан к другому аккаунту")
        user.telegram_user_id = telegram_user_id
    if "customer_id" in changes:
        new_customer_id = changes["customer_id"]
        if new_customer_id is not None and db.get(Client, new_customer_id) is None:
            raise HTTPException(status_code=422, detail="Клиент не найден")
        user.customer_id = new_customer_id
    if "is_active" in changes and changes["is_active"] is not None:
        user.is_active = changes["is_active"]
    db.add(ActivityEvent(actor=owner.user.username if owner.user else "owner", entity_type="user", entity_id=user.id, action="updated", summary=f"Изменены настройки аккаунта {user.username}"))
    db.commit()
    db.refresh(user)
    return _admin_user(user)


@admin_router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    owner: AccessContext = Depends(require_permission("admin:users:reset_password")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    if user.is_owner and not owner.is_owner:
        raise HTTPException(status_code=403, detail="Сброс пароля владельца доступен только владельцу")
    temporary_password = secrets.token_urlsafe(18)
    user.password_hash = hash_password(temporary_password)
    user.must_change_password = True
    user.failed_login_attempts = 0
    user.locked_until = None
    now = utcnow()
    db.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).update({AuthSession.revoked_at: now}, synchronize_session=False)
    db.add(ActivityEvent(actor=owner.user.username if owner.user else "owner", entity_type="security", entity_id=user.id, action="password_reset", summary=f"Владелец сбросил пароль аккаунта {user.username}"))
    db.commit()
    return {"user_id": user.id, "username": user.username, "temporary_password": temporary_password, "message": "Пароль показан один раз; при входе его необходимо заменить."}


@admin_router.get("/users/{user_id}/sessions", response_model=AdminSessionListRead)
def list_user_sessions(
    user_id: int,
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
    access: AccessContext = Depends(require_permission("admin:users:sessions")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    if user.is_owner and not access.is_owner:
        raise HTTPException(status_code=403, detail="Сессии владельца может просматривать только владелец")
    base = select(AuthSession).where(AuthSession.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(AuthSession.created_at.desc(), AuthSession.id.desc()).limit(limit).offset(offset)).all()
    now = utcnow()
    raw_token = request.cookies.get(settings.session_cookie_name)
    current_digest = token_digest(raw_token) if raw_token else None
    return {
        "items": [{
            "id": row.id,
            "created_at": row.created_at,
            "expires_at": row.expires_at,
            "revoked_at": row.revoked_at,
            "user_agent": row.user_agent,
            "is_active": row.revoked_at is None and row.expires_at > now and user.is_active,
            "is_current": bool(current_digest and row.token_hash == current_digest),
        } for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@admin_router.post("/users/{user_id}/sessions/{session_id}/revoke")
def revoke_user_session(
    user_id: int,
    session_id: int,
    request: Request,
    access: AccessContext = Depends(require_permission("admin:users:sessions")),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    if user.is_owner and not access.is_owner:
        raise HTTPException(status_code=403, detail="Сессии владельца может отзывать только владелец")
    row = db.scalar(select(AuthSession).where(AuthSession.id == session_id, AuthSession.user_id == user_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    current_token = request.cookies.get(settings.session_cookie_name)
    if access.user and access.user.id == user_id and current_token and row.token_hash == token_digest(current_token):
        raise HTTPException(status_code=409, detail="Нельзя отозвать текущую сессию из этого же окна. Используй выход из аккаунта.")
    if row.revoked_at is not None or row.expires_at <= utcnow():
        raise HTTPException(status_code=409, detail="Сессия уже не активна")
    row.revoked_at = utcnow()
    actor_name = access.user.username if access.user else "owner"
    db.add(ActivityEvent(actor=actor_name, entity_type="security", entity_id=user.id, action="session_revoked", summary=f"Отозвана сессия аккаунта {user.username} (session #{row.id})"))
    db.commit()
    return {"ok": True, "user_id": user.id, "session_id": row.id, "revoked_at": row.revoked_at}


@admin_router.get("/permissions")
def list_permission_catalog(_owner: AccessContext = Depends(require_permission("admin:roles:view")), db: Session = Depends(get_db)):
    """Return the allowlisted permission catalog for the owner role editor."""
    return [
        {"key": permission.key, "description": permission.description}
        for permission in db.scalars(select(Permission).order_by(Permission.key)).all()
    ]


@admin_router.get("/roles", response_model=list[RoleRead])
def list_roles(_owner: AccessContext = Depends(require_permission("admin:roles:view")), db: Session = Depends(get_db)):
    roles = db.scalars(select(Role).options(selectinload(Role.grants).selectinload(RolePermissionGrant.permission), selectinload(Role.users)).order_by(Role.is_system.desc(), Role.name)).all()
    return [_role_read(role) for role in roles]


@admin_router.post("/roles", response_model=RoleRead, status_code=201)
def create_role(payload: RoleCreate, owner: AccessContext = Depends(require_permission("admin:roles:create")), db: Session = Depends(get_db)):
    slug = payload.slug.casefold()
    if db.scalar(select(Role.id).where(Role.slug == slug)) is not None:
        raise HTTPException(status_code=409, detail="Роль с таким идентификатором уже существует")
    role = Role(slug=slug, name=payload.name.strip(), description=payload.description, is_system=False, is_active=True)
    db.add(role)
    db.flush()
    _assign_permissions(db, role, payload.permissions, allow_privileged=owner.is_owner)
    db.add(ActivityEvent(actor=owner.user.username if owner.user else "owner", entity_type="role", entity_id=role.id, action="created", summary=f"Создана роль {role.name}"))
    db.commit()
    role = db.scalar(select(Role).options(selectinload(Role.grants).selectinload(RolePermissionGrant.permission), selectinload(Role.users)).where(Role.id == role.id))
    return _role_read(role)


@admin_router.patch("/roles/{role_id}", response_model=RoleRead)
def update_role(role_id: int, payload: RoleUpdate, owner: AccessContext = Depends(require_permission("admin:roles:edit")), db: Session = Depends(get_db)):
    role = db.scalar(select(Role).options(selectinload(Role.grants).selectinload(RolePermissionGrant.permission), selectinload(Role.users)).where(Role.id == role_id))
    if role is None:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    if role.slug == "owner":
        raise HTTPException(status_code=403, detail="Права владельца нельзя изменить через матрицу ролей")
    changes = payload.model_dump(exclude_unset=True)
    if role.is_system and ("permissions" in changes or changes.get("is_active") is False):
        raise HTTPException(status_code=403, detail="Системную роль нельзя отключить или изменить набор её прав")
    if changes.get("name") is not None:
        role.name = changes["name"].strip()
    if "description" in changes:
        role.description = changes["description"]
    if changes.get("is_active") is not None:
        role.is_active = changes["is_active"]
    if "permissions" in changes and changes["permissions"] is not None:
        _assign_permissions(db, role, changes["permissions"], allow_privileged=owner.is_owner)
    db.add(ActivityEvent(actor=owner.user.username if owner.user else "owner", entity_type="role", entity_id=role.id, action="updated", summary=f"Изменена роль {role.name}"))
    db.commit()
    role = db.scalar(select(Role).options(selectinload(Role.grants).selectinload(RolePermissionGrant.permission), selectinload(Role.users)).where(Role.id == role.id))
    return _role_read(role)


@admin_router.get("/projects/{project_id}/members", response_model=list[ProjectAssignmentRead])
def list_project_members(project_id: int, _owner: AccessContext = Depends(require_permission("projects:assign")), db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Проект не найден")
    rows = db.scalars(select(ProjectAssignment).options(selectinload(ProjectAssignment.user)).where(ProjectAssignment.project_id == project_id).order_by(ProjectAssignment.created_at)).all()
    return [{"id": row.id, "project_id": row.project_id, "user_id": row.user_id, "username": row.user.username, "created_at": row.created_at} for row in rows]


@admin_router.post("/projects/{project_id}/members", response_model=ProjectAssignmentRead, status_code=201)
def assign_project_member(project_id: int, payload: ProjectAssignmentCreate, owner: AccessContext = Depends(require_permission("projects:assign")), db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Проект не найден")
    user = db.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=422, detail="Аккаунт не найден или отключён")
    existing = db.scalar(select(ProjectAssignment).where(ProjectAssignment.project_id == project_id, ProjectAssignment.user_id == user.id))
    if existing:
        raise HTTPException(status_code=409, detail="Пользователь уже назначен на этот проект")
    row = ProjectAssignment(project_id=project_id, user_id=user.id, assigned_by_user_id=owner.user.id if owner.user else None)
    db.add(row)
    db.add(ActivityEvent(actor=owner.user.username if owner.user else "owner", entity_type="project_assignment", entity_id=project_id, action="created", summary=f"Пользователь {user.username} назначен на проект #{project_id}"))
    db.commit()
    return {"id": row.id, "project_id": row.project_id, "user_id": row.user_id, "username": user.username, "created_at": row.created_at}


@admin_router.delete("/projects/{project_id}/members/{user_id}")
def unassign_project_member(project_id: int, user_id: int, owner: AccessContext = Depends(require_permission("projects:assign")), db: Session = Depends(get_db)):
    row = db.scalar(select(ProjectAssignment).where(ProjectAssignment.project_id == project_id, ProjectAssignment.user_id == user_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Назначение не найдено")
    user = db.get(User, user_id)
    db.delete(row)
    db.add(ActivityEvent(actor=owner.user.username if owner.user else "owner", entity_type="project_assignment", entity_id=project_id, action="deleted", summary=f"Пользователь {user.username if user else user_id} снят с проекта #{project_id}"))
    db.commit()
    return {"ok": True}
