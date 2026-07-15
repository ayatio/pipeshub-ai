"""Embedding backend: Ollama (nomic-embed-text) with a deterministic fallback.

If the Ollama server is unreachable, we degrade to a local hashed bag-of-tokens
embedding so ingestion / consolidation / search still run headless (with lower
quality). The two paths share the same dimensionality (``EMBED_DIM``).
"""
from __future__ import annotations

import hashlib
import math
import re

import httpx
import numpy as np

from .config import get_settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Cache the availability probe so we do not hammer a dead endpoint per call.
_ollama_ok: bool | None = None


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _fallback_embed(text: str, dim: int) -> list[float]:
    """Deterministic hashed embedding. Shared tokens -> higher cosine."""
    vec = np.zeros(dim, dtype=np.float64)
    toks = _tokens(text)
    if not toks:
        return vec.tolist()
    for tok in toks:
        h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec.tolist()


def _ollama_available() -> bool:
    global _ollama_ok
    if _ollama_ok is not None:
        return _ollama_ok
    s = get_settings()
    try:
        r = httpx.get(f"{s.ollama_base_url}/api/tags", timeout=1.5)
        _ollama_ok = r.status_code == 200
    except Exception:  # noqa: BLE001
        _ollama_ok = False
    return _ollama_ok


def _ollama_embed(text: str) -> list[float] | None:
    s = get_settings()
    try:
        r = httpx.post(
            f"{s.ollama_base_url}/api/embeddings",
            json={"model": s.embed_model, "prompt": text},
            timeout=60,
        )
        r.raise_for_status()
        emb = r.json().get("embedding")
        if isinstance(emb, list) and emb:
            return [float(x) for x in emb]
    except Exception:  # noqa: BLE001
        return None
    return None


def embed(text: str) -> list[float]:
    dim = get_settings().embed_dim
    if _ollama_available():
        emb = _ollama_embed(text)
        if emb is not None:
            return emb
    return _fallback_embed(text, dim)


def embed_batch(texts: list[str]) -> list[list[float]]:
    return [embed(t) for t in texts]


def backend_name() -> str:
    return "ollama" if _ollama_available() else "fallback-hash"


def cosine(a, b) -> float:
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


__all__ = ["embed", "embed_batch", "cosine", "backend_name"]
