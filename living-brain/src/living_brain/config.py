"""Configuration loading. Reads a .env file (if present) then the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dependency)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Do not clobber values already set in the real environment.
        os.environ.setdefault(key, value)


_load_dotenv(PROJECT_ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    database_url: str = os.environ.get("DATABASE_URL", "sqlite:///./data/brain.db")
    ollama_host: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    embed_model: str = os.environ.get("EMBED_MODEL", "nomic-embed-text")
    llm_model: str = os.environ.get("LLM_MODEL", "qwen2.5:14b")
    embed_dim: int = int(os.environ.get("EMBED_DIM", "768"))
    night_default_minutes: float = float(os.environ.get("NIGHT_DEFAULT_MINUTES", "60"))
    night_batch_size: int = int(os.environ.get("NIGHT_BATCH_SIZE", "5"))
    night_stop_when_idle: bool = _bool("NIGHT_STOP_WHEN_IDLE", True)


CONFIG = Config()
