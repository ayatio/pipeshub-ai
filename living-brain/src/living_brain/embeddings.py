"""Text embeddings via Ollama (nomic-embed-text), with an offline fallback.

If the Ollama server is reachable we use the real model. Otherwise we fall back
to a deterministic hashing embedding so that ingestion, similarity search and
the nightly loop all keep working end-to-end (in DEGRADED mode).
"""
from __future__ import annotations

import hashlib
import math
import struct

import httpx

from .config import CONFIG

# Module-level flag so callers can report whether real models were used.
LAST_EMBED_DEGRADED = False


def _hash_embed(text: str, dim: int) -> list[float]:
    """Deterministic, dependency-free embedding.

    Buckets token hashes into `dim` slots (a hashing trick), then L2-normalises.
    Not semantically strong, but stable and good enough to exercise the pipeline.
    """
    vec = [0.0] * dim
    tokens = text.lower().split()
    for tok in tokens:
        h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        idx = struct.unpack("<Q", h)[0] % dim
        sign = 1.0 if (idx % 2 == 0) else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def embed(text: str) -> list[float]:
    global LAST_EMBED_DEGRADED
    text = (text or "").strip()
    if not text:
        LAST_EMBED_DEGRADED = False
        return [0.0] * CONFIG.embed_dim
    try:
        resp = httpx.post(
            f"{CONFIG.ollama_host}/api/embeddings",
            json={"model": CONFIG.embed_model, "prompt": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        emb = data.get("embedding")
        if emb:
            LAST_EMBED_DEGRADED = False
            return [float(x) for x in emb]
    except Exception:
        pass
    LAST_EMBED_DEGRADED = True
    return _hash_embed(text, CONFIG.embed_dim)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(a[i] * a[i] for i in range(n)))
    nb = math.sqrt(sum(b[i] * b[i] for i in range(n)))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
