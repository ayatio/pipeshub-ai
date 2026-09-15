"""Candidate-link persistence, generation, and query (BUILD-BRIEF §5, Phase 5).

The pure builders/validators live in `linking.py`; this module writes what they
produce, generates the DB-derived link methods, and answers `relate`. Every link
is born `proposed` with a method, a score, and an evidence payload (§1.4).

Link methods realised here:
  * extracted   — from LLM relationships (written during capture --extract)
  * temporal    — co-mention within one episode
  * shared_attr — entities sharing a normalised prop value
  * semantic    — entity-embedding cosine ≥ threshold
  * structural  — [[wikilinks]] (parser in `wikilinks.py`)
"""
from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from .embedding import to_pgvector
from .linking import (
    CandidateLink,
    canonical_pair,
    make_link,
    semantic_link,
    shared_attr_link,
    temporal_link,
)

_SEMANTIC_THRESHOLD = 0.80


def upsert_link(
    conn: psycopg.Connection, link: CandidateLink, *, decided_by: str | None = None
) -> None:
    """Insert a proposed link, or strengthen an existing one for the same pair.

    On conflict we keep the human/rule decision (status, decided_by), merge
    evidence, and keep the higher score (with its method). We never silently
    downgrade a confirmed link back to proposed.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO candidate_link "
            "(a_id, b_id, rel_type, method, score, evidence, decided_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (a_id, b_id, rel_type) DO UPDATE SET "
            "  method = CASE WHEN EXCLUDED.score > candidate_link.score "
            "                THEN EXCLUDED.method ELSE candidate_link.method END, "
            "  score = GREATEST(candidate_link.score, EXCLUDED.score), "
            "  evidence = candidate_link.evidence || EXCLUDED.evidence, "
            "  updated_at = now()",
            (
                link.a_id, link.b_id, link.rel_type, link.method,
                link.score, Jsonb(link.evidence), decided_by,
            ),
        )


def set_status(
    conn: psycopg.Connection, a: str, b: str, rel_type: str, status: str, decided_by: str
) -> None:
    """Confirm or reject a link (the only way status leaves 'proposed', §1.4)."""
    a_id, b_id = canonical_pair(a, b)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE candidate_link SET status = %s, decided_by = %s, updated_at = now() "
            "WHERE a_id = %s AND b_id = %s AND rel_type = %s",
            (status, decided_by, a_id, b_id, rel_type),
        )


def relate(conn: psycopg.Connection, a: str, b: str) -> list[dict[str, Any]]:
    """Every link between two entities, with method, score, status, evidence."""
    a_id, b_id = canonical_pair(a, b)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT rel_type, method, score, status, evidence, decided_by "
            "FROM candidate_link WHERE a_id = %s AND b_id = %s "
            "ORDER BY score DESC",
            (a_id, b_id),
        )
        return [
            {
                "rel_type": r[0], "method": r[1], "score": r[2],
                "status": r[3], "evidence": r[4], "decided_by": r[5],
            }
            for r in cur.fetchall()
        ]


def neighbors(
    conn: psycopg.Connection,
    entity_id: str,
    *,
    min_score: float = 0.0,
    statuses: tuple[str, ...] = ("proposed", "confirmed"),
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Linked neighbours of an entity (for graph walk / MCP traverse)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT CASE WHEN a_id = %s THEN b_id ELSE a_id END AS other, "
            "       rel_type, method, score, status "
            "FROM candidate_link "
            "WHERE (a_id = %s OR b_id = %s) AND score >= %s AND status = ANY(%s) "
            "ORDER BY score DESC LIMIT %s",
            (entity_id, entity_id, entity_id, min_score, list(statuses), limit),
        )
        return [
            {"id": r[0], "rel_type": r[1], "method": r[2], "score": r[3], "status": r[4]}
            for r in cur.fetchall()
        ]


# --- Generators -------------------------------------------------------------
def _entity_exists(conn: psycopg.Connection, eid: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM entity WHERE id = %s", (eid,))
        return cur.fetchone() is not None


def generate_co_mention_links(conn: psycopg.Connection, episode_id: int) -> int:
    """Link every distinct pair of entities mentioned in one episode (temporal)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT m1.entity_id, m2.entity_id FROM entity_mention m1 "
            "JOIN entity_mention m2 ON m1.episode_id = m2.episode_id "
            "  AND m1.entity_id < m2.entity_id "
            "WHERE m1.episode_id = %s",
            (episode_id,),
        )
        pairs = cur.fetchall()
    for a, b in pairs:
        upsert_link(conn, temporal_link(a, b, episode_id))
    return len(pairs)


def generate_shared_attr_links(conn: psycopg.Connection) -> int:
    """Link entities that share a normalised (attr, value) in their props."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, props FROM entity WHERE props <> '{}'::jsonb")
        rows = cur.fetchall()
    groups: dict[tuple[str, str], list[str]] = {}
    for eid, props in rows:
        for key, value in (props or {}).items():
            if value is None or isinstance(value, (dict, list)):
                continue
            norm = (key, str(value).strip().lower())
            groups.setdefault(norm, []).append(eid)
    count = 0
    for (attr, value), ids in groups.items():
        ids = sorted(set(ids))
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                upsert_link(conn, shared_attr_link(ids[i], ids[j], attr, value))
                count += 1
    return count


def generate_semantic_links(
    conn: psycopg.Connection, *, threshold: float = _SEMANTIC_THRESHOLD
) -> int:
    """Link entity pairs whose embeddings are within cosine ≥ threshold."""
    max_distance = 1.0 - threshold
    with conn.cursor() as cur:
        cur.execute(
            "SELECT a.id, b.id, 1 - (a.embedding <=> b.embedding) AS cos "
            "FROM entity a JOIN entity b ON a.id < b.id "
            "WHERE a.embedding IS NOT NULL AND b.embedding IS NOT NULL "
            "  AND (a.embedding <=> b.embedding) <= %s",
            (max_distance,),
        )
        rows = cur.fetchall()
    count = 0
    for a, b, cos in rows:
        link = semantic_link(a, b, float(cos), threshold=threshold)
        if link is not None:
            upsert_link(conn, link)
            count += 1
    return count


def add_extracted_link(
    conn: psycopg.Connection,
    a_id: str,
    b_id: str,
    rel_type: str,
    evidence_text: str,
    episode_id: int,
) -> bool:
    """Persist an LLM-extracted relationship as an evidenced link.

    Both endpoints must already exist as entities (no dangling links). Returns
    True if a link was written.
    """
    if a_id == b_id or not _entity_exists(conn, a_id) or not _entity_exists(conn, b_id):
        return False
    link = make_link(
        a_id, b_id, rel_type, "extracted", 0.7,
        {"quote": evidence_text[:500], "episode_id": episode_id},
    )
    upsert_link(conn, link)
    return True
