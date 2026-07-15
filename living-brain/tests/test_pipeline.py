"""End-to-end tests for the Living Brain, using the offline fallback backend.

These do not require Ollama: with the service unreachable the store uses the
deterministic hash embedder and the extractive summariser, so the full
ingest -> search -> consolidate -> brief pipeline is exercised deterministically.
"""

from __future__ import annotations

import os

import pytest

from living_brain.config import load_config
from living_brain.consolidate import Consolidator, morning_brief
from living_brain.db import ensure_db, migrate, migration_status
from living_brain.memory import MemoryStore
from living_brain.seed import seed_if_empty


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    db = tmp_path / "brain.db"
    monkeypatch.setenv("LB_DB_PATH", str(db))
    # Point Ollama at a dead port so the fallback path is used deterministically.
    monkeypatch.setenv("LB_OLLAMA_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("LB_DECAY_HALF_LIFE_DAYS", "14")
    c = load_config()
    ensure_db(c.db_path)
    migrate(c.db_path)
    return c


def test_migrations_apply(cfg):
    status = migration_status(cfg.db_path)
    assert status, "expected migration files to be discovered"
    assert all(done for _, done in status), "all migrations should be applied"


def test_ingest_and_search(cfg):
    store = MemoryStore(cfg)
    store.add("The ingestion pipeline chokes on files larger than 200MB.", kind="fact")
    store.add("Grocery run: oat milk and coffee beans.", kind="task")
    store.add("nomic-embed-text produces 768-dimensional embeddings.", kind="fact")

    results = store.search("problems with the ingestion pipeline", top_k=1)
    assert results, "search should return at least one result"
    top, score = results[0]
    assert "ingestion pipeline" in top.content
    assert score > 0


def test_empty_memory_rejected(cfg):
    store = MemoryStore(cfg)
    with pytest.raises(ValueError):
        store.add("   ")


def test_seed_is_idempotent(cfg):
    assert seed_if_empty(cfg) > 0
    assert seed_if_empty(cfg) == 0  # second call does nothing


def test_night_produces_insights(cfg):
    seed_if_empty(cfg)
    summary = Consolidator(cfg).run(duration_s=5.0)
    assert summary["memories_seen"] > 0
    assert summary["cycles"] >= 1
    # The seed set contains several clearly-related clusters (ingestion, sleep,
    # ollama facts), so the extractive summariser should yield >= 1 insight.
    assert summary["insights_created"] >= 1

    brief = morning_brief(cfg)
    assert brief["insights"], "morning brief should contain insights"
    assert brief["last_run"]["notes"] == "ok"


def test_night_on_empty_brain_is_safe(cfg):
    summary = Consolidator(cfg).run(duration_s=2.0)
    assert summary["memories_seen"] == 0
    assert summary["insights_created"] == 0
