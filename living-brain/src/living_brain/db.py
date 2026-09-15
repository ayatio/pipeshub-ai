"""Database access (psycopg 3). Explicit SQL, no ORM.

The DB is a derived index (BUILD-BRIEF §1.1): it can be dropped and rebuilt from
the vault. This module owns connections, migration application, and the health
check.
"""
from __future__ import annotations

from pathlib import Path

import psycopg

from .config import Config

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def connect(cfg: Config | None = None) -> psycopg.Connection:
    """Open a new connection. Caller owns the lifecycle (use as a context manager)."""
    cfg = cfg or Config.load()
    return psycopg.connect(cfg.database_url)


def apply_migrations(conn: psycopg.Connection) -> list[str]:
    """Apply every migrations/*.sql in filename order. Returns the files applied.

    Migrations are written idempotently (CREATE ... IF NOT EXISTS), so this is
    safe to re-run.
    """
    applied: list[str] = []
    files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    with conn.cursor() as cur:
        for f in files:
            cur.execute(f.read_text(encoding="utf-8"))
            applied.append(f.name)
    conn.commit()
    return applied


_EXPECTED_TABLES = {
    "episode", "chunk", "entity", "entity_alias", "entity_version",
    "entity_mention", "candidate_link", "ontology_type",
}


def health(conn: psycopg.Connection) -> dict[str, object]:
    """Report pgvector presence and which expected tables exist."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        has_vector = cur.fetchone() is not None
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
        has_trgm = cur.fetchone() is not None
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        )
        present = {r[0] for r in cur.fetchall()}
    missing = sorted(_EXPECTED_TABLES - present)
    return {
        "pgvector": has_vector,
        "pg_trgm": has_trgm,
        "tables_present": sorted(_EXPECTED_TABLES & present),
        "tables_missing": missing,
        "ok": has_vector and has_trgm and not missing,
    }
