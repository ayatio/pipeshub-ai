"""Nightly consolidation.

This is the "sleep" of the living brain: it reads everything that has been
ingested and produces a digest that surfaces (1) an overall summary, (2) the
dominant themes, and (3) surprising *connections* — pairs of chunks from
different notes that are semantically close but weren't written together.

The result is written both to the database (reports table) and to a timestamped
markdown file under the reports directory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from .config import Config
from .db import all_chunks, connect, counts, save_report
from .embeddings import cosine
from .llm import Summarizer, keywords


@dataclass
class Connection:
    score: float
    path_a: str
    path_b: str
    text_a: str
    text_b: str


def _find_connections(rows, top_n: int = 5) -> List[Connection]:
    """Highest-similarity chunk pairs that come from *different* documents."""
    parsed = [(r["path"], r["text"], json.loads(r["embedding"])) for r in rows]
    found: List[Connection] = []
    for i in range(len(parsed)):
        pa, ta, ea = parsed[i]
        for j in range(i + 1, len(parsed)):
            pb, tb, eb = parsed[j]
            if pa == pb:
                continue
            score = cosine(ea, eb)
            found.append(Connection(score, pa, pb, ta, tb))
    found.sort(key=lambda c: c.score, reverse=True)
    return found[:top_n]


def _snippet(text: str, n: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rstrip() + "…"


def consolidate(cfg: Config, stamp: str | None = None) -> Tuple[Path, str]:
    """Build the digest. `stamp` lets callers pass a deterministic timestamp."""
    conn = connect(cfg)
    try:
        rows = all_chunks(conn)
        n_docs, n_chunks = counts(conn)
    finally:
        conn.close()

    stamp = stamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    summarizer = Summarizer(cfg)

    if not rows:
        body = (
            f"# Nightly digest — {stamp}\n\n"
            "No notes have been ingested yet. Drop some `.md` files into "
            f"`{cfg.notes_dir}` and run ingest.\n"
        )
        path = _write_report(cfg, stamp, body, conn_title="Empty digest")
        return path, body

    corpus = "\n\n".join(r["text"] for r in rows)
    summary = summarizer.summarize(
        corpus,
        instruction=(
            "You are the nightly consolidation process of a personal knowledge "
            "base. Read the notes below and write a concise digest (5-8 "
            "sentences) capturing the key themes, open questions, and "
            "takeaways:"
        ),
    )
    themes = keywords(corpus, top_n=12)
    connections = _find_connections(rows, top_n=5)

    lines: List[str] = []
    lines.append(f"# Nightly digest — {stamp}")
    lines.append("")
    lines.append(
        f"*{n_docs} note(s), {n_chunks} chunk(s) · "
        f"summarizer: {summarizer.backend}*"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(summary.strip() or "_(no summary produced)_")
    lines.append("")
    lines.append("## Dominant themes")
    lines.append("")
    if themes:
        lines.append(
            "  ".join(f"`{w}`×{c}" for w, c in themes)
        )
    else:
        lines.append("_(no themes detected)_")
    lines.append("")
    lines.append("## Connections discovered")
    lines.append("")
    if connections and connections[0].score > 0:
        for c in connections:
            lines.append(
                f"- **{c.score:.2f}** — `{c.path_a}` ↔ `{c.path_b}`"
            )
            lines.append(f"    - {_snippet(c.text_a)}")
            lines.append(f"    - {_snippet(c.text_b)}")
    else:
        lines.append("_(not enough cross-note material yet)_")
    lines.append("")

    body = "\n".join(lines)
    path = _write_report(cfg, stamp, body, conn_title=f"Nightly digest {stamp}")
    return path, body


def _write_report(cfg: Config, stamp: str, body: str, conn_title: str) -> Path:
    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.reports_dir / f"digest-{stamp}.md"
    path.write_text(body, encoding="utf-8")
    conn = connect(cfg)
    try:
        save_report(conn, conn_title, body)
    finally:
        conn.close()
    return path
