"""Database connection abstraction over SQLite (default) and Postgres/pgvector.

Both backends expose the same tiny interface used by the store:
  - ``connect()``     -> a DB-API connection with autocommit-ish semantics
  - ``dialect``       -> "sqlite" | "postgres"
  - parameter style is normalised to ``?`` placeholders; the Postgres path
    rewrites them to ``%s`` transparently.
"""
from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from .config import get_settings


def dialect() -> str:
    return "postgres" if get_settings().is_postgres else "sqlite"


def _sqlite_path() -> Path:
    url = get_settings().database_url
    # sqlite:///./data/living_brain.db  ->  ./data/living_brain.db
    raw = url.split("sqlite:///", 1)[-1]
    return Path(raw).expanduser()


class Cursor:
    """Thin wrapper so callers always use ``?`` placeholders."""

    def __init__(self, raw, dial: str):
        self._raw = raw
        self._dial = dial

    def execute(self, sql: str, params: tuple | list = ()):  # noqa: A003
        if self._dial == "postgres":
            sql = _qmark_to_pyformat(sql)
        self._raw.execute(sql, params)
        return self

    def fetchone(self):
        return self._raw.fetchone()

    def fetchall(self):
        return self._raw.fetchall()

    @property
    def rowcount(self) -> int:
        return self._raw.rowcount


def _qmark_to_pyformat(sql: str) -> str:
    """Rewrite ``?`` placeholders to ``%s`` for psycopg, ignoring ``?`` in
    string literals (there are none in our queries, but be safe)."""
    out, in_str = [], False
    for ch in sql:
        if ch == "'":
            in_str = not in_str
            out.append(ch)
        elif ch == "?" and not in_str:
            out.append("%s")
        else:
            out.append(ch)
    return "".join(out)


class Connection:
    def __init__(self, raw, dial: str):
        self._raw = raw
        self._dial = dial

    def cursor(self) -> Cursor:
        return Cursor(self._raw.cursor(), self._dial)

    def execute(self, sql: str, params: tuple | list = ()) -> Cursor:
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


def _connect_sqlite() -> Connection:
    path = _sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(path))
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA journal_mode=WAL;")
    raw.execute("PRAGMA foreign_keys=ON;")
    return Connection(raw, "sqlite")


def _connect_postgres() -> Connection:
    import psycopg  # imported lazily; only needed for the postgres backend
    from psycopg.rows import dict_row

    raw = psycopg.connect(get_settings().database_url, row_factory=dict_row)
    try:  # register pgvector adapters if available
        from pgvector.psycopg import register_vector

        register_vector(raw)
    except Exception:  # noqa: BLE001 - optional
        pass
    return Connection(raw, "postgres")


def connect() -> Connection:
    return _connect_postgres() if dialect() == "postgres" else _connect_sqlite()


@contextmanager
def connection() -> Iterator[Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_sql() -> str:
    """Portable 'current timestamp' expression."""
    return "CURRENT_TIMESTAMP"


__all__ = ["connect", "connection", "dialect", "Connection", "Cursor", "now_sql"]
