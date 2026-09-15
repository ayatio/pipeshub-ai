"""Capture: ingest a markdown note into episode + chunks (BUILD-BRIEF Phase 2).

Idempotent by content_hash (§1.1, §4): re-capturing an unchanged note is a
no-op. Embeddings are populated in Phase 3 (embed=True), so capture works with
or without a live Ollama.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psycopg

from . import resolution as R
from .chunking import chunk_markdown
from .config import Config
from .embedding import Embedder, to_pgvector
from .extraction import Extractor
from .ids import content_hash


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
                    conn, episode_id, chunk_id, ch.content, extractor, embedder, resolved_ids
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
) -> None:
    """Extract entities from one chunk and resolve them into the graph.

    Relationships are recorded in Phase 5 (linking); here we persist the typed
    entities, their bi-temporal versions, and their mentions (provenance).
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
