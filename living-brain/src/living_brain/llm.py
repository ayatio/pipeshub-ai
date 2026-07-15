"""Summarisation / reasoning with an Ollama backend and extractive fallback.

When Ollama (``qwen2.5:14b``) is reachable it is asked to synthesise an insight
from a cluster of related memories. Otherwise a lightweight extractive
summariser picks the most representative sentences so consolidation still
produces useful output offline.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from . import ollama_client
from .config import Config

log = logging.getLogger("living_brain.llm")

_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[a-zA-Z0-9']+")

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "of", "to", "in", "on",
    "for", "with", "at", "by", "from", "is", "are", "was", "were", "be", "been",
    "it", "its", "this", "that", "these", "those", "i", "you", "we", "they",
    "he", "she", "my", "our", "your", "their", "as", "so", "not", "no", "do",
    "did", "have", "has", "had", "will", "would", "can", "could", "should",
}


def _sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENT_RE.split(text) if s.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def _extractive_summary(texts: list[str], max_sentences: int = 3) -> str:
    """Rank sentences by summed term frequency and return the top few."""
    corpus = " ".join(texts)
    words = [w.lower() for w in _WORD_RE.findall(corpus) if w.lower() not in _STOPWORDS]
    freq = Counter(words)
    if not freq:
        return texts[0][:200] if texts else ""

    scored: list[tuple[float, int, str]] = []
    for text in texts:
        for sent in _sentences(text):
            sw = [w.lower() for w in _WORD_RE.findall(sent) if w.lower() not in _STOPWORDS]
            if not sw:
                continue
            score = sum(freq[w] for w in sw) / (len(sw) ** 0.5)
            scored.append((score, len(scored), sent))

    scored.sort(key=lambda t: (-t[0], t[1]))
    top = [s for _, _, s in scored[:max_sentences]]
    # Preserve original ordering among the chosen sentences.
    ordered = [s for s in (sent for t in texts for sent in _sentences(t)) if s in top]
    seen: set[str] = set()
    result = []
    for s in ordered:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return " ".join(result)


_PROMPT = """You are the consolidation engine of a personal "second brain".
Below are several related memories captured during the day. Write ONE concise
insight (1-2 sentences) that synthesises the common theme, pattern, or takeaway.
Do not add a preamble; output only the insight.

Memories:
{items}

Insight:"""


class Summarizer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._ollama_ok: bool | None = None

    def _ollama_available(self) -> bool:
        if self._ollama_ok is None:
            self._ollama_ok = ollama_client.is_available(self.cfg.ollama_url)
            if not self._ollama_ok:
                log.info(
                    "Ollama not reachable at %s — using extractive summariser.",
                    self.cfg.ollama_url,
                )
        return self._ollama_ok

    def synthesize(self, texts: list[str]) -> tuple[str, str]:
        """Return (insight_text, backend)."""
        if self._ollama_available():
            items = "\n".join(f"- {t}" for t in texts)
            prompt = _PROMPT.format(items=items)
            out = ollama_client.generate(self.cfg.ollama_url, self.cfg.llm_model, prompt)
            if out:
                return out.strip(), "ollama"
            log.warning("Ollama generate failed; using extractive summary.")
        return _extractive_summary(texts), "fallback"
