"""DB integration tests for entity resolution + versioning (Phase 4, no LLM).

Resolution is deterministic/DB-driven, so it is fully testable without Ollama.
"""
import uuid

import pytest

from living_brain import resolution as R

pytestmark = pytest.mark.db


def _fresh_episode(conn, marker):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO episode (content, content_hash, source) "
            "VALUES (%s, %s, %s) RETURNING id",
            (f"note {marker}", f"h-{marker}", f"test://{marker}"),
        )
        return cur.fetchone()[0]


def test_mint_then_reuse_by_exact_label(db_conn):
    m = uuid.uuid4().hex
    label = f"Sarah Chen {m}"
    eid, created = R.resolve_entity(db_conn, "person", label)
    assert created is True
    R.upsert_entity(db_conn, eid, "person", label, {"role": "eng"})
    db_conn.commit()
    # second resolution finds the same entity (exact slug/alias), not a new one
    eid2, created2 = R.resolve_entity(db_conn, "person", label)
    assert created2 is False
    assert eid2 == eid


def test_alias_resolves_to_same_entity(db_conn):
    m = uuid.uuid4().hex
    label = f"Project Atlas {m}"
    eid, _ = R.resolve_entity(db_conn, "project", label)
    R.upsert_entity(db_conn, eid, "project", label, {}, aliases=[f"Atlas {m}"])
    db_conn.commit()
    hit, created = R.resolve_entity(db_conn, "project", f"Atlas {m}")
    assert created is False
    assert hit == eid


def test_trigram_matches_near_duplicate(db_conn):
    m = uuid.uuid4().hex
    label = f"Acme Corporation {m}"
    eid, _ = R.resolve_entity(db_conn, "org", label)
    R.upsert_entity(db_conn, eid, "org", label, {})
    db_conn.commit()
    # a small typo should resolve to the existing entity via trigram similarity
    hit, created = R.resolve_entity(db_conn, "org", f"Acme Corporaton {m}")
    assert created is False
    assert hit == eid


def test_versioning_is_append_only_and_change_gated(db_conn):
    m = uuid.uuid4().hex
    ep = _fresh_episode(db_conn, m)
    label = f"Sarah {m}"
    eid, _ = R.resolve_entity(db_conn, "person", label)
    R.upsert_entity(db_conn, eid, "person", label, {"role": "eng"})

    assert R.append_version_if_changed(db_conn, eid, "person", label, {"role": "eng"}, episode_id=ep) is True
    # identical fact → no new version
    assert R.append_version_if_changed(db_conn, eid, "person", label, {"role": "eng"}, episode_id=ep) is False
    # changed props → a new version, and exactly one open version remains
    assert R.append_version_if_changed(db_conn, eid, "person", label, {"role": "lead"}, episode_id=ep) is True
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM entity_version WHERE entity_id=%s", (eid,))
        assert cur.fetchone()[0] == 2
        cur.execute(
            "SELECT count(*) FROM entity_version WHERE entity_id=%s AND valid_to IS NULL",
            (eid,),
        )
        assert cur.fetchone()[0] == 1


def test_record_mention_is_idempotent(db_conn):
    m = uuid.uuid4().hex
    ep = _fresh_episode(db_conn, m)
    label = f"Michel {m}"
    eid, _ = R.resolve_entity(db_conn, "person", label)
    R.upsert_entity(db_conn, eid, "person", label, {})
    R.record_mention(db_conn, eid, ep)
    R.record_mention(db_conn, eid, ep)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM entity_mention WHERE entity_id=%s AND episode_id=%s",
            (eid, ep),
        )
        assert cur.fetchone()[0] == 1
