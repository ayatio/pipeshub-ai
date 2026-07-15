"""Database access. SQLite by default; optional Postgres via psycopg.

The rest of the codebase talks to a tiny abstraction so night/memory logic does
not care which backend is in use. SQL uses the widely-portable subset; the one
dialect difference we need (autoincrement PK, placeholder style) is handled here.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from .config import CONFIG, PROJECT_ROOT


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:")


def sqlite_path(url: str) -> Path:
    # sqlite:///relative/path.db  or  sqlite:////absolute/path.db
    raw = url[len("sqlite://") :]
    if raw.startswith("/"):
        raw = raw[1:]
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


class Database:
    """Thin wrapper exposing execute/executemany/query with a uniform '?' style."""

    def __init__(self, url: str | None = None) -> None:
        self.url = url or CONFIG.database_url
        self.is_sqlite = _is_sqlite(self.url)
        self._conn = self._connect()

    def _connect(self):
        if self.is_sqlite:
            path = sqlite_path(self.url)
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            return conn
        try:
            import psycopg  # type: ignore
        except ImportError as exc:  # pragma: no cover - clear operator message
            raise RuntimeError(
                "Postgres URL configured but psycopg is not installed. "
                "Run: uv sync --extra postgres"
            ) from exc
        parsed = urlparse(self.url)
        return psycopg.connect(self.url)  # noqa: PGH-connect

    # -- helpers ------------------------------------------------------------
    def _translate(self, sql: str) -> str:
        """SQLite uses '?' placeholders; psycopg uses '%s'."""
        if self.is_sqlite:
            return sql
        return sql.replace("?", "%s")

    def execute(self, sql: str, params: Iterable[Any] = ()) -> Any:
        cur = self._conn.cursor()
        cur.execute(self._translate(sql), tuple(params))
        return cur

    def executescript(self, script: str) -> None:
        if self.is_sqlite:
            self._conn.executescript(script)
        else:
            with self._conn.cursor() as cur:
                cur.execute(script)

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        cur = self.execute(sql, params)
        rows = cur.fetchall()
        if self.is_sqlite:
            return [dict(r) for r in rows]
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in rows]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc: Any) -> None:
        if exc[0] is None:
            self.commit()
        self.close()


def init_db(url: str | None = None) -> str:
    """Ensure the database file/dir exists. Returns a human description."""
    db = Database(url)
    try:
        if db.is_sqlite:
            db.execute("SELECT 1")
            return f"SQLite ready at {sqlite_path(db.url)}"
        db.execute("SELECT 1")
        return f"Postgres connection ok: {db.url}"
    finally:
        db.commit()
        db.close()
