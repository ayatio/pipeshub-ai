"""Semantic search over stored chunks (linear cosine scan)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List

from .config import Config
from .db import all_chunks, connect
from .embeddings import Embedder, cosine


@dataclass
class SearchHit:
    score: float
    path: str
    ordinal: int
    text: str


def search(cfg: Config, query: str, top_k: int = 5) -> List[SearchHit]:
    embedder = Embedder(cfg)
    q_emb = embedder.embed(query)
    conn = connect(cfg)
    try:
        rows = all_chunks(conn)
    finally:
        conn.close()

    hits: List[SearchHit] = []
    for row in rows:
        emb = json.loads(row["embedding"])
        hits.append(
            SearchHit(
                score=cosine(q_emb, emb),
                path=row["path"],
                ordinal=row["ordinal"],
                text=row["text"],
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]
