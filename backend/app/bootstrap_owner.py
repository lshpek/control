"""One-time owner bootstrap. Never runs automatically during application startup.

Run after `alembic upgrade head` with BOOTSTRAP_OWNER_PASSWORD supplied through
an untracked environment variable. Existing users are never reset or replaced.
"""
from __future__ import annotations

import os
import re
import sys
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import settings
from .database import SessionLocal
from .models import ActivityEvent, Permission, Role, RolePermissionGrant, User

PERMISSIONS: dict[str, str] = {
    "dashboard:view": "View the operational dashboard",
    "clients:view": "View customer and lead records",
    "clients:create": "Create customer and lead records",
    "clients:edit": "Edit customer and lead records",
    "clients:archive": "Archive customer and lead records",
    "clients:restore": "Restore archived clients",
    "projects:view": "View projects",
    "projects:create": "Create projects",
    "projects:edit": "Edit projects",
    "projects:archive": "Archive projects",
    "projects:restore": "Restore archived projects",
    "projects:assign": "Assign team members to projects",
    "tasks:view": "View tasks",
    "tasks:create": "Create tasks",
    "tasks:edit": "Edit tasks",
    "tasks:archive": "Archive tasks",
    "tasks:restore": "Restore archived tasks",
    "services:view": "View service records",
    "services:create": "Create service records",
    "services:edit": "Edit service records",
    "services:archive": "Archive service records",
    "services:restore": "Restore archived services",
    "logs:view": "View manual log records",
    "logs:create": "Create manual log records",
    "logs:edit": "Edit manual log records",
    "logs:archive": "Archive manual log records",
    "logs:restore": "Restore archived logs",
    "test_suites:view": "View test-suite records",
    "test_suites:create": "Create test-suite records and manual runs",
    "test_suites:edit": "Edit test-suite records",
    "deployments:view": "View manual deployment records",
    "deployments:create": "Create manual deployment records",
    "deployments:edit": "Edit manual deployment records",
    "activity:view": "View business activity history",
    "settings:view": "View application settings",
    "settings:edit": "Edit application settings",
    "orders:view": "View order records permitted by scope",
    "orders:create": "Create orders",
    "orders:edit": "Edit order details",
    "orders:archive": "Archive orders without deleting history",
    "orders:restore": "Restore archived orders",
    "orders:view_internal": "View internal order notes and operational context",
    "orders:transition": "Change order lifecycle status",
    "orders:messages:view": "View order conversations",
    "orders:messages:create": "Post messages to order conversations",
    "orders:messages:internal": "View and post internal-only order messages",
    "portal:orders:view": "Access own customer orders in the portal",
    "portal:messages:view": "View customer-visible order messages",
    "portal:messages:create": "Send messages about own orders",
    "admin:users:view": "View user accounts",
    "admin:users:create": "Create user accounts and issue temporary credentials",
    "admin:users:edit": "Edit user account roles and access",
    "admin:users:suspend": "Suspend and reactivate user accounts",
    "admin:users:reset_password": "Reset user passwords",
    "admin:users:sessions": "Inspect and revoke user sessions",
    "admin:roles:view": "View roles and their permissions",
    "admin:roles:create": "Create custom roles",
    "admin:roles:edit": "Edit custom roles",
}

# Only the owner may delegate account-administration, role-management, settings,
# or internal operational permissions through custom roles. This prevents an
# administrator from elevating another account by assigning a crafted role.
OWNER_ONLY_PERMISSION_KEYS = frozenset(
    key for key in PERMISSIONS if key.startswith("admin:")
) | frozenset({"settings:view", "settings:edit"})

DEFAULT_ROLES: dict[str, dict] = {
    "owner": {"name": "Owner", "description": "Полный доступ владельца", "system": True, "permissions": "all"},
    "administrator": {"name": "Administrator", "description": "Широкое управление операциями без права изменить владельца", "system": True, "permissions": "admin"},
    "manager": {"name": "Manager", "description": "CRM, проекты, задачи и заказы в назначенной области", "system": True, "permissions": "manager"},
    "developer": {"name": "Developer", "description": "Назначенные проекты, задачи и технические записи", "system": True, "permissions": "developer"},
    "client": {"name": "Client", "description": "Только собственные заказы и клиентская переписка", "system": True, "permissions": "client"},
    "observer": {"name": "Observer", "description": "Только чтение назначенных записей", "system": True, "permissions": "observer"},
}


def _role_permissions(role_slug: str) -> dict[str, str]:
    if role_slug == "owner":
        return {key: "all" for key in PERMISSIONS}
    if role_slug == "administrator":
        return {
            **{f"{resource}:{action}": "all" for resource, actions in {
                "dashboard": ["view"], "clients": ["view", "create", "edit", "archive", "restore"],
                "projects": ["view", "create", "edit", "archive", "restore", "assign"],
                "tasks": ["view", "create", "edit", "archive", "restore"],
                "services": ["view", "create", "edit", "archive", "restore"],
                "logs": ["view", "create", "edit", "archive", "restore"],
                "test_suites": ["view", "create", "edit"],
                "deployments": ["view", "create", "edit"],
                "activity": ["view"], "orders": ["view", "create", "edit", "archive", "restore", "transition", "view_internal", "messages:view", "messages:create", "messages:internal"],
                "admin": [],
            }.items() for action in actions}
            | {f"admin:users:{action}": "all" for action in ["view", "create", "edit"]}
            | {"admin:roles:view": "all"}
        }
    if role_slug == "manager":
        grants = {f"{resource}:{action}": "all" for resource, actions in {
            "dashboard": ["view"], "clients": ["view", "create", "edit", "archive", "restore"],
            "projects": ["view", "create", "edit", "archive", "restore", "assign"],
            "tasks": ["view", "create", "edit", "archive", "restore"],
            "services": ["view", "create", "edit"], "activity": ["view"],
            "orders": ["view", "create", "edit", "archive", "restore", "transition", "view_internal", "messages:view", "messages:create", "messages:internal"],
            "test_suites": ["view", "create", "edit"], "deployments": ["view", "create", "edit"],
        }.items() for action in actions}
        return grants
    if role_slug == "developer":
        return {key: "assigned" for key in [
            "projects:view", "tasks:view", "tasks:create", "tasks:edit",
            "services:view", "test_suites:view", "test_suites:create", "test_suites:edit",
            "deployments:view", "deployments:create", "deployments:edit",
        ]} | {"orders:view": "assigned", "orders:view_internal": "assigned", "orders:messages:view": "assigned", "orders:messages:create": "assigned", "orders:messages:internal": "assigned"}
    if role_slug == "client":
        return {key: "own_customer" for key in ["portal:orders:view", "portal:messages:view", "portal:messages:create"]}
    if role_slug == "observer":
        return {key: "assigned" for key in ["projects:view", "tasks:view", "services:view", "test_suites:view", "deployments:view", "orders:view", "orders:messages:view"]}
    return {}


def seed_authorization(db: Session) -> None:
    for key, description in PERMISSIONS.items():
        if db.scalar(select(Permission.id).where(Permission.key == key)) is None:
            db.add(Permission(key=key, description=description))
    db.flush()
    for slug, meta in DEFAULT_ROLES.items():
        role = db.scalar(select(Role).where(Role.slug == slug))
        if role is None:
            role = Role(slug=slug, name=meta["name"], description=meta["description"], is_system=meta["system"], is_active=True)
            db.add(role)
            db.flush()
        # Seeding can run more than once as the built-in permission catalogue grows.
        # Preserve any existing scope (including intentional customisation), while
        # adding newly introduced grants that a system role is missing.
        existing_keys = {grant.permission.key for grant in role.grants}
        for key, scope in _role_permissions(slug).items():
            if key in existing_keys:
                continue
            permission = db.scalar(select(Permission).where(Permission.key == key))
            if permission is not None:
                role.grants.append(RolePermissionGrant(permission=permission, scope=scope))
                existing_keys.add(key)
    db.flush()


def bootstrap_owner(db: Session, username: str, password: str) -> User:
    if db.scalar(select(User.id).limit(1)) is not None:
        raise RuntimeError("Пользователи уже существуют. Bootstrap прекращён без изменения существующих аккаунтов.")
    if not username or re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", username) is None:
        raise RuntimeError("Имя владельца должно содержать только буквы, цифры, точку, дефис или подчёркивание.")
    if not password:
        raise RuntimeError("BOOTSTRAP_OWNER_PASSWORD не задан. Передай временный пароль через окружение.")
    seed_authorization(db)
    role = db.scalar(select(Role).where(Role.slug == "owner"))
    if role is None:
        raise RuntimeError("Не удалось создать системную роль владельца.")
    user = User(
        username=username.strip().casefold(),
        password_hash=hash_password(password),
        is_active=True,
        is_owner=True,
        must_change_password=True,
        roles=[role],
    )
    db.add(user)
    db.add(ActivityEvent(actor="bootstrap", entity_type="security", action="owner_bootstrapped", summary="Выполнена первичная настройка владельца; временный пароль требуется заменить"))
    db.commit()
    db.refresh(user)
    return user


def main() -> int:
    password = settings.bootstrap_owner_password
    username = settings.bootstrap_owner_username or "lshpek"
    if not password:
        print("ОШИБКА: задай BOOTSTRAP_OWNER_PASSWORD только для этой команды.", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        try:
            user = bootstrap_owner(db, username, password)
        except RuntimeError as exc:
            db.rollback()
            print(f"ОШИБКА: {exc}", file=sys.stderr)
            return 2
    print(f"Создан владелец {user.username}. При первом входе необходимо заменить временный пароль.")
    print("Удали BOOTSTRAP_OWNER_PASSWORD из окружения перед обычным запуском приложения.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
