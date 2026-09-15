"""End-to-end vector search (Phase 3, -m ollama tier).

Needs BOTH a live Postgres and a live Ollama with MODEL_EMBED pulled. Skips
cleanly otherwise, so this never blocks the offline or -m db tiers.
"""
import uuid

import pytest

from living_brain.capture import capture_text
from living_brain.retrieval import hybrid_search

pytestmark = [pytest.mark.ollama, pytest.mark.db]

_NOTE = """# Vacation planning

We are considering a trip to the coast in late summer, somewhere quiet with good
seafood and a short drive from the airport.
"""


def test_vector_signal_surfaces_semantic_match(db_conn, embedder):
    src = f"test://{uuid.uuid4()}"
    # embed=True populates chunk.embedding via Ollama.
    capture_text(db_conn, _NOTE, title="vacation", source=src, embed=True)
    # a paraphrase with no lexical overlap should still surface via the vector signal
    hits = hybrid_search(db_conn, "beach holiday by the ocean", k=5, embedder=embedder)
    assert hits, "expected a semantic hit from the vector signal"
    assert any("vector" in h.signals for h in hits)
