"""Small shared helpers: time, vector (de)serialisation, math."""

from __future__ import annotations

import math
import struct
from datetime import datetime, timezone


def now_iso() -> str:
    """UTC timestamp in ISO-8601, seconds precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def pack_vector(vec: list[float]) -> bytes:
    """Serialise a float vector as little-endian float32 for BLOB storage."""
    return struct.pack("<%sf" % len(vec), *vec)


def unpack_vector(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack("<%sf" % n, blob))


def l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. Assumes equal length; returns 0 on mismatch."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
