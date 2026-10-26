"""Explicit, one-time CLI recovery for an existing owner account.

Run only with the backend stopped and direct access to the intended database.
The recovery password is read from OWNER_RECOVERY_PASSWORD, never command-line args.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .auth import hash_password
from .database import SessionLocal
from .models import ActivityEvent, AuthSession, User, utcnow


def recover_owner_password(db: Session, username: str, password: str) -> bool:
    normalized = username.strip().casefold()
    if not normalized or re.fullmatch(r"[a-z0-9_.-]{1,100}", normalized) is None:
        raise RuntimeError("Некорректное имя владельца")
    if len(password) < 12:
        raise RuntimeError("Для восстановления требуется временный пароль длиной не менее 12 символов")
    owner = db.scalar(select(User).where(User.username == normalized, User.is_owner.is_(True)))
    if owner is None:
        raise RuntimeError("Существующий аккаунт владельца не найден; восстановление не создаёт новые аккаунты")

    now = utcnow()
    owner.password_hash = hash_password(password)
    owner.must_change_password = True
    owner.failed_login_attempts = 0
    owner.locked_until = None
    db.execute(update(AuthSession).where(AuthSession.user_id == owner.id, AuthSession.revoked_at.is_(None)).values(revoked_at=now))
    db.add(ActivityEvent(
        actor="owner-recovery-cli",
        entity_type="security",
        entity_id=owner.id,
        action="owner_password_recovered",
        summary="Пароль существующего владельца восстановлен через локальную CLI; требуется сменить его после входа",
    ))
    db.commit()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="One-time recovery of an existing BOTVEX owner account")
    parser.add_argument("--confirm", action="store_true", help="Confirm that the backend is stopped and the intended database is selected")
    parser.add_argument("--username", default=os.getenv("OWNER_RECOVERY_USERNAME", "lshpek"))
    args = parser.parse_args()
    if not args.confirm:
        parser.error("pass --confirm only after stopping the backend and checking DATABASE_URL")
    password = os.getenv("OWNER_RECOVERY_PASSWORD", "")
    if not password:
        print("ERROR: set OWNER_RECOVERY_PASSWORD in the environment for this command only.", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        try:
            recover_owner_password(db, args.username, password)
        except RuntimeError as exc:
            db.rollback()
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    print(f"Recovered the existing owner account '{args.username}'. The next sign-in requires a password change.")
    print("Remove OWNER_RECOVERY_PASSWORD from the environment before restarting the backend.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
