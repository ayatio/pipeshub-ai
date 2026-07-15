"""End-to-end pipeline test on an isolated temporary SQLite brain."""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


@pytest.fixture()
def brain(tmp_path, monkeypatch):
    db_path = tmp_path / "brain.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EMBED_DIM", "64")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:1")  # force fallback
    monkeypatch.setenv("THEME_MIN_CLUSTER", "2")
    # Fallback embeddings on tiny test text produce low absolute similarities;
    # relax the link threshold so the linking mechanism is exercised.
    monkeypatch.setenv("LINK_MIN_SIM", "0.05")

    # Reload modules so cached settings pick up the temp env.
    import living_brain.config as config
    config.get_settings.cache_clear()
    for name in ["db", "store", "migrate", "embeddings", "llm",
                 "consolidate", "ingest", "search", "night"]:
        importlib.reload(importlib.import_module(f"living_brain.{name}"))
    import living_brain.migrate as migrate
    migrate.run()
    return tmp_path


def test_embed_fallback_dim_and_similarity():
    from living_brain import embeddings
    a = embeddings.embed("sleep and memory consolidation")
    b = embeddings.embed("memory consolidation during sleep")
    c = embeddings.embed("postgres vector index tuning")
    assert len(a) == 64 or len(a) == 768  # dim from env or default
    assert embeddings.cosine(a, b) > embeddings.cosine(a, c)


def test_migrations_idempotent(brain):
    from living_brain import migrate
    assert migrate.run() == 0  # already applied in fixture


def test_ingest_creates_memories(brain):
    from living_brain import ingest, store
    ids = ingest.ingest_text(
        "First idea about sleep.\n\nSecond idea about memory.", source="t"
    )
    assert len(ids) == 2
    assert store.counts()["memories"] == 2


def test_night_run_embeds_links_and_search(brain):
    from living_brain import ingest, night, store, search

    ingest.ingest_text(
        "Sleep replays memories to consolidate them.\n\n"
        "Deep sleep strengthens what you learned that day.\n\n"
        "Spaced repetition fights the forgetting curve through recall.",
        source="notes",
    )
    assert store.counts()["embedded"] == 0

    result = night.run_night(5, verbose=False)
    c = store.counts()
    assert c["embedded"] == c["memories"] == 3
    assert c["links"] >= 1
    assert c["night_runs"] == 1
    assert result["cycles"] >= 1

    hits = search.search("how does sleep help memory", top_k=2)
    assert hits
    assert hits[0].score >= hits[-1].score  # ranked


def test_insight_created_for_cluster(brain):
    from living_brain import ingest, night, store
    # three near-identical memories -> a cluster -> a theme insight
    ingest.ingest_text(
        "Cats are small domestic felines that purr.\n\n"
        "Domestic cats are small felines kept as pets.\n\n"
        "A house cat is a small feline companion animal.",
        source="cats",
    )
    night.run_night(5, verbose=False)
    assert store.counts()["insights"] >= 1
