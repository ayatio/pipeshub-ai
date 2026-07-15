"""Semantic search over memories (and, optionally, consolidated insights)."""
from __future__ import annotations

from . import store
from .embeddings import embed


def search(query: str, top_k: int = 5, kind: str | None = None) -> list[store.SearchHit]:
    return store.search(embed(query), top_k=top_k, kind=kind)


__all__ = ["search"]
