"""Shared fixtures.

DB tests run against an ISOLATED test database (`<db>_test`), created and
migrated once per session and truncated after every test — so tests never
pollute the real vault index and never interfere with one another. The whole DB
tier skips cleanly when no Postgres is reachable, keeping the offline tier green
with no database (CLAUDE.md test tiers).
"""
from __future__ import annotations

import psycopg
import pytest

from living_brain import db as dbmod
from living_brain.config import Config

_TABLES = (
    "candidate_link", "entity_mention", "entity_version", "entity_alias",
    "chunk", "entity", "episode", "ontology_type",
)


@pytest.fixture(scope="session")
def cfg() -> Config:
    return Config.load()


def _split_url(url: str) -> tuple[str, str]:
    """Return (prefix, dbname) so we can address a sibling database."""
    prefix, _, name = url.rpartition("/")
    # strip any ?query on the db name
    name = name.split("?", 1)[0]
    return prefix, name


def _server_reachable(url: str) -> bool:
    try:
        with psycopg.connect(url, connect_timeout=2):
            return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def test_db_url(cfg: Config) -> str:
    """Create (if needed) and migrate an isolated <db>_test database."""
    prefix, name = _split_url(cfg.database_url)
    admin_url = f"{prefix}/{name}"          # the app db acts as maintenance db
    test_name = f"{name}_test"
    test_url = f"{prefix}/{test_name}"
    if not _server_reachable(admin_url):
        pytest.skip("no database — run `make db-local && make migrate` (or set DATABASE_URL)")
    # CREATE DATABASE cannot run inside a transaction; use autocommit.
    with psycopg.connect(admin_url, autocommit=True) as admin:
        with admin.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (test_name,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{test_name}"')
    with psycopg.connect(test_url) as conn:
        dbmod.apply_migrations(conn)
    return test_url


@pytest.fixture
def db_conn(test_db_url: str):
    """A connection to the isolated, migrated test DB. Truncated after each test."""
    conn = psycopg.connect(test_db_url)
    try:
        yield conn
    finally:
        try:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(
                    f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"
                )
            conn.commit()
        finally:
            conn.close()


@pytest.fixture
def embedder(cfg: Config):
    """A live Ollama embedder. Skips if Ollama isn't reachable / model missing."""
    from living_brain.embedding import Embedder

    e = Embedder(cfg)
    try:
        e.embed("probe")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no Ollama embeddings available: {exc}")
    return e
