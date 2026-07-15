"""Memory consolidation — the work the brain does 'overnight'.

One consolidation *cycle* does four things, mirroring sleep-time replay:
  1. embed  — give any new memory a vector
  2. link   — connect each memory to its nearest neighbours (associative recall)
  3. theme  — cluster tightly-linked memories and write an insight via the LLM
  4. decay  — apply the forgetting curve to un-accessed memories

Each step is bounded so a cycle is cheap; ``night.py`` loops cycles until the
time budget runs out.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import db, store
from .config import get_settings
from .embeddings import embed, cosine
from .llm import summarize_theme


@dataclass
class CycleReport:
    embedded: int = 0
    links_created: int = 0
    insights_created: int = 0
    did_work: bool = False
    detail: list[str] = field(default_factory=list)


def _embed_new(conn: db.Connection, limit: int) -> int:
    pending = store.unembedded(conn, limit=limit)
    for mem in pending:
        store.set_embedding(mem.id, embed(mem.content), conn)
    return len(pending)


def _build_links(conn: db.Connection) -> int:
    s = get_settings()
    mems = store.all_embedded(conn)
    if len(mems) < 2:
        return 0
    mat = np.asarray([m.embedding for m in mems], dtype=np.float64)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = mat / norms
    sims = unit @ unit.T
    created = 0
    for i, mem in enumerate(mems):
        order = np.argsort(-sims[i])
        made = 0
        for j in order:
            if j == i:
                continue
            score = float(sims[i, j])
            if score < s.link_min_sim or made >= s.link_top_k:
                break
            if store.upsert_link(mem.id, mems[j].id, score, conn):
                created += 1
            made += 1
    return created


def _cluster_and_theme(conn: db.Connection) -> tuple[int, list[str]]:
    """Find connected components over strong links; summarize new/large ones."""
    s = get_settings()
    rows = conn.execute(
        "SELECT src_id, dst_id, weight FROM links WHERE kind = 'associative'"
    ).fetchall()
    if not rows:
        return 0, []

    # union-find over memories connected by strong links
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    strong = [r for r in rows if float(r["weight"]) >= max(s.link_min_sim, 0.45)]
    for r in strong:
        union(int(r["src_id"]), int(r["dst_id"]))

    clusters: dict[int, list[int]] = {}
    for node in list(parent.keys()):
        clusters.setdefault(find(node), []).append(node)

    # which memory-sets already have an insight? avoid re-summarizing them.
    existing = set()
    for row in conn.execute("SELECT source_ids FROM insights").fetchall():
        import json

        try:
            existing.add(frozenset(json.loads(row["source_ids"])))
        except Exception:  # noqa: BLE001
            pass

    created = 0
    detail: list[str] = []
    for members in clusters.values():
        if len(members) < s.theme_min_cluster:
            continue
        key = frozenset(members)
        if key in existing:
            continue
        mems = [store.get_memory(mid, conn) for mid in sorted(members)]
        mems = [m for m in mems if m]
        texts = [m.content for m in mems]
        title, body = summarize_theme(texts)
        emb = embed(f"{title}. {body}")
        store.add_insight(title, body, [m.id for m in mems], emb, conn)
        created += 1
        detail.append(f"theme '{title}' over {len(mems)} memories")
    return created, detail


def run_cycle() -> CycleReport:
    report = CycleReport()
    s = get_settings()
    with db.connection() as conn:
        report.embedded = _embed_new(conn, limit=64)
        report.links_created = _build_links(conn)
        insights, detail = _cluster_and_theme(conn)
        report.insights_created = insights
        report.detail = detail
        store.decay_importance(s.importance_decay, conn)
    report.did_work = bool(
        report.embedded or report.links_created or report.insights_created
    )
    return report


__all__ = ["run_cycle", "CycleReport"]
