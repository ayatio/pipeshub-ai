"""Ingestion: walk the notes directory, chunk changed files, embed, store.

Only files whose content hash changed since last ingest are re-embedded, so
running ingest repeatedly (as the nightly loop does) is cheap and idempotent.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .config import Config
from .db import (
    connect,
    delete_chunks_for_document,
    get_document,
    insert_chunk,
    upsert_document,
)
from .embeddings import Embedder

_TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".text", ".rst", ".org"}


@dataclass
class IngestResult:
    scanned: int = 0
    ingested: int = 0
    unchanged: int = 0
    chunks: int = 0
    backend: str = "unknown"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str, size: int, overlap: int) -> List[str]:
    """Chunk on paragraph boundaries where possible, then pack to ~size chars."""
    text = text.strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    buf = ""
    for para in paragraphs:
        if not buf:
            buf = para
        elif len(buf) + 2 + len(para) <= size:
            buf += "\n\n" + para
        else:
            chunks.append(buf)
            # carry an overlap tail into the next chunk for context continuity
            tail = buf[-overlap:] if overlap > 0 else ""
            buf = (tail + "\n\n" + para).strip() if tail else para
    if buf:
        chunks.append(buf)

    # Hard-split any oversized single paragraph.
    final: List[str] = []
    for c in chunks:
        if len(c) <= size * 1.5:
            final.append(c)
            continue
        start = 0
        while start < len(c):
            final.append(c[start:start + size])
            start += max(size - overlap, 1)
    return final


def iter_note_files(notes_dir: Path):
    if not notes_dir.exists():
        return
    for p in sorted(notes_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in _TEXT_SUFFIXES:
            yield p


def ingest(cfg: Config) -> IngestResult:
    result = IngestResult()
    embedder = Embedder(cfg)
    conn = connect(cfg)
    try:
        for path in iter_note_files(cfg.notes_dir):
            result.scanned += 1
            rel = str(path.relative_to(cfg.notes_dir))
            content = path.read_text(encoding="utf-8", errors="replace")
            sha = _sha256(content)

            existing = get_document(conn, rel)
            if existing is not None and existing["sha"] == sha:
                result.unchanged += 1
                continue

            doc_id = upsert_document(conn, rel, sha)
            delete_chunks_for_document(conn, doc_id)

            pieces = chunk_text(content, cfg.chunk_size, cfg.chunk_overlap)
            for ordinal, piece in enumerate(pieces):
                emb = embedder.embed(piece)
                insert_chunk(conn, doc_id, ordinal, piece, emb)
                result.chunks += 1
            conn.commit()
            result.ingested += 1
        result.backend = embedder.backend
    finally:
        conn.close()
    return result
