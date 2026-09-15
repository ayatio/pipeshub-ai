"""DB tests for type crystallisation (Phase 6, no LLM)."""
import uuid

import pytest
from psycopg.types.json import Jsonb

from living_brain import ontology

pytestmark = pytest.mark.db


def _mk_entity(conn, eid, type_, label, props=None):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entity (id, type, label, props) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (eid, type_, label, Jsonb(props or {})),
        )


def test_type_stays_proposed_below_instance_min(db_conn):
    t = f"gadget-{uuid.uuid4().hex}"
    _mk_entity(db_conn, f"{t}/a", t, "A", {"color": "red"})
    _mk_entity(db_conn, f"{t}/b", t, "B", {"color": "blue"})
    db_conn.commit()
    rec = ontology.refresh_type(db_conn, t)
    db_conn.commit()
    assert rec["instances"] == 2
    assert rec["status"] == "proposed"  # 2 < 3


def test_type_crystallises_at_instance_min(db_conn):
    t = f"widget-{uuid.uuid4().hex}"
    for i, c in enumerate(["red", "blue", "green"]):
        _mk_entity(db_conn, f"{t}/{i}", t, f"W{i}", {"color": c, "size": "m"})
    db_conn.commit()
    rec = ontology.refresh_type(db_conn, t)
    db_conn.commit()
    assert rec["instances"] == 3
    assert rec["status"] == "crystallised"
    # shape reflects shared keys
    assert set(rec["shape"]["common_keys"]) == {"color", "size"}


def test_crystallised_is_not_demoted(db_conn):
    t = f"thing-{uuid.uuid4().hex}"
    for i in range(3):
        _mk_entity(db_conn, f"{t}/{i}", t, f"T{i}")
    db_conn.commit()
    assert ontology.refresh_type(db_conn, t)["status"] == "crystallised"
    # a subsequent refresh keeps it crystallised (monotonic)
    assert ontology.refresh_type(db_conn, t)["status"] == "crystallised"
    db_conn.commit()


def test_list_types_includes_live_counts(db_conn):
    t = f"kind-{uuid.uuid4().hex}"
    _mk_entity(db_conn, f"{t}/x", t, "X")
    db_conn.commit()
    ontology.refresh_all(db_conn)
    db_conn.commit()
    rows = {r["name"]: r for r in ontology.list_types(db_conn)}
    assert t in rows
    assert rows[t]["instances"] == 1
