"""DB test for the capture -> extract -> resolve wiring (Phase 4).

Injects a fake extractor (no Ollama), so this runs on the -m db tier and proves
that extracted entities are persisted with versions and mentions.
"""
import uuid

import pytest

from living_brain.capture import capture_text
from living_brain.extraction import Extraction, ExtractedEntity

pytestmark = pytest.mark.db


class _FakeExtractor:
    """Returns the same extraction for every chunk (deterministic wiring test)."""

    def __init__(self, entities):
        self._entities = entities

    def extract(self, text):  # noqa: ARG002 - fixed output regardless of text
        return Extraction(entities=self._entities, relationships=[])


def test_capture_with_extractor_persists_entities(db_conn):
    m = uuid.uuid4().hex
    ents = [
        ExtractedEntity(type="person", label=f"Sarah Chen {m}", aliases=[f"Sarah {m}"]),
        ExtractedEntity(type="project", label=f"Atlas {m}", props={"status": "active"}),
    ]
    note = f"# Kickoff {m}\n\nSarah Chen kicked off Atlas.\n"
    res = capture_text(
        db_conn, note, title="k", source=f"test://{m}", extractor=_FakeExtractor(ents)
    )
    assert res.created is True
    assert res.entity_count == 2

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM entity_mention WHERE episode_id = %s", (res.episode_id,)
        )
        assert cur.fetchone()[0] == 2
        # each resolved entity has exactly one open version
        cur.execute(
            "SELECT count(*) FROM entity_version ev "
            "JOIN entity_mention em ON em.entity_id = ev.entity_id "
            "WHERE em.episode_id = %s AND ev.valid_to IS NULL",
            (res.episode_id,),
        )
        assert cur.fetchone()[0] == 2
        # alias resolves back to the person entity
        cur.execute("SELECT entity_id FROM entity_alias WHERE alias = %s", (f"Sarah {m}",))
        assert cur.fetchone() is not None
