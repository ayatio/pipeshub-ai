"""Memory store: ingest, retrieve, and the row <-> object plumbing."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .db import connect
from .embeddings import Embedder
from .util import cosine, now_iso, pack_vector, unpack_vector


@dataclass
class Memory:
    id: int
    content: str
    source: str
    kind: str
    importance: float
    created_at: str
    last_seen_at: str
    access_count: int
    archived: int
    tags: str = ""


def _row_to_memory(row) -> Memory:
    return Memory(
        id=row["id"],
        content=row["content"],
        source=row["source"],
        kind=row["kind"],
        importance=row["importance"],
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
        access_count=row["access_count"],
        archived=row["archived"],
        tags=row["tags"] if "tags" in row.keys() else "",
    )


class MemoryStore:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.embedder = Embedder(cfg)

    # -- ingest -------------------------------------------------------------
    def add(
        self,
        content: str,
        *,
        source: str = "manual",
        kind: str = "note",
        importance: float = 0.5,
        tags: str = "",
    ) -> int:
        content = content.strip()
        if not content:
            raise ValueError("cannot store an empty memory")
        ts = now_iso()
        emb = self.embedder.embed(content)
        conn = connect(self.cfg.db_path)
        try:
            cur = conn.execute(
                """INSERT INTO memories
                   (content, source, kind, importance, created_at, last_seen_at, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (content, source, kind, importance, ts, ts, tags),
            )
            mem_id = cur.lastrowid
            conn.execute(
                "INSERT INTO embeddings(memory_id, model, dim, vector) VALUES (?, ?, ?, ?)",
                (mem_id, emb.model, emb.dim, pack_vector(emb.vector)),
            )
            conn.commit()
            return mem_id
        finally:
            conn.close()

    # -- retrieve -----------------------------------------------------------
    def search(self, query: str, top_k: int | None = None) -> list[tuple[Memory, float]]:
        top_k = top_k or self.cfg.top_k
        q = self.embedder.embed(query)
        conn = connect(self.cfg.db_path)
        try:
            rows = conn.execute(
                """SELECT m.*, e.dim AS e_dim, e.vector AS e_vec
                   FROM memories m JOIN embeddings e ON e.memory_id = m.id
                   WHERE m.archived = 0"""
            ).fetchall()
            scored: list[tuple[Memory, float]] = []
            for row in rows:
                if row["e_dim"] != q.dim:
                    continue  # different embedding space; skip
                vec = unpack_vector(row["e_vec"])
                scored.append((_row_to_memory(row), cosine(q.vector, vec)))
            scored.sort(key=lambda t: t[1], reverse=True)
            top = scored[:top_k]
            # Reinforcement: retrieved memories are "seen" again.
            if top:
                ids = [m.id for m, _ in top]
                conn.executemany(
                    "UPDATE memories SET access_count = access_count + 1, last_seen_at = ? WHERE id = ?",
                    [(now_iso(), i) for i in ids],
                )
                conn.commit()
            return top
        finally:
            conn.close()

    # -- stats --------------------------------------------------------------
    def counts(self) -> dict[str, int]:
        conn = connect(self.cfg.db_path)
        try:
            active = conn.execute(
                "SELECT COUNT(*) c FROM memories WHERE archived = 0"
            ).fetchone()["c"]
            archived = conn.execute(
                "SELECT COUNT(*) c FROM memories WHERE archived = 1"
            ).fetchone()["c"]
            insights = conn.execute("SELECT COUNT(*) c FROM insights").fetchone()["c"]
            return {"active": active, "archived": archived, "insights": insights}
        finally:
            conn.close()
