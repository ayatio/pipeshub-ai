"""Runtime configuration, loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = Field(default="sqlite:///./data/living_brain.db")

    ollama_base_url: str = Field(default="http://localhost:11434")
    embed_model: str = Field(default="nomic-embed-text")
    llm_model: str = Field(default="qwen2.5:14b")
    embed_dim: int = Field(default=768)

    link_top_k: int = Field(default=5)
    link_min_sim: float = Field(default=0.35)
    importance_decay: float = Field(default=0.98)
    theme_min_cluster: int = Field(default=3)

    notes_dir: str = Field(default="./data/notes")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgres://", "postgresql://"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
