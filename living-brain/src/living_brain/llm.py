"""Summarization / generation.

Primary path: Ollama's /api/generate endpoint (e.g. qwen2.5:14b).
Fallback path: a dependency-free extractive summarizer (frequency-scored
sentence selection) so nightly consolidation still produces a readable digest
with no model server.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections import Counter
from typing import List

from .config import Config

# A small English stopword set for the extractive fallback.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "of", "to", "in",
    "on", "for", "with", "as", "is", "are", "was", "were", "be", "been",
    "it", "this", "that", "these", "those", "at", "by", "from", "into",
    "i", "you", "we", "they", "he", "she", "my", "our", "your", "their",
    "so", "not", "no", "do", "does", "did", "can", "will", "would", "should",
    "have", "has", "had", "there", "here", "than", "too", "very", "just",
}

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[a-zA-Z0-9']+")


def _ollama_generate(cfg: Config, prompt: str) -> str:
    payload = json.dumps(
        {"model": cfg.llm_model, "prompt": prompt, "stream": False}
    ).encode()
    req = urllib.request.Request(
        f"{cfg.ollama_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=max(cfg.ollama_timeout, 60)) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = (data.get("response") or "").strip()
    if not text:
        raise ValueError("Ollama returned empty response")
    return text


def _extractive_summary(text: str, max_sentences: int = 5) -> str:
    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    freq: Counter[str] = Counter()
    for s in sentences:
        for w in _WORD_RE.findall(s.lower()):
            if w not in _STOPWORDS and len(w) > 2:
                freq[w] += 1
    if not freq:
        return " ".join(sentences[:max_sentences])

    top = freq.most_common(1)[0][1]
    scored = []
    for idx, s in enumerate(sentences):
        words = [w for w in _WORD_RE.findall(s.lower()) if w in freq]
        score = sum(freq[w] for w in words) / (len(words) or 1)
        scored.append((score / top, idx, s))

    chosen = sorted(scored, reverse=True)[:max_sentences]
    chosen.sort(key=lambda t: t[1])  # restore original order
    return " ".join(s for _, _, s in chosen)


class Summarizer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._use_ollama: bool | None = None
        self.backend = "unknown"

    def summarize(self, text: str, instruction: str = "") -> str:
        if not text.strip():
            return ""
        prompt = (
            (instruction or
             "Summarize the following notes into a concise digest of key "
             "themes and takeaways:")
            + "\n\n" + text
        )
        if self._use_ollama is not False:
            try:
                out = _ollama_generate(self.cfg, prompt)
                self._use_ollama = True
                self.backend = f"ollama:{self.cfg.llm_model}"
                return out
            except (urllib.error.URLError, OSError, ValueError, TimeoutError):
                self._use_ollama = False
        self.backend = "extractive-fallback"
        return _extractive_summary(text)


def keywords(text: str, top_n: int = 12) -> List[tuple[str, int]]:
    """Frequency-ranked keywords for theme detection (stdlib only)."""
    freq: Counter[str] = Counter()
    for w in _WORD_RE.findall(text.lower()):
        if w not in _STOPWORDS and len(w) > 2 and not w.isdigit():
            freq[w] += 1
    return freq.most_common(top_n)
