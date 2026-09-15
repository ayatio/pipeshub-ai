"""Ollama embedding client (BUILD-BRIEF §1.6, Phase 3).

Local-first: talks to a local Ollama by default. Kept thin and dependency-light
(httpx). The vector formatting helper is pure and unit-tested offline; the
network call is exercised only under `-m ollama`.
"""
from __future__ import annotations

import httpx

from .config import Config


def to_pgvector(vec: list[float]) -> str:
    """Format a float list as a pgvector literal: [0.1,0.2,0.3]."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


class Embedder:
    """Wraps Ollama's /api/embeddings endpoint for a single embedding model."""

    def __init__(self, cfg: Config | None = None) -> None:
        self.cfg = cfg or Config.load()

    def embed(self, text: str) -> list[float]:
        """Return the embedding vector for one piece of text."""
        resp = httpx.post(
            f"{self.cfg.ollama_url}/api/embeddings",
            json={"model": self.cfg.model_embed, "prompt": text},
            timeout=120.0,
        )
        resp.raise_for_status()
        vec = resp.json()["embedding"]
        if len(vec) != self.cfg.embed_dim:
            raise ValueError(
                f"embedding dim {len(vec)} != configured EMBED_DIM {self.cfg.embed_dim}; "
                "update EMBED_DIM and the vector(N) columns to match MODEL_EMBED"
            )
        return vec

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]
