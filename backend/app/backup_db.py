"""Hot SQLite backup utility with integrity verification and security audit logging."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .config import settings
from .database import SessionLocal
from .models import ActivityEvent


def _sqlite_file_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise RuntimeError("Горячее резервное копирование через sqlite3.backup поддерживается только для файловой БД SQLite")
    raw_path = unquote(urlsplit(database_url).path)
    if database_url.startswith("sqlite:///./") or not database_url.startswith("sqlite:////"):
        raw_path = database_url[len("sqlite:///"):]
    return Path(raw_path).resolve()


def backup_sqlite_database(output_path: Path, database_url: str | None = None) -> Path:
    source_path = _sqlite_file_from_url(database_url or settings.database_url)
    if not source_path.exists():
        raise RuntimeError(f"Исходный файл базы данных не найден: {source_path}")
    target_path = output_path.resolve()
    if target_path == source_path:
        raise RuntimeError("Целевой путь резервной копии не должен совпадать с рабочей базой данных")
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(source_path)) as src_conn:
        with sqlite3.connect(str(target_path)) as dst_conn:
            src_conn.backup(dst_conn)

    with sqlite3.connect(str(target_path)) as verify_conn:
        row = verify_conn.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != "ok":
            raise RuntimeError(f"Проверка целостности резервной копии завершилась ошибкой: {row}")

    with SessionLocal() as db:
        db.add(ActivityEvent(
            actor="backup-cli",
            entity_type="security",
            action="database_backup",
            summary=f"Создана и проверена резервная копия БД ({target_path.name}, PRAGMA integrity_check=ok)",
        ))
        db.commit()
    return target_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a verified hot backup of the BOTVEX SQLite database")
    parser.add_argument("--output", required=True, help="Destination path for the SQLite backup file")
    args = parser.parse_args()
    try:
        dest = backup_sqlite_database(Path(args.output))
    except RuntimeError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 2
    print(f"[BOTVEX-BACKUP] Резервная копия успешно создана и верифицирована: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
