"""Shared fixtures. DB tests skip cleanly when no Postgres is reachable, so the
offline tier stays green with no database (CLAUDE.md test tiers)."""
from __future__ import annotations

import psycopg
import pytest

from living_brain import db as dbmod
from living_brain.config import Config


@pytest.fixture(scope="session")
def cfg() -> Config:
    return Config.load()


def _db_available(cfg: Config) -> bool:
    try:
        with psycopg.connect(cfg.database_url, connect_timeout=2):
            return True
    except Exception:
        return False


@pytest.fixture
def db_conn(cfg: Config):
    """A connection to a migrated DB. Skips if unreachable.

    Cleanup deletes any episode whose source starts with 'test://' (chunks,
    versions, mentions cascade), so tests never leave residue and never touch
    real captures.
    """
    if not _db_available(cfg):
        pytest.skip("no database — run `make db && make migrate` (or set DATABASE_URL)")
    conn = dbmod.connect(cfg)
    dbmod.apply_migrations(conn)  # idempotent
    try:
        yield conn
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM episode WHERE source LIKE 'test://%'")
            conn.commit()
        finally:
            conn.close()
