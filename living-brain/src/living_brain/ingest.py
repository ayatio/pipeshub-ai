"""Ingest notes (files or raw text) into the brain as memories.

Markdown/text files are split into paragraph-sized chunks so each memory is a
single coherent thought. Embeddings are left NULL and filled in by the next
night run (or eagerly via ``embed=True``).
"""
from __future__ import annotations

import re
from pathlib import Path

from . import db, store
from .config import get_settings
from .embeddings import embed

_CHUNK_SPLIT = re.compile(r"\n\s*\n")  # blank-line paragraph breaks


def chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    chunks: list[str] = []
    for para in _CHUNK_SPLIT.split(text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            chunks.append(para)
            continue
        # Long paragraph: split on sentence boundaries into <= max_chars pieces.
        buf = ""
        for sent in re.split(r"(?<=[.!?])\s+", para):
            if len(buf) + len(sent) + 1 > max_chars and buf:
                chunks.append(buf.strip())
                buf = sent
            else:
                buf = f"{buf} {sent}".strip()
        if buf.strip():
            chunks.append(buf.strip())
    return chunks


def ingest_text(
    text: str,
    *,
    source: str | None = None,
    title: str | None = None,
    kind: str = "note",
    embed_now: bool = False,
) -> list[int]:
    ids: list[int] = []
    with db.connection() as conn:
        for chunk in chunk_text(text):
            emb = embed(chunk) if embed_now else None
            mem_id = store.add_memory(
                chunk, title=title, source=source, kind=kind,
                embedding=emb, conn=conn,
            )
            ids.append(mem_id)
    return ids


def ingest_file(path: Path, *, embed_now: bool = False) -> list[int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    title = _title_from_markdown(text) or path.stem.replace("_", " ").title()
    return ingest_text(
        text, source=str(path), title=title, embed_now=embed_now
    )


def ingest_dir(directory: Path, *, embed_now: bool = False) -> dict[str, int]:
    exts = {".md", ".markdown", ".txt"}
    result: dict[str, int] = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix.lower() in exts:
            ids = ingest_file(path, embed_now=embed_now)
            result[str(path)] = len(ids)
    return result


def _title_from_markdown(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line:
            break
    return None


__all__ = ["ingest_text", "ingest_file", "ingest_dir", "chunk_text"]
