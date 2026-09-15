"""Entity resolution + bi-temporal versioning (BUILD-BRIEF §5, Phase 4).

Resolution ladder (deterministic first, then fuzzy):
  1. exact alias           2. exact slug/label (within type)
  3. trigram label match   4. embedding cosine match   5. mint new entity

Every resolution records an entity_mention (provenance, §1.2). Facts are
append-only and bi-temporal (§1.3): a new version is written only when the
label/props actually change, closing the previous open version's valid_to.

Resolution needs only the DB (no LLM), so it is exercised under `-m db`; the
embedding step engages when a vector is supplied.
"""
from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from .embedding import to_pgvector
from .ids import entity_id as make_entity_id

_TRIGRAM_THRESHOLD = 0.55
_COSINE_THRESHOLD = 0.85


def _exact_alias(conn: psycopg.Connection, label: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT entity_id FROM entity_alias WHERE alias = %s LIMIT 1", (label,))
        row = cur.fetchone()
        return row[0] if row else None


def _exact_id(conn: psycopg.Connection, eid: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM entity WHERE id = %s", (eid,))
        row = cur.fetchone()
        return row[0] if row else None


def _trigram_match(
    conn: psycopg.Connection, type_: str, label: str, threshold: float
) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, similarity(label, %s) AS sim FROM entity "
            "WHERE type = %s AND similarity(label, %s) >= %s "
            "ORDER BY sim DESC LIMIT 1",
            (label, type_, label, threshold),
        )
        row = cur.fetchone()
        return row[0] if row else None


def _cosine_match(
    conn: psycopg.Connection, type_: str, vec: list[float], threshold: float
) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, 1 - (embedding <=> %s::vector) AS cos FROM entity "
            "WHERE type = %s AND embedding IS NOT NULL "
            "ORDER BY embedding <=> %s::vector LIMIT 1",
            (to_pgvector(vec), type_, to_pgvector(vec)),
        )
        row = cur.fetchone()
        if row and row[1] is not None and row[1] >= threshold:
            return row[0]
        return None


def resolve_entity(
    conn: psycopg.Connection,
    type_: str,
    label: str,
    *,
    embedding: list[float] | None = None,
    trigram_threshold: float = _TRIGRAM_THRESHOLD,
    cosine_threshold: float = _COSINE_THRESHOLD,
) -> tuple[str, bool]:
    """Resolve (type, label) to an entity id. Returns (entity_id, created).

    Does not insert; `upsert_entity` performs the write. This is the read-side
    of resolution so callers can resolve both ends of a relationship first.
    """
    if (hit := _exact_alias(conn, label)) is not None:
        return hit, False
    candidate_id = make_entity_id(type_, label)
    if (hit := _exact_id(conn, candidate_id)) is not None:
        return hit, False
    if (hit := _trigram_match(conn, type_, label, trigram_threshold)) is not None:
        return hit, False
    if embedding is not None:
        if (hit := _cosine_match(conn, type_, embedding, cosine_threshold)) is not None:
            return hit, False
    return candidate_id, True


def upsert_entity(
    conn: psycopg.Connection,
    entity_id: str,
    type_: str,
    label: str,
    props: dict[str, Any],
    *,
    aliases: list[str] | None = None,
    embedding: list[float] | None = None,
) -> None:
    """Insert or update the denormalised entity snapshot and its aliases.

    props are merged (new keys win); an embedding overwrites only if supplied.
    """
    emb = to_pgvector(embedding) if embedding is not None else None
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entity (id, type, label, props, embedding) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET "
            "  label = EXCLUDED.label, "
            "  props = entity.props || EXCLUDED.props, "
            "  embedding = COALESCE(EXCLUDED.embedding, entity.embedding), "
            "  updated_at = now()",
            (entity_id, type_, label, Jsonb(props), emb),
        )
        for alias in {label, *(aliases or [])}:
            cur.execute(
                "INSERT INTO entity_alias (entity_id, alias) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                (entity_id, alias),
            )


def append_version_if_changed(
    conn: psycopg.Connection,
    entity_id: str,
    type_: str,
    label: str,
    props: dict[str, Any],
    *,
    episode_id: int | None = None,
) -> bool:
    """Append a bi-temporal version iff label/props differ from the open one.

    Closes the previously-open version's valid_to before opening the new one.
    Returns True if a new version was written.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, label, props FROM entity_version "
            "WHERE entity_id = %s AND valid_to IS NULL "
            "ORDER BY recorded_at DESC LIMIT 1",
            (entity_id,),
        )
        current = cur.fetchone()
        if current is not None and current[1] == label and current[2] == props:
            return False
        if current is not None:
            cur.execute(
                "UPDATE entity_version SET valid_to = now() WHERE id = %s", (current[0],)
            )
        cur.execute(
            "INSERT INTO entity_version "
            "(entity_id, type, label, props, valid_from, episode_id) "
            "VALUES (%s, %s, %s, %s, now(), %s)",
            (entity_id, type_, label, Jsonb(props), episode_id),
        )
    return True


def record_mention(
    conn: psycopg.Connection,
    entity_id: str,
    episode_id: int,
    chunk_id: int | None = None,
) -> None:
    """Record that an entity was mentioned in an episode (provenance)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entity_mention (entity_id, episode_id, chunk_id) "
            "VALUES (%s, %s, %s) ON CONFLICT (entity_id, episode_id) DO NOTHING",
            (entity_id, episode_id, chunk_id),
        )
