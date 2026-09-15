"""Live extraction over Ollama (Phase 4, -m ollama tier). Skips without Ollama."""
import pytest

from living_brain.config import Config
from living_brain.extraction import Extractor

pytestmark = pytest.mark.ollama


def test_extractor_returns_entities_from_a_clear_note():
    cfg = Config.load()
    ex = Extractor(cfg)
    try:
        result = ex.extract(
            "Sarah Chen is the engineering lead on Project Atlas. "
            "Michel is the executive sponsor."
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no Ollama extraction available: {exc}")
    labels = " ".join(e.label.lower() for e in result.entities)
    # a capable local model should surface at least the two people / the project
    assert result.entities, "expected some entities"
    assert "sarah" in labels or "atlas" in labels or "michel" in labels
