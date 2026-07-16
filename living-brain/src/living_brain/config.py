"""Configuration loading.

Reads a .env file (simple KEY=VALUE parser, no third-party deps) layered under
real environment variables, and exposes a typed Config object. Every setting has
a default so the app runs with an empty or missing .env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Project root = two levels up from this file (src/living_brain/config.py -> project root).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict. Ignores comments and blank lines."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            values[key] = val
    return values


def _resolve(path_str: str) -> Path:
    """Resolve a possibly-relative path against the project root."""
    p = Path(path_str)
    return p if p.is_absolute() else (PROJECT_ROOT / p)


@dataclass(frozen=True)
class Config:
    db_path: Path
    notes_dir: Path
    reports_dir: Path
    ollama_url: str
    embed_model: str
    llm_model: str
    embed_dim: int
    chunk_size: int
    chunk_overlap: int
    ollama_timeout: float

    @classmethod
    def load(cls) -> "Config":
        # Real environment variables win over .env file values.
        dotenv = _load_dotenv(PROJECT_ROOT / ".env")

        def get(key: str, default: str) -> str:
            return os.environ.get(key, dotenv.get(key, default))

        return cls(
            db_path=_resolve(get("LB_DB_PATH", "data/brain.db")),
            notes_dir=_resolve(get("LB_NOTES_DIR", "data/notes")),
            reports_dir=_resolve(get("LB_REPORTS_DIR", "data/reports")),
            ollama_url=get("LB_OLLAMA_URL", "http://localhost:11434").rstrip("/"),
            embed_model=get("LB_EMBED_MODEL", "nomic-embed-text"),
            llm_model=get("LB_LLM_MODEL", "qwen2.5:14b"),
            embed_dim=int(get("LB_EMBED_DIM", "256")),
            chunk_size=int(get("LB_CHUNK_SIZE", "800")),
            chunk_overlap=int(get("LB_CHUNK_OVERLAP", "120")),
            ollama_timeout=float(get("LB_OLLAMA_TIMEOUT", "5")),
        )
