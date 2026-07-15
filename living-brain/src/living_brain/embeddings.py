"""Embeddings with an Ollama backend and a deterministic local fallback.

When Ollama (``nomic-embed-text``) is reachable it is used. Otherwise a
hashing-based bag-of-words embedder produces stable vectors so that lexical
overlap still yields meaningful cosine similarity and the whole pipeline keeps
working offline.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

from . import ollama_client
from .config import Config
from .util import l2_normalize

log = logging.getLogger("living_brain.embeddings")

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _hash_embed(text: str, dim: int) -> list[float]:
    """Deterministic bag-of-words hashing embedding (feature hashing)."""
    vec = [0.0] * dim
    for tok in _tokens(text):
        h = hashlib.md5(tok.encode("utf-8")).digest()  # noqa: S324 — not security
        idx = int.from_bytes(h[:4], "little") % dim
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign
    return l2_normalize(vec)


@dataclass
class EmbedResult:
    vector: list[float]
    model: str
    dim: int
    backend: str  # "ollama" | "fallback"


class Embedder:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._ollama_ok: bool | None = None

    def _ollama_available(self) -> bool:
        if self._ollama_ok is None:
            self._ollama_ok = ollama_client.is_available(self.cfg.ollama_url)
            if not self._ollama_ok:
                log.info(
                    "Ollama not reachable at %s — using local fallback embedder.",
                    self.cfg.ollama_url,
                )
        return self._ollama_ok

    def embed(self, text: str) -> EmbedResult:
        if self._ollama_available():
            vec = ollama_client.embed(self.cfg.ollama_url, self.cfg.embed_model, text)
            if vec:
                return EmbedResult(
                    vector=l2_normalize(vec),
                    model=self.cfg.embed_model,
                    dim=len(vec),
                    backend="ollama",
                )
            # A single failure shouldn't permanently flip us to fallback, but do
            # note it and serve this call from the fallback embedder.
            log.warning("Ollama embed call failed; using fallback for this item.")
        dim = self.cfg.fallback_embed_dim
        return EmbedResult(
            vector=_hash_embed(text, dim),
            model=f"fallback-hash-{dim}",
            dim=dim,
            backend="fallback",
        )
