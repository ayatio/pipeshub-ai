"""DB integration tests for capture (BUILD-BRIEF Phase 2 DoD).

Run with `uv run pytest -m db` after `make db && make migrate`. Skipped when no
Postgres is reachable.
"""
import uuid

import pytest

from living_brain.capture import capture_text

pytestmark = pytest.mark.db

_NOTE = """# Atlas kickoff

Sarah Chen kicked off Project Atlas.

## Decisions

- We chose Postgres + pgvector.
"""


def _count(conn, table, episode_id):
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table} WHERE episode_id = %s", (episode_id,))
        return cur.fetchone()[0]


def test_capture_creates_episode_and_chunks(db_conn):
    src = f"test://{uuid.uuid4()}"
    res = capture_text(db_conn, _NOTE, title="atlas", source=src)
    assert res.created is True
    assert res.episode_id is not None
    assert res.chunk_count >= 2  # at least the two headings
    assert _count(db_conn, "chunk", res.episode_id) == res.chunk_count


def test_capture_is_idempotent_by_content_hash(db_conn):
    src = f"test://{uuid.uuid4()}"
    first = capture_text(db_conn, _NOTE, title="atlas", source=src)
    second = capture_text(db_conn, _NOTE, title="atlas", source=src)
    assert first.created is True
    assert second.created is False
    assert second.episode_id == first.episode_id
    assert second.chunk_count == 0
    # still exactly one episode's worth of chunks
    assert _count(db_conn, "chunk", first.episode_id) == first.chunk_count


def test_whitespace_only_change_is_still_same_episode(db_conn):
    src = f"test://{uuid.uuid4()}"
    first = capture_text(db_conn, _NOTE, source=src)
    # trailing whitespace per line is normalised in the content hash
    padded = "\n".join(line + "   " for line in _NOTE.splitlines())
    again = capture_text(db_conn, padded, source=src)
    assert again.created is False
    assert again.episode_id == first.episode_id
