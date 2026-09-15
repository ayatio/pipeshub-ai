"""Hybrid retrieval (BUILD-BRIEF §6, Phase 3).

Two signals, fused:
  * FTS over chunk.tsv (always available; needs only the DB).
  * vector ANN over chunk.embedding (engages when embeddings exist and a query
    embedding can be produced via Ollama).

They are combined with Reciprocal Rank Fusion (RRF), which is scale-free — it
needs only each signal's *ranking*, not comparable scores — so the fusion is a
pure function, unit-tested offline. When only one signal is available, search
degrades to that signal alone rather than failing.
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg

from .config import Config
from .embedding import Embedder, to_pgvector

_RRF_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[str]], *, k: int = _RRF_K
) -> dict[str, float]:
    """Fuse several ranked id-lists into one score map (higher = better).

    RRF: score(d) = Σ 1 / (k + rank_i(d)), rank 1-based. Pure and deterministic.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def fuse_and_order(rankings: list[list[str]], *, k: int = _RRF_K) -> list[str]:
    """RRF-fuse rankings and return ids best-first.

    Ties break by first appearance across the inputs, so the order is stable.
    """
    scores = reciprocal_rank_fusion(rankings, k=k)
    first_seen: dict[str, int] = {}
    seq = 0
    for ranking in rankings:
        for doc_id in ranking:
            if doc_id not in first_seen:
                first_seen[doc_id] = seq
                seq += 1
    return sorted(scores, key=lambda d: (-scores[d], first_seen[d]))


@dataclass
class SearchHit:
    chunk_id: int
    episode_id: int
    heading_path: str
    content: str
    score: float
    signals: tuple[str, ...]  # which signals surfaced this hit


def _fts_ranking(conn: psycopg.Connection, query: str, limit: int) -> list[tuple[int, dict]]:
    """FTS candidates, best-first. Returns (chunk_id, row) pairs."""
    sql = (
        "SELECT c.id, c.episode_id, c.heading_path, c.content "
        "FROM chunk c "
        "WHERE c.tsv @@ websearch_to_tsquery('english', %s) "
        "ORDER BY ts_rank(c.tsv, websearch_to_tsquery('english', %s)) DESC "
        "LIMIT %s"
    )
    with conn.cursor() as cur:
        cur.execute(sql, (query, query, limit))
        return [
            (r[0], {"episode_id": r[1], "heading_path": r[2], "content": r[3]})
            for r in cur.fetchall()
        ]


def _vector_ranking(
    conn: psycopg.Connection, query_vec: list[float], limit: int
) -> list[tuple[int, dict]]:
    """Vector ANN candidates by cosine distance, best-first."""
    sql = (
        "SELECT c.id, c.episode_id, c.heading_path, c.content "
        "FROM chunk c "
        "WHERE c.embedding IS NOT NULL "
        "ORDER BY c.embedding <=> %s::vector "
        "LIMIT %s"
    )
    with conn.cursor() as cur:
        cur.execute(sql, (to_pgvector(query_vec), limit))
        return [
            (r[0], {"episode_id": r[1], "heading_path": r[2], "content": r[3]})
            for r in cur.fetchall()
        ]


def hybrid_search(
    conn: psycopg.Connection,
    query: str,
    *,
    k: int = 8,
    cfg: Config | None = None,
    embedder: Embedder | None = None,
    per_signal: int = 40,
) -> list[SearchHit]:
    """Run FTS (+ vector if available), RRF-fuse, and return the top k hits.

    If `embedder` is None the caller opted out of the vector signal (or Ollama is
    unavailable); search falls back to FTS only.
    """
    fts = _fts_ranking(conn, query, per_signal)
    rows: dict[str, dict] = {str(cid): row for cid, row in fts}
    rankings: list[list[str]] = [[str(cid) for cid, _ in fts]]
    signals_by_id: dict[str, set[str]] = {str(cid): {"fts"} for cid, _ in fts}

    if embedder is not None:
        qvec = embedder.embed(query)
        vec = _vector_ranking(conn, qvec, per_signal)
        for cid, row in vec:
            rows.setdefault(str(cid), row)
            signals_by_id.setdefault(str(cid), set()).add("vector")
        rankings.append([str(cid) for cid, _ in vec])

    scores = reciprocal_rank_fusion(rankings)
    ordered = fuse_and_order(rankings)
    hits: list[SearchHit] = []
    for cid in ordered[:k]:
        row = rows[cid]
        hits.append(
            SearchHit(
                chunk_id=int(cid),
                episode_id=row["episode_id"],
                heading_path=row["heading_path"],
                content=row["content"],
                score=round(scores[cid], 6),
                signals=tuple(sorted(signals_by_id.get(cid, set()))),
            )
        )
    return hits
