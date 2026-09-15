"""DB integration tests for FTS search (Phase 3, no Ollama needed).

The vector signal is covered by the -m ollama tier; here we exercise the
FTS-only path (embedder=None), which needs only Postgres.
"""
import uuid

import pytest

from living_brain.capture import capture_text
from living_brain.retrieval import hybrid_search

pytestmark = pytest.mark.db

_NOTE = """# Pricing decision

We agreed to move Project Atlas to usage-based pricing next quarter.

## Rationale

Flat-rate pricing was leaving revenue on the table for heavy accounts.
"""


def test_fts_search_finds_captured_content(db_conn):
    src = f"test://{uuid.uuid4()}"
    capture_text(db_conn, _NOTE, title="pricing", source=src)
    hits = hybrid_search(db_conn, "usage-based pricing", k=5, embedder=None)
    assert hits, "expected at least one FTS hit"
    assert any("pricing" in h.content.lower() for h in hits)
    assert all(h.signals == ("fts",) for h in hits)  # FTS-only path
    # scores are ordered non-increasing
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_fts_search_empty_for_absent_terms(db_conn):
    src = f"test://{uuid.uuid4()}"
    capture_text(db_conn, _NOTE, title="pricing", source=src)
    hits = hybrid_search(db_conn, "zzqqxx nonexistent term", k=5, embedder=None)
    assert hits == []
