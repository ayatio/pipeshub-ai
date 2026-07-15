"""SQLite access and a tiny forward-only migration runner."""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def connect(db_path: str) -> sqlite3.Connection:
    """Open (and create the parent dir for) a SQLite database."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def ensure_db(db_path: str) -> None:
    """`make db` — create the database file and the migrations bookkeeping table."""
    conn = connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _applied_versions(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {r["version"] for r in rows}


def migrate(db_path: str, migrations_dir: Path | None = None) -> list[str]:
    """`make migrate` — apply every *.sql migration not yet recorded, in order.

    Returns the list of newly applied version identifiers.
    """
    from .util import now_iso  # local import avoids a cycle at module load

    ensure_db(db_path)
    mdir = migrations_dir or MIGRATIONS_DIR
    files = sorted(mdir.glob("*.sql"))
    conn = connect(db_path)
    applied: list[str] = []
    try:
        done = _applied_versions(conn)
        for f in files:
            version = f.stem
            if version in done:
                continue
            sql = f.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, now_iso()),
            )
            conn.commit()
            applied.append(version)
    finally:
        conn.close()
    return applied


def migration_status(db_path: str, migrations_dir: Path | None = None) -> list[tuple[str, bool]]:
    mdir = migrations_dir or MIGRATIONS_DIR
    files = sorted(mdir.glob("*.sql"))
    ensure_db(db_path)
    conn = connect(db_path)
    try:
        done = _applied_versions(conn)
    finally:
        conn.close()
    return [(f.stem, f.stem in done) for f in files]
