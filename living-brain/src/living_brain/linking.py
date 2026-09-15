"""Link canonical form and scoring — pure functions (BUILD-BRIEF §1.7, §5).

A candidate_link is canonicalised so a_id <= b_id, and carries a method, a score
in [0, 1], and evidence. These helpers are deterministic and unit-tested with no
DB or network; the DB layer persists what they return.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Recognised link methods (BUILD-BRIEF §5).
METHODS = ("semantic", "structural", "extracted", "shared_attr", "temporal")


@dataclass(frozen=True)
class CandidateLink:
    a_id: str
    b_id: str
    rel_type: str
    method: str
    score: float
    evidence: dict[str, Any] = field(default_factory=dict)


def canonical_pair(x: str, y: str) -> tuple[str, str]:
    """Order two entity ids so the smaller (string order) comes first.

    Guarantees a stable (a_id, b_id) for the unique constraint regardless of the
    order the two entities were discovered in.
    """
    return (x, y) if x <= y else (y, x)


def make_link(
    a: str,
    b: str,
    rel_type: str,
    method: str,
    score: float,
    evidence: dict[str, Any] | None = None,
) -> CandidateLink:
    """Build a canonical, validated CandidateLink.

    Raises ValueError for self-links, unknown methods, or out-of-range scores —
    enforcing the "no link without evidence" constitution at construction time.
    """
    if a == b:
        raise ValueError("cannot link an entity to itself")
    if method not in METHODS:
        raise ValueError(f"unknown link method: {method!r}")
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"score out of range [0,1]: {score}")
    a_id, b_id = canonical_pair(a, b)
    ev = dict(evidence or {})
    if not ev:
        raise ValueError("no link without evidence: evidence payload is empty")
    return CandidateLink(a_id, b_id, rel_type, method, float(score), ev)


def cosine_to_score(cosine: float) -> float:
    """Map a cosine similarity in [-1, 1] to a link score in [0, 1]."""
    return max(0.0, min(1.0, (cosine + 1.0) / 2.0))


def semantic_link(a: str, b: str, cosine: float, *, threshold: float = 0.75):
    """Propose a 'similar-to' link if entity-embedding cosine clears threshold.

    Returns None when below threshold (no weak links). Evidence records the raw
    cosine so a reviewer can see why.
    """
    if cosine < threshold:
        return None
    return make_link(
        a, b, "similar-to", "semantic",
        cosine_to_score(cosine),
        {"cosine": round(cosine, 4), "threshold": threshold},
    )


def shared_attr_link(a: str, b: str, attr: str, value: str):
    """Propose a link between two entities sharing a normalised attribute value."""
    return make_link(
        a, b, "shares-attr", "shared_attr",
        1.0,
        {"attr": attr, "value": value},
    )


def temporal_link(a: str, b: str, episode_id: int):
    """Propose a co-mention link: both entities named in the same episode."""
    return make_link(
        a, b, "co-occurs", "temporal",
        0.5,
        {"episode_id": episode_id},
    )
