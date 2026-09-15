"""Capture: ingest a markdown note into episode + chunks (BUILD-BRIEF Phase 2).

Idempotent by content_hash (§1.1, §4): re-capturing an unchanged note is a
no-op. Embeddings are populated in Phase 3 (embed=True), so capture works with
or without a live Ollama.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psycopg

from .chunking import chunk_markdown
from .config import Config
from .embedding import Embedder, to_pgvector
from .ids import content_hash


@dataclass
class CaptureResult:
    episode_id: int | None
    chunk_count: int
    created: bool  # False when the note was already present (idempotent no-op)


def capture_text(
    conn: psycopg.Connection,
    text: str,
    *,
    title: str = "",
    source: str | None = None,
    kind: str = "note",
    embed: bool = False,
    cfg: Config | None = None,
) -> CaptureResult:
    """Ingest raw markdown as one episode plus heading-aware chunks.

    Returns created=False (and no new rows) if an episode with the same
    content_hash already exists.
    """
    chash = content_hash(text)
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
        embedder = Embedder(cfg) if embed else None
        for ch in chunks:
            embedding = to_pgvector(embedder.embed(ch.content)) if embedder else None
            cur.execute(
                "INSERT INTO chunk (episode_id, heading_path, content, embedding) "
                "VALUES (%s, %s, %s, %s)",
                (episode_id, ch.heading_path, ch.content, embedding),
            )
    conn.commit()
    return CaptureResult(episode_id=episode_id, chunk_count=len(chunks), created=True)


def capture_file(
    conn: psycopg.Connection, path: Path, *, embed: bool = False, cfg: Config | None = None
) -> CaptureResult:
    """Capture a markdown file; the filename stem seeds the chunk heading path."""
    text = path.read_text(encoding="utf-8")
    return capture_text(
        conn, text, title=path.stem, source=str(path), embed=embed, cfg=cfg
    )
