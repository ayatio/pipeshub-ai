"""Heading-aware markdown chunking (BUILD-BRIEF §2, Phase 2).

Pure and deterministic: same markdown in, same chunks out — no DB, no network.
Each chunk carries its heading breadcrumb ('Doc > Section > Sub') and its text is
prefixed with that breadcrumb so embeddings keep document context.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_DEFAULT_MAX_CHARS = 1200


@dataclass(frozen=True)
class Chunk:
    heading_path: str  # e.g. "Meeting Notes > Decisions"
    content: str       # breadcrumb-prefixed text, ready to embed


def _split_paragraphs(body: str) -> list[str]:
    """Split a section body into paragraph blocks on blank lines."""
    blocks, cur = [], []
    for line in body.splitlines():
        if line.strip() == "":
            if cur:
                blocks.append("\n".join(cur).strip())
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur).strip())
    return [b for b in blocks if b]


def _pack(paragraphs: list[str], max_chars: int) -> list[str]:
    """Greedily pack paragraphs into pieces of at most max_chars.

    A single paragraph longer than max_chars is emitted whole (we never split
    mid-sentence — deterministically simpler and keeps meaning intact).
    """
    pieces, cur = [], ""
    for para in paragraphs:
        if not cur:
            cur = para
        elif len(cur) + 2 + len(para) <= max_chars:
            cur = f"{cur}\n\n{para}"
        else:
            pieces.append(cur)
            cur = para
    if cur:
        pieces.append(cur)
    return pieces


def chunk_markdown(
    text: str, *, title: str = "", max_chars: int = _DEFAULT_MAX_CHARS
) -> list[Chunk]:
    """Chunk markdown into heading-aware, breadcrumb-prefixed pieces.

    - `title` (e.g. the note filename) seeds the heading path so even
      pre-heading content is contextualised.
    - Sections longer than `max_chars` are packed at paragraph boundaries.
    - Returns [] for empty/whitespace-only input.
    """
    lines = text.splitlines()
    # stack of (level, heading_text); level 0 is the optional title.
    stack: list[tuple[int, str]] = [(0, title)] if title else []
    sections: list[tuple[str, list[str]]] = []
    cur_body: list[str] = []

    def breadcrumb() -> str:
        return " > ".join(h for _, h in stack if h)

    def flush() -> None:
        body = "\n".join(cur_body).strip()
        if body:
            sections.append((breadcrumb(), _split_paragraphs(body)))

    for line in lines:
        m = _ATX.match(line)
        if m:
            flush()
            cur_body = []
            level = len(m.group(1))
            heading = m.group(2).strip()
            # pop headings at or below this level, then push (keep title at 0).
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, heading))
        else:
            cur_body.append(line)
    flush()

    chunks: list[Chunk] = []
    for path, paragraphs in sections:
        for piece in _pack(paragraphs, max_chars):
            prefix = f"{path}\n\n" if path else ""
            chunks.append(Chunk(heading_path=path, content=f"{prefix}{piece}"))
    return chunks
