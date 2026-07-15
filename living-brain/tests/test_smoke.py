"""End-to-end smoke tests using an isolated temporary SQLite database."""
from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture()
def brain(tmp_path, monkeypatch):
    """Point the whole package at a throwaway DB and reload config-bound modules."""
    db_file = tmp_path / "brain.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")  # force fallback
    monkeypatch.setenv("EMBED_DIM", "64")
    monkeypatch.setenv("NIGHT_STOP_WHEN_IDLE", "1")

    import living_brain.config as config
    importlib.reload(config)
    for name in ("db", "embeddings", "llm", "memory", "migrate", "night"):
        importlib.reload(importlib.import_module(f"living_brain.{name}"))

    from living_brain import db, memory, migrate, night

    migrate.run_migrations()
    return {"db": db, "memory": memory, "night": night}


def test_migrations_apply_once(brain):
    from living_brain import migrate

    # Re-running is a no-op.
    assert migrate.run_migrations() == []


def test_remember_and_recall(brain):
    db, memory = brain["db"], brain["memory"]
    with db.Database() as conn:
        memory.remember(conn, "the cat sat on the mat")
        memory.remember(conn, "quarterly revenue grew twelve percent")
    with db.Database() as conn:
        hits = memory.recall(conn, "revenue growth", k=1)
    assert hits
    assert "revenue" in hits[0]["content"]


def test_night_consolidates_and_converges(brain):
    db, memory, night = brain["db"], brain["memory"], brain["night"]
    with db.Database() as conn:
        for i in range(6):
            memory.remember(conn, f"observation number {i} about consolidation")

    summary = night.run_night(minutes=1, batch_size=3, log=lambda *_: None)

    assert summary["status"] == "converged"
    assert summary["insights_created"] >= 1
    assert summary["memories_consolidated"] == 6
    # Offline env => degraded mode.
    assert summary["mode"] == "degraded"

    with db.Database() as conn:
        assert memory.pending_count(conn) == 0
        s = memory.stats(conn)
    assert s["insights"] >= 1
    assert s["pending"] == 0


def test_night_on_empty_brain_is_noop(brain):
    night = brain["night"]
    summary = night.run_night(minutes=1, batch_size=5, log=lambda *_: None)
    assert summary["status"] == "converged"
    assert summary["cycles"] == 0
