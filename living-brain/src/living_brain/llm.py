"""Reflection LLM via Ollama (qwen2.5:14b), with an extractive fallback.

`reflect()` turns a cluster of related memories into a single higher-level
insight. With Ollama present it asks the model; otherwise it produces a compact
extractive summary so the nightly loop still yields useful, deterministic output.
"""
from __future__ import annotations

import re
from collections import Counter

import httpx

from .config import CONFIG

LAST_LLM_DEGRADED = False

_SYSTEM = (
    "You are the reflective subsystem of a Living Brain. Given several raw "
    "observations, distil ONE concise insight (1-2 sentences) capturing the "
    "common theme or actionable takeaway. Reply with the insight only."
)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "it", "this", "that", "these",
    "those", "i", "we", "you", "they", "he", "she", "my", "our", "your", "at",
    "as", "by", "from", "about", "into", "then", "so", "if", "not", "no",
}


def _extractive(observations: list[str]) -> str:
    """Dependency-free summariser: surface the most salient shared keywords."""
    text = " ".join(observations).lower()
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9'-]+", text)
    freq = Counter(w for w in words if w not in _STOPWORDS and len(w) > 2)
    top = [w for w, _ in freq.most_common(6)]
    lead = observations[0].strip().rstrip(".")
    if top:
        return f"Recurring theme around {', '.join(top[:4])}. Anchored by: {lead}."
    return f"Consolidated note: {lead}."


def reflect(observations: list[str]) -> str:
    global LAST_LLM_DEGRADED
    observations = [o for o in observations if o and o.strip()]
    if not observations:
        LAST_LLM_DEGRADED = False
        return ""
    prompt = _SYSTEM + "\n\nObservations:\n" + "\n".join(
        f"- {o.strip()}" for o in observations
    )
    try:
        resp = httpx.post(
            f"{CONFIG.ollama_host}/api/generate",
            json={"model": CONFIG.llm_model, "prompt": prompt, "stream": False},
            timeout=120.0,
        )
        resp.raise_for_status()
        out = (resp.json().get("response") or "").strip()
        if out:
            LAST_LLM_DEGRADED = False
            return out
    except Exception:
        pass
    LAST_LLM_DEGRADED = True
    return _extractive(observations)
