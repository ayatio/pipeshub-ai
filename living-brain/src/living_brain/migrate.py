"""File-based migration runner. Applies migrations/*.sql in lexical order once."""
from __future__ import annotations

from pathlib import Path

from .config import PROJECT_ROOT
from .db import Database

MIGRATIONS_DIR = PROJECT_ROOT / "migrations"

_TRACKING = """
CREATE TABLE IF NOT EXISTS _migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


def _applied(db: Database) -> set[str]:
    db.executescript(_TRACKING)
    rows = db.query("SELECT name FROM _migrations")
    return {r["name"] for r in rows}


def pending(db: Database) -> list[Path]:
    done = _applied(db)
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [f for f in files if f.name not in done]


def run_migrations(url: str | None = None) -> list[str]:
    applied: list[str] = []
    with Database(url) as db:
        for path in pending(db):
            sql = path.read_text(encoding="utf-8")
            db.executescript(sql)
            db.execute(
                "INSERT INTO _migrations (name, applied_at) VALUES (?, datetime('now'))"
                if db.is_sqlite
                else "INSERT INTO _migrations (name, applied_at) VALUES (?, now())",
                (path.name,),
            )
            db.commit()
            applied.append(path.name)
    return applied
