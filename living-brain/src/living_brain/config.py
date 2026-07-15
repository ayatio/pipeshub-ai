"""Configuration loading.

Reads a `.env` file (simple KEY=VALUE format) from the current working
directory if present, then overlays real environment variables. No third-party
dependency required.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Populate os.environ from a .env file without overriding real env vars."""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # `export FOO=bar` is tolerated.
        if key.startswith("export "):
            key = key[len("export "):].strip()
        os.environ.setdefault(key, value)


def _get(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Config:
    db_path: str
    ollama_url: str
    embed_model: str
    llm_model: str
    embed_dim: int
    fallback_embed_dim: int
    top_k: int
    cluster_threshold: float
    duplicate_threshold: float
    fallback_cluster_threshold: float
    fallback_duplicate_threshold: float
    decay_half_life_days: float
    importance_floor: float
    log_level: str


def load_config() -> Config:
    _load_dotenv()
    return Config(
        db_path=_get("LB_DB_PATH", "./data/brain.db"),
        ollama_url=_get("LB_OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        embed_model=_get("LB_EMBED_MODEL", "nomic-embed-text"),
        llm_model=_get("LB_LLM_MODEL", "qwen2.5:14b"),
        embed_dim=_get_int("LB_EMBED_DIM", 768),
        fallback_embed_dim=_get_int("LB_FALLBACK_EMBED_DIM", 256),
        top_k=_get_int("LB_TOP_K", 5),
        cluster_threshold=_get_float("LB_CLUSTER_THRESHOLD", 0.72),
        duplicate_threshold=_get_float("LB_DUPLICATE_THRESHOLD", 0.95),
        fallback_cluster_threshold=_get_float("LB_FALLBACK_CLUSTER_THRESHOLD", 0.24),
        fallback_duplicate_threshold=_get_float("LB_FALLBACK_DUPLICATE_THRESHOLD", 0.85),
        decay_half_life_days=_get_float("LB_DECAY_HALF_LIFE_DAYS", 14.0),
        importance_floor=_get_float("LB_IMPORTANCE_FLOOR", 0.05),
        log_level=_get("LB_LOG_LEVEL", "INFO").upper(),
    )
