"""Text embeddings.

Primary path: Ollama's /api/embeddings endpoint (e.g. nomic-embed-text).
Fallback path: a deterministic, dependency-free hashing embedder so the whole
pipeline still works with no model server and no network access.

The fallback is a signed feature-hashing bag-of-words vector with L2
normalization — good enough for nearest-neighbour retrieval on a small personal
corpus, and completely reproducible.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.error
import urllib.request
from typing import List

from .config import Config

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


def _hash_embed(text: str, dim: int) -> List[float]:
    """Signed feature-hashing embedding (offline fallback)."""
    vec = [0.0] * dim
    for tok in _tokenize(text):
        h = hashlib.md5(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if (h[4] & 1) else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _ollama_embed(cfg: Config, text: str) -> List[float]:
    """Call Ollama. Raises on any failure so callers can fall back."""
    payload = json.dumps({"model": cfg.embed_model, "prompt": text}).encode()
    req = urllib.request.Request(
        f"{cfg.ollama_url}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=cfg.ollama_timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    emb = data.get("embedding")
    if not emb:
        raise ValueError("Ollama returned no embedding")
    return [float(x) for x in emb]


class Embedder:
    """Embeds text, preferring Ollama and degrading to the hash fallback.

    The choice is made once (on first use) and cached, so we don't hammer a
    dead socket for every chunk.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._use_ollama: bool | None = None
        self.backend = "unknown"

    def _probe(self, sample: str) -> None:
        try:
            _ollama_embed(self.cfg, sample or "probe")
            self._use_ollama = True
            self.backend = f"ollama:{self.cfg.embed_model}"
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            self._use_ollama = False
            self.backend = f"hash-fallback:dim{self.cfg.embed_dim}"

    def embed(self, text: str) -> List[float]:
        if self._use_ollama is None:
            self._probe(text)
        if self._use_ollama:
            try:
                return _ollama_embed(self.cfg, text)
            except (urllib.error.URLError, OSError, ValueError, TimeoutError):
                # Server died mid-run: fall back permanently.
                self._use_ollama = False
                self.backend = f"hash-fallback:dim{self.cfg.embed_dim}"
        return _hash_embed(text, self.cfg.embed_dim)


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
