"""SQLite persistence layer + a tiny migration runner.

We use the Python standard-library sqlite3 module so there is nothing to
install and it works fully offline. Embeddings are stored as JSON arrays of
floats; corpora for a personal second brain are small enough that a linear
cosine scan in Python is perfectly fast.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from .config import Config, PROJECT_ROOT

MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def connect(cfg: Config) -> sqlite3.Connection:
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(cfg: Config) -> Path:
    """Create the database file and the migrations bookkeeping table."""
    conn = connect(cfg)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id        TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    return cfg.db_path


def _applied(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT id FROM schema_migrations").fetchall()
    return {r["id"] for r in rows}


def migrate(cfg: Config) -> list[str]:
    """Apply any pending .sql files in migrations/ in lexical order."""
    init_db(cfg)
    conn = connect(cfg)
    applied_now: list[str] = []
    try:
        done = _applied(conn)
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            mig_id = sql_file.stem
            if mig_id in done:
                continue
            conn.executescript(sql_file.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (id) VALUES (?)", (mig_id,)
            )
            conn.commit()
            applied_now.append(mig_id)
    finally:
        conn.close()
    return applied_now


# --- Document / chunk helpers ------------------------------------------------


def get_document(conn: sqlite3.Connection, path: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM documents WHERE path = ?", (path,)
    ).fetchone()


def upsert_document(conn: sqlite3.Connection, path: str, sha: str) -> int:
    """Insert or update a document row, returning its id."""
    existing = get_document(conn, path)
    if existing is None:
        cur = conn.execute(
            "INSERT INTO documents (path, sha, updated_at) "
            "VALUES (?, ?, datetime('now'))",
            (path, sha),
        )
        return int(cur.lastrowid)
    conn.execute(
        "UPDATE documents SET sha = ?, updated_at = datetime('now') WHERE id = ?",
        (sha, existing["id"]),
    )
    return int(existing["id"])


def delete_chunks_for_document(conn: sqlite3.Connection, doc_id: int) -> None:
    conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))


def insert_chunk(
    conn: sqlite3.Connection,
    doc_id: int,
    ordinal: int,
    text: str,
    embedding: Iterable[float],
) -> None:
    conn.execute(
        "INSERT INTO chunks (document_id, ordinal, text, embedding) "
        "VALUES (?, ?, ?, ?)",
        (doc_id, ordinal, text, json.dumps(list(embedding))),
    )


def all_chunks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT c.id, c.document_id, c.ordinal, c.text, c.embedding, d.path
        FROM chunks c JOIN documents d ON d.id = c.document_id
        ORDER BY d.path, c.ordinal
        """
    ).fetchall()


def counts(conn: sqlite3.Connection) -> tuple[int, int]:
    docs = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
    chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
    return int(docs), int(chunks)


def save_report(conn: sqlite3.Connection, title: str, content: str) -> int:
    cur = conn.execute(
        "INSERT INTO reports (title, content, created_at) "
        "VALUES (?, ?, datetime('now'))",
        (title, content),
    )
    conn.commit()
    return int(cur.lastrowid)
