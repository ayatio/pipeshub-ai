"""Configuration loaded from environment / .env.

Local-first defaults (BUILD-BRIEF §1.6): everything points at localhost. A .env
is loaded if present, but real environment variables win over it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency). Existing env vars take precedence."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv(_REPO_ROOT / ".env")


@dataclass(frozen=True)
class Config:
    database_url: str
    vault_path: Path
    ollama_url: str
    model_embed: str
    model_extract: str
    embed_dim: int
    extract_fallback: str
    openai_api_key: str
    anthropic_api_key: str
    mcp_port: int
    mcp_token: str

    @staticmethod
    def load() -> "Config":
        return Config(
            database_url=os.environ.get(
                "DATABASE_URL", "postgresql://brain:brain@localhost:5433/brain"
            ),
            vault_path=Path(os.environ.get("VAULT_PATH", "./vault")).expanduser(),
            ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
            model_embed=os.environ.get("MODEL_EMBED", "nomic-embed-text"),
            model_extract=os.environ.get("MODEL_EXTRACT", "qwen2.5:14b"),
            embed_dim=int(os.environ.get("EMBED_DIM", "768")),
            extract_fallback=os.environ.get("EXTRACT_FALLBACK", ""),
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            mcp_port=int(os.environ.get("MCP_PORT", "8848")),
            mcp_token=os.environ.get("MCP_TOKEN", "change-me"),
        )
