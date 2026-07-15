"""LLM backend: Ollama chat (qwen2.5) with a template-based fallback summarizer.

Used during night consolidation to name themes and write short syntheses. When
Ollama is unavailable we produce a deterministic extractive summary so a night
run still yields readable insights.
"""
from __future__ import annotations

import re
from collections import Counter

import httpx

from .config import get_settings

_ollama_ok: bool | None = None

_STOP = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "it", "this", "that", "these",
    "those", "i", "you", "he", "she", "they", "we", "as", "at", "by", "from",
    "so", "if", "then", "than", "into", "about", "over", "after", "before",
    "my", "your", "our", "their", "its", "not", "no", "can", "will", "just",
}
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'-]+")
_SENT_RE = re.compile(r"(?<=[.!?])\s+")


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


def _ollama_chat(prompt: str, system: str | None = None) -> str | None:
    s = get_settings()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        r = httpx.post(
            f"{s.ollama_base_url}/api/chat",
            json={"model": s.llm_model, "messages": messages, "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        return (r.json().get("message") or {}).get("content", "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def keywords(text: str, top: int = 6) -> list[str]:
    counts = Counter(
        w.lower() for w in _WORD_RE.findall(text) if w.lower() not in _STOP and len(w) > 2
    )
    return [w for w, _ in counts.most_common(top)]


def _fallback_theme(texts: list[str]) -> tuple[str, str]:
    joined = "\n".join(texts)
    kws = keywords(joined, top=6)
    title = ", ".join(kws[:3]) if kws else "untitled theme"
    # Pick the most representative sentence from each memory (first non-empty).
    picks = []
    for t in texts[:5]:
        for sent in _SENT_RE.split(t.strip()):
            sent = sent.strip()
            if len(sent) > 10:
                picks.append(f"- {sent}")
                break
    body = (
        f"Recurring theme around: {', '.join(kws) if kws else 'these notes'}.\n"
        + "\n".join(picks)
    )
    return title.title(), body


def summarize_theme(texts: list[str]) -> tuple[str, str]:
    """Return (title, body) synthesizing a cluster of related memories."""
    if _ollama_available():
        joined = "\n\n---\n\n".join(f"[{i+1}] {t}" for i, t in enumerate(texts))
        system = (
            "You are the consolidation process of a personal knowledge system, "
            "running overnight. Find the single theme connecting the notes."
        )
        prompt = (
            "Here are related memories:\n\n" + joined + "\n\n"
            "Reply with exactly two lines:\n"
            "TITLE: a 3-6 word name for the shared theme\n"
            "SUMMARY: 1-2 sentences synthesizing the connection and any insight."
        )
        out = _ollama_chat(prompt, system)
        if out:
            title, body = "Theme", out
            for line in out.splitlines():
                if line.upper().startswith("TITLE:"):
                    title = line.split(":", 1)[1].strip() or title
                elif line.upper().startswith("SUMMARY:"):
                    body = line.split(":", 1)[1].strip() or body
            return title[:120], body
    return _fallback_theme(texts)


def backend_name() -> str:
    return "ollama" if _ollama_available() else "fallback-template"


__all__ = ["summarize_theme", "keywords", "backend_name"]
