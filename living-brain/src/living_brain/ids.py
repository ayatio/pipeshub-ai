"""Pure, deterministic identity helpers (BUILD-BRIEF §1.7).

No DB, no network — same input, same output. Unit-tested offline.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase ASCII slug: 'Sarah Chen!' -> 'sarah-chen'."""
    norm = unicodedata.normalize("NFKD", text)
    ascii_text = norm.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", ascii_text.lower()).strip("-")
    return slug or "unnamed"


def entity_id(type_: str, label: str) -> str:
    """Stable entity slug id, e.g. ('person', 'Sarah Chen') -> 'person/sarah-chen'."""
    return f"{slugify(type_)}/{slugify(label)}"


def content_hash(text: str) -> str:
    """SHA-256 over normalised content — the idempotency key for episodes.

    Normalisation: strip trailing whitespace per line, collapse a trailing
    newline, so cosmetic edits that don't change meaning still re-ingest, but
    identical content is deduped.
    """
    normalised = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()
