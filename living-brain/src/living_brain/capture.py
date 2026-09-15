"""Capture: ingest a markdown note into episode + chunks (BUILD-BRIEF Phase 2).

Idempotent by content_hash (§1.1, §4): re-capturing an unchanged note is a
no-op. Embeddings are populated in Phase 3 (embed=True), so capture works with
or without a live Ollama.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psycopg

from . import links as L
from . import resolution as R
from .chunking import chunk_markdown
from .config import Config
from .embedding import Embedder, to_pgvector
from .extraction import ExtractedRelationship, Extractor
from .ids import content_hash
from .linking import make_link
from .wikilinks import parse_wikilinks


@dataclass
class CaptureResult:
    episode_id: int | None
    chunk_count: int
    created: bool  # False when the note was already present (idempotent no-op)
    entity_count: int = 0  # distinct entities resolved (when extract=True)


def capture_text(
    conn: psycopg.Connection,
    text: str,
    *,
    title: str = "",
    source: str | None = None,
    kind: str = "note",
    embed: bool = False,
    extract: bool = False,
    cfg: Config | None = None,
    extractor: Extractor | None = None,
) -> CaptureResult:
    """Ingest raw markdown as one episode plus heading-aware chunks.

    Returns created=False (and no new rows) if an episode with the same
    content_hash already exists. With extract=True, each chunk is run through the
    LLM extractor and resolved into entities / versions / mentions (Phase 4).
    """
    chash = content_hash(text)
    # Entity/chunk embeddings are opt-in via embed=True; extraction can run
    # without them (resolution falls back to alias/label/trigram).
    embedder = Embedder(cfg) if embed else None
    extractor = extractor or (Extractor(cfg) if extract else None)
    resolved_ids: set[str] = set()

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM episode WHERE content_hash = %s", (chash,))
        row = cur.fetchone()
        if row is not None:
            return CaptureResult(episode_id=row[0], chunk_count=0, created=False)

        cur.execute(
            "INSERT INTO episode (kind, source, content, content_hash) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (kind, source, text, chash),
        )
        episode_id = cur.fetchone()[0]

        chunks = chunk_markdown(text, title=title)
        label_to_eid: dict[str, str] = {}
        relationships: list[ExtractedRelationship] = []
        for ch in chunks:
            embedding = to_pgvector(embedder.embed(ch.content)) if embedder else None
            cur.execute(
                "INSERT INTO chunk (episode_id, heading_path, content, embedding) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (episode_id, ch.heading_path, ch.content, embedding),
            )
            chunk_id = cur.fetchone()[0]
            if extractor is not None:
                _extract_chunk(
                    conn, episode_id, chunk_id, ch.content, extractor, embedder,
                    resolved_ids, label_to_eid, relationships,
                )

        if extractor is not None:
            _build_links(
                conn, episode_id, text, resolved_ids, label_to_eid, relationships
            )
    conn.commit()
    return CaptureResult(
        episode_id=episode_id,
        chunk_count=len(chunks),
        created=True,
        entity_count=len(resolved_ids),
    )


def _extract_chunk(
    conn: psycopg.Connection,
    episode_id: int,
    chunk_id: int,
    text: str,
    extractor: Extractor,
    embedder: Embedder | None,
    resolved_ids: set[str],
    label_to_eid: dict[str, str],
    relationships: list[ExtractedRelationship],
) -> None:
    """Extract entities from one chunk, resolve them, and collect relationships.

    Persists typed entities, their bi-temporal versions, and their mentions
    (provenance). Relationships and the label→entity map are accumulated for the
    episode-level link pass in `_build_links`.
    """
    extraction = extractor.extract(text)
    for ent in extraction.entities:
        emb = embedder.embed(ent.label) if embedder else None
        eid, _ = R.resolve_entity(conn, ent.type, ent.label, embedding=emb)
        R.upsert_entity(conn, eid, ent.type, ent.label, ent.props,
                        aliases=ent.aliases, embedding=emb)
        R.append_version_if_changed(conn, eid, ent.type, ent.label, ent.props,
                                    episode_id=episode_id)
        R.record_mention(conn, eid, episode_id, chunk_id)
        resolved_ids.add(eid)
        label_to_eid[ent.label] = eid
        for alias in ent.aliases:
            label_to_eid[alias] = eid
    relationships.extend(extraction.relationships)


def _build_links(
    conn: psycopg.Connection,
    episode_id: int,
    text: str,
    resolved_ids: set[str],
    label_to_eid: dict[str, str],
    relationships: list[ExtractedRelationship],
) -> None:
    """Episode-level link pass: extracted, structural, and co-mention (temporal)."""
    # extracted: LLM relationships whose endpoints resolved to real entities
    for rel in relationships:
        a = label_to_eid.get(rel.source) or _resolve_existing(conn, rel.source)
        b = label_to_eid.get(rel.target) or _resolve_existing(conn, rel.target)
        if a and b and a != b:
            L.add_extracted_link(conn, a, b, rel.rel_type, rel.evidence, episode_id)

    # structural: [[wikilinks]] mint concept entities the note references
    entity_ids = list(resolved_ids)
    for target in parse_wikilinks(text):
        cid, _ = R.resolve_entity(conn, "concept", target)
        R.upsert_entity(conn, cid, "concept", target, {})
        R.record_mention(conn, cid, episode_id)
        for eid in entity_ids:
            if eid != cid:
                L.upsert_link(
                    conn,
                    make_link(eid, cid, "references", "structural", 0.6,
                              {"wikilink": target, "episode_id": episode_id}),
                )
        resolved_ids.add(cid)

    # temporal: co-mention across everything now mentioned in this episode
    L.generate_co_mention_links(conn, episode_id)


def _resolve_existing(conn: psycopg.Connection, label: str) -> str | None:
    """Resolve a label to an EXISTING entity id, or None (never mints)."""
    eid, created = R.resolve_entity(conn, "thing", label)
    return None if created else eid


def capture_file(
    conn: psycopg.Connection,
    path: Path,
    *,
    embed: bool = False,
    extract: bool = False,
    cfg: Config | None = None,
) -> CaptureResult:
    """Capture a markdown file; the filename stem seeds the chunk heading path."""
    text = path.read_text(encoding="utf-8")
    return capture_text(
        conn, text, title=path.stem, source=str(path), embed=embed, extract=extract, cfg=cfg
    )
