"""DB integration tests for link generation and relate (Phase 5, no LLM).

Entities/mentions/props are inserted directly (or via the injected-extractor
capture path), so these run on the -m db tier without Ollama.
"""
import uuid

import pytest
from psycopg.types.json import Jsonb

from living_brain import links as L

pytestmark = pytest.mark.db


def _mk_entity(conn, eid, type_, label, props=None, embedding=None):
    from living_brain.embedding import to_pgvector
    emb = to_pgvector(embedding) if embedding else None
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entity (id, type, label, props, embedding) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (eid, type_, label, Jsonb(props or {}), emb),
        )
        cur.execute(
            "INSERT INTO entity_alias (entity_id, alias) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (eid, label),
        )


def _mk_episode(conn, marker):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO episode (content, content_hash, source) "
            "VALUES (%s, %s, %s) RETURNING id",
            ("x", f"h-{marker}", f"test://{marker}"),
        )
        return cur.fetchone()[0]


def test_co_mention_links_and_relate(db_conn):
    m = uuid.uuid4().hex
    ep = _mk_episode(db_conn, m)
    a, b = f"person/a-{m}", f"person/b-{m}"
    _mk_entity(db_conn, a, "person", f"A {m}")
    _mk_entity(db_conn, b, "person", f"B {m}")
    with db_conn.cursor() as cur:
        for eid in (a, b):
            cur.execute(
                "INSERT INTO entity_mention (entity_id, episode_id) VALUES (%s, %s)",
                (eid, ep),
            )
    n = L.generate_co_mention_links(db_conn, ep)
    db_conn.commit()
    assert n == 1
    rels = L.relate(db_conn, b, a)  # order-independent (canonicalised)
    assert len(rels) == 1
    assert rels[0]["method"] == "temporal"
    assert rels[0]["status"] == "proposed"
    assert rels[0]["evidence"]["episode_id"] == ep


def test_shared_attr_links(db_conn):
    m = uuid.uuid4().hex
    a, b = f"person/x-{m}", f"person/y-{m}"
    _mk_entity(db_conn, a, "person", f"X {m}", props={"employer": f"Acme {m}"})
    _mk_entity(db_conn, b, "person", f"Y {m}", props={"employer": f"acme {m}"})  # case-diff
    db_conn.commit()
    L.generate_shared_attr_links(db_conn)
    db_conn.commit()
    rels = L.relate(db_conn, a, b)
    assert any(r["method"] == "shared_attr" for r in rels)


def test_semantic_links_by_embedding(db_conn):
    m = uuid.uuid4().hex
    dim = 768
    near = [1.0] + [0.0] * (dim - 1)
    also_near = [0.99, 0.01] + [0.0] * (dim - 2)
    far = [0.0] * (dim - 1) + [1.0]
    a, b, c = f"c/a-{m}", f"c/b-{m}", f"c/c-{m}"
    _mk_entity(db_conn, a, "concept", f"A {m}", embedding=near)
    _mk_entity(db_conn, b, "concept", f"B {m}", embedding=also_near)
    _mk_entity(db_conn, c, "concept", f"C {m}", embedding=far)
    db_conn.commit()
    L.generate_semantic_links(db_conn, threshold=0.9)
    db_conn.commit()
    assert any(r["method"] == "semantic" for r in L.relate(db_conn, a, b))
    assert L.relate(db_conn, a, c) == []  # orthogonal → below threshold


def test_extracted_link_requires_both_endpoints(db_conn):
    m = uuid.uuid4().hex
    ep = _mk_episode(db_conn, m)
    a, b = f"person/s-{m}", f"project/atlas-{m}"
    _mk_entity(db_conn, a, "person", f"Sarah {m}")
    # b does not exist yet → no dangling link
    assert L.add_extracted_link(db_conn, a, b, "works-on", "Sarah leads Atlas", ep) is False
    _mk_entity(db_conn, b, "project", f"Atlas {m}")
    assert L.add_extracted_link(db_conn, a, b, "works-on", "Sarah leads Atlas", ep) is True
    db_conn.commit()
    rels = L.relate(db_conn, a, b)
    assert rels[0]["method"] == "extracted"
    assert "Sarah leads Atlas" in rels[0]["evidence"]["quote"]


def test_set_status_confirm(db_conn):
    m = uuid.uuid4().hex
    ep = _mk_episode(db_conn, m)
    a, b = f"person/p-{m}", f"person/q-{m}"
    _mk_entity(db_conn, a, "person", f"P {m}")
    _mk_entity(db_conn, b, "person", f"Q {m}")
    L.add_extracted_link(db_conn, a, b, "knows", "P knows Q", ep)
    L.set_status(db_conn, a, b, "knows", "confirmed", "human:tester")
    db_conn.commit()
    rels = L.relate(db_conn, a, b)
    assert rels[0]["status"] == "confirmed"
    assert rels[0]["decided_by"] == "human:tester"
