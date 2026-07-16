"""End-to-end smoke tests using a temporary database and notes dir.

Run with:  make test   (or)   python -m unittest discover -s tests
These tests never touch the network and never require Ollama.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Make src/ importable when run directly.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class LivingBrainSmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        (base / "notes").mkdir()
        (base / "reports").mkdir()
        (base / "notes" / "a.md").write_text(
            "Vector databases store embeddings for semantic search.\n\n"
            "Cosine similarity finds nearest neighbours.",
            encoding="utf-8",
        )
        (base / "notes" / "b.md").write_text(
            "Sleep consolidates memories. Embeddings and semantic search "
            "power retrieval over notes.",
            encoding="utf-8",
        )
        os.environ["LB_DB_PATH"] = str(base / "brain.db")
        os.environ["LB_NOTES_DIR"] = str(base / "notes")
        os.environ["LB_REPORTS_DIR"] = str(base / "reports")
        # Point Ollama at a dead port so we exercise the offline fallback fast.
        os.environ["LB_OLLAMA_URL"] = "http://127.0.0.1:1"
        os.environ["LB_OLLAMA_TIMEOUT"] = "1"

    def tearDown(self):
        self.tmp.cleanup()
        for k in ("LB_DB_PATH", "LB_NOTES_DIR", "LB_REPORTS_DIR",
                  "LB_OLLAMA_URL", "LB_OLLAMA_TIMEOUT"):
            os.environ.pop(k, None)

    def _cfg(self):
        from living_brain.config import Config
        return Config.load()

    def test_full_pipeline(self):
        from living_brain import db, ingest, search, consolidate

        cfg = self._cfg()

        db.init_db(cfg)
        applied = db.migrate(cfg)
        self.assertIn("001_init", applied)

        r = ingest.ingest(cfg)
        self.assertEqual(r.ingested, 2)
        self.assertGreater(r.chunks, 0)
        self.assertTrue(r.backend.startswith("hash-fallback"))

        # Re-ingest is idempotent: nothing changed.
        r2 = ingest.ingest(cfg)
        self.assertEqual(r2.ingested, 0)
        self.assertEqual(r2.unchanged, 2)

        hits = search.search(cfg, "semantic search over embeddings", top_k=3)
        self.assertTrue(hits)
        self.assertGreaterEqual(hits[0].score, hits[-1].score)

        path, body = consolidate.consolidate(cfg, stamp="test-stamp")
        self.assertTrue(Path(path).exists())
        self.assertIn("Nightly digest", body)
        self.assertIn("Dominant themes", body)

    def test_chunker(self):
        from living_brain.ingest import chunk_text
        text = "\n\n".join(f"Paragraph number {i} with some words." for i in range(20))
        chunks = chunk_text(text, size=200, overlap=40)
        self.assertTrue(all(len(c) <= 300 for c in chunks))
        self.assertGreater(len(chunks), 1)

    def test_cosine(self):
        from living_brain.embeddings import cosine
        self.assertAlmostEqual(cosine([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(cosine([1, 0], [0, 1]), 0.0)
        self.assertEqual(cosine([], [1]), 0.0)


if __name__ == "__main__":
    unittest.main()
