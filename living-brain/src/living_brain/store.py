"""Persistence + retrieval for memories, links and insights.

SQLite stores embeddings as JSON text and ranks with in-Python cosine (fine for
a personal-scale brain). Postgres stores real ``vector`` columns and ranks with
pgvector's ``<=>`` operator inside the database.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import db
from .embeddings import cosine
from .config import get_settings


@dataclass
class Memory:
    id: int
    content: str
    title: str | None
    source: str | None
    kind: str
    importance: float
    embedding: list[float] | None
    meta: dict


def _emb_to_db(emb: list[float] | None):
    if emb is None:
        return None
    if db.dialect() == "postgres":
        return emb  # pgvector adapter handles the list
    return json.dumps(emb)


def _emb_from_db(val) -> list[float] | None:
    if val is None:
        return None
    if isinstance(val, str):
        return json.loads(val)
    if isinstance(val, (list, tuple)):
        return list(val)
    # pgvector returns numpy arrays
    try:
        return list(val)
    except TypeError:
        return None


def _row_to_memory(row: Any) -> Memory:
    meta = row["meta"]
    if isinstance(meta, str):
        meta = json.loads(meta)
    return Memory(
        id=int(row["id"]),
        content=row["content"],
        title=row["title"],
        source=row["source"],
        kind=row["kind"],
        importance=float(row["importance"]),
        embedding=_emb_from_db(row["embedding"]),
        meta=meta or {},
    )


# --------------------------------------------------------------------------- #
# writes
# --------------------------------------------------------------------------- #
def add_memory(
    content: str,
    *,
    title: str | None = None,
    source: str | None = None,
    kind: str = "note",
    embedding: list[float] | None = None,
    meta: dict | None = None,
    conn: db.Connection | None = None,
) -> int:
    meta_val = json.dumps(meta or {})
    sql = (
        "INSERT INTO memories (source, title, content, kind, embedding, meta) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    )
    params = (source, title, content, kind, _emb_to_db(embedding), meta_val)

    def _do(c: db.Connection) -> int:
        if db.dialect() == "postgres":
            row = c.execute(sql + " RETURNING id", params).fetchone()
            return int(row["id"])
        cur = c.execute(sql, params)
        return int(cur._raw.lastrowid)

    if conn is not None:
        return _do(conn)
    with db.connection() as c:
        return _do(c)


def set_embedding(mem_id: int, embedding: list[float], conn: db.Connection) -> None:
    conn.execute(
        "UPDATE memories SET embedding = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (_emb_to_db(embedding), mem_id),
    )


def upsert_link(
    src_id: int, dst_id: int, weight: float, conn: db.Connection, kind: str = "associative"
) -> bool:
    """Insert an associative link; ignore the mirror/duplicate. Returns True if new."""
    if src_id == dst_id:
        return False
    a, b = (src_id, dst_id) if src_id < dst_id else (dst_id, src_id)
    existing = conn.execute(
        "SELECT id FROM links WHERE src_id = ? AND dst_id = ? AND kind = ?",
        (a, b, kind),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE links SET weight = ? WHERE id = ?", (weight, existing["id"])
        )
        return False
    conn.execute(
        "INSERT INTO links (src_id, dst_id, kind, weight) VALUES (?, ?, ?, ?)",
        (a, b, kind, weight),
    )
    return True


def add_insight(
    title: str,
    content: str,
    source_ids: list[int],
    embedding: list[float] | None,
    conn: db.Connection,
    kind: str = "theme",
) -> int:
    sql = (
        "INSERT INTO insights (kind, title, content, embedding, source_ids) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    params = (kind, title, content, _emb_to_db(embedding), json.dumps(source_ids))
    if db.dialect() == "postgres":
        row = conn.execute(sql + " RETURNING id", params).fetchone()
        return int(row["id"])
    cur = conn.execute(sql, params)
    return int(cur._raw.lastrowid)


def touch_accessed(mem_id: int, conn: db.Connection) -> None:
    conn.execute(
        "UPDATE memories SET accessed_at = CURRENT_TIMESTAMP WHERE id = ?", (mem_id,)
    )


def decay_importance(factor: float, conn: db.Connection) -> None:
    """Nightly forgetting curve: un-accessed memories lose a little importance."""
    conn.execute("UPDATE memories SET importance = importance * ?", (factor,))


# --------------------------------------------------------------------------- #
# reads
# --------------------------------------------------------------------------- #
def get_memory(mem_id: int, conn: db.Connection | None = None) -> Memory | None:
    def _do(c: db.Connection):
        row = c.execute("SELECT * FROM memories WHERE id = ?", (mem_id,)).fetchone()
        return _row_to_memory(row) if row else None

    if conn is not None:
        return _do(conn)
    with db.connection() as c:
        return _do(c)


def unembedded(conn: db.Connection, limit: int = 128) -> list[Memory]:
    rows = conn.execute(
        "SELECT * FROM memories WHERE embedding IS NULL ORDER BY id LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_memory(r) for r in rows]


def all_embedded(conn: db.Connection) -> list[Memory]:
    rows = conn.execute(
        "SELECT * FROM memories WHERE embedding IS NOT NULL ORDER BY id"
    ).fetchall()
    return [_row_to_memory(r) for r in rows]


def counts() -> dict[str, int]:
    with db.connection() as conn:
        def one(table: str, where: str = "") -> int:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} {where}").fetchone()
            return int(row["n"])
        return {
            "memories": one("memories"),
            "embedded": one("memories", "WHERE embedding IS NOT NULL"),
            "links": one("links"),
            "insights": one("insights"),
            "night_runs": one("night_runs"),
        }


@dataclass
class SearchHit:
    memory: Memory
    score: float


def search(query_embedding: list[float], top_k: int = 5, kind: str | None = None) -> list[SearchHit]:
    with db.connection() as conn:
        if db.dialect() == "postgres":
            where = "WHERE embedding IS NOT NULL"
            kind_params: list[Any] = []
            if kind:
                where += " AND kind = ?"
                kind_params.append(kind)
            rows = conn.execute(
                f"SELECT *, 1 - (embedding <=> ?) AS score FROM memories "
                f"{where} ORDER BY embedding <=> ? LIMIT ?",
                [query_embedding, *kind_params, query_embedding, top_k],
            ).fetchall()
            hits = [SearchHit(_row_to_memory(r), float(r["score"])) for r in rows]
        else:
            mems = all_embedded(conn)
            if kind:
                mems = [m for m in mems if m.kind == kind]
            scored = [
                SearchHit(m, cosine(query_embedding, m.embedding)) for m in mems
            ]
            scored.sort(key=lambda h: h.score, reverse=True)
            hits = scored[:top_k]
        for h in hits:
            touch_accessed(h.memory.id, conn)
        return hits


__all__ = [
    "Memory", "SearchHit", "add_memory", "set_embedding", "upsert_link",
    "add_insight", "touch_accessed", "decay_importance", "get_memory",
    "unembedded", "all_embedded", "counts", "search",
]
