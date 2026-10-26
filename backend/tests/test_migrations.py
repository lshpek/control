"""Run Alembic on an isolated database and compare the result with ORM metadata."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app import models  # noqa: F401 — ensure all mapped tables are registered
from app.database import Base


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _alembic(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["PYTHONPATH"] = str(REPOSITORY_ROOT / "backend")
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", *arguments],
        cwd=REPOSITORY_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def test_migrations_are_reversible_and_create_current_table_columns(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration-check.db'}"
    for command in (
        ("upgrade", "head"),
        ("downgrade", "-1"),
        ("upgrade", "head"),
    ):
        result = _alembic(database_url, *command)
        assert result.returncode == 0, (
            f"alembic {' '.join(command)} failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        actual_tables = set(inspector.get_table_names()) - {"alembic_version"}
        expected_tables = set(Base.metadata.tables)
        assert actual_tables == expected_tables, (
            f"table mismatch: missing={sorted(expected_tables - actual_tables)}, "
            f"extra={sorted(actual_tables - expected_tables)}"
        )
        for table_name, table in Base.metadata.tables.items():
            actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
            expected_columns = {column.name for column in table.columns}
            assert actual_columns == expected_columns, (
                f"column mismatch for {table_name}: missing={sorted(expected_columns - actual_columns)}, "
                f"extra={sorted(actual_columns - expected_columns)}"
            )

            expected_foreign_keys = {
                tuple(sorted((element.parent.name, element.column.table.name, element.column.name) for element in constraint.elements))
                for constraint in table.foreign_key_constraints
            }
            actual_foreign_keys = {
                tuple(sorted((column, foreign_key["referred_table"], referred_column)
                             for column, referred_column in zip(foreign_key.get("constrained_columns") or [], foreign_key.get("referred_columns") or [])))
                for foreign_key in inspector.get_foreign_keys(table_name)
            }
            assert actual_foreign_keys == expected_foreign_keys, (
                f"foreign-key mismatch for {table_name}: missing={sorted(expected_foreign_keys - actual_foreign_keys)}, "
                f"extra={sorted(actual_foreign_keys - expected_foreign_keys)}"
            )

            expected_unique = {
                tuple(sorted(index.columns.keys())) for index in table.indexes if index.unique
            } | {
                tuple(sorted(column.name for column in constraint.columns))
                for constraint in table.constraints if constraint.__class__.__name__ == "UniqueConstraint"
            }
            actual_unique = {
                tuple(sorted(constraint.get("column_names") or []))
                for constraint in inspector.get_unique_constraints(table_name)
            } | {
                tuple(sorted(index.get("column_names") or []))
                for index in inspector.get_indexes(table_name) if index.get("unique")
            }
            assert actual_unique == expected_unique, (
                f"unique-constraint mismatch for {table_name}: missing={sorted(expected_unique - actual_unique)}, "
                f"extra={sorted(actual_unique - expected_unique)}"
            )

            expected_index_columns = {tuple(sorted(index.columns.keys())) for index in table.indexes}
            actual_index_columns = {
                tuple(sorted(index.get("column_names") or []))
                for index in inspector.get_indexes(table_name)
            }
            assert actual_index_columns == expected_index_columns, (
                f"index mismatch for {table_name}: missing={sorted(expected_index_columns - actual_index_columns)}, "
                f"extra={sorted(actual_index_columns - expected_index_columns)}"
            )
    finally:
        engine.dispose()
