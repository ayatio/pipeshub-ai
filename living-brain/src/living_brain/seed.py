"""Sample memories so a fresh brain has something to consolidate on night one."""

from __future__ import annotations

from .config import Config
from .memory import MemoryStore

SAMPLE_MEMORIES: list[tuple[str, str, float]] = [
    ("Met Priya from the platform team; she owns the ingestion pipeline.", "note", 0.6),
    ("Priya mentioned the ingestion pipeline chokes on files larger than 200MB.", "note", 0.6),
    ("The ingestion pipeline retries failed chunks three times before giving up.", "fact", 0.5),
    ("Read a paper on memory consolidation during sleep and hippocampal replay.", "note", 0.7),
    ("Sleep replay strengthens important memories and prunes weak ones.", "fact", 0.7),
    ("Idea: build a second brain that consolidates notes overnight like sleep does.", "note", 0.9),
    ("Grocery run: oat milk, coffee beans, spinach.", "task", 0.2),
    ("Dentist appointment moved to next Thursday at 3pm.", "event", 0.4),
    ("qwen2.5:14b runs comfortably on 16GB of RAM with 4-bit quantization.", "fact", 0.5),
    ("nomic-embed-text produces 768-dimensional embeddings.", "fact", 0.5),
    ("Ollama serves an OpenAI-compatible API on port 11434 by default.", "fact", 0.5),
    ("Follow up with Priya about the 200MB ingestion limit next week.", "task", 0.6),
]


def seed_if_empty(cfg: Config) -> int:
    """Insert sample memories only if the brain currently has none. Returns count added."""
    store = MemoryStore(cfg)
    if store.counts()["active"] > 0:
        return 0
    added = 0
    for content, kind, importance in SAMPLE_MEMORIES:
        store.add(content, source="seed", kind=kind, importance=importance)
        added += 1
    return added
