"""End-to-end MCP tool tests against the isolated test DB (Phase 7 DoD).

Points the server's config at the test database and drives the tools the way a
client would (call_tool), proving capture -> search -> entity work over MCP.
No Ollama needed: capture runs without extraction, search uses the FTS path.
"""
import dataclasses

import pytest

from living_brain.config import Config
from living_brain.mcp_server import build_server

pytestmark = pytest.mark.db


def _result(call_result):
    assert call_result.is_error is False, call_result
    sc = call_result.structured_content
    if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
        return sc["result"]
    return sc


@pytest.fixture
def server(test_db_url, db_conn):  # db_conn ensures a clean, migrated schema
    cfg = dataclasses.replace(Config.load(), database_url=test_db_url)
    return build_server(cfg)


async def test_capture_then_search_over_mcp(server):
    note = "# Pricing\n\nWe moved Atlas to usage-based pricing this quarter.\n"
    cap = _result(await server.call_tool("capture", {"text": note, "title": "pricing"}))
    assert cap["created"] is True
    assert cap["chunks"] >= 1

    hits = _result(await server.call_tool("search", {"query": "usage-based pricing", "k": 5}))
    assert hits, "expected an FTS hit via MCP search"
    assert any("pricing" in h["content"].lower() for h in hits)


async def test_entity_and_relate_tools(server, db_conn):
    # seed two linked entities directly, then read them back through the tools
    from psycopg.types.json import Jsonb

    from living_brain import links as L

    with db_conn.cursor() as cur:
        for eid, label in [("person/sarah", "Sarah"), ("project/atlas", "Atlas")]:
            cur.execute(
                "INSERT INTO entity (id, type, label, props) VALUES (%s, %s, %s, %s)",
                (eid, eid.split("/")[0], label, Jsonb({})),
            )
    L.add_extracted_link(db_conn, "person/sarah", "project/atlas", "works-on",
                         "Sarah leads Atlas", 1)
    db_conn.commit()

    ent = _result(await server.call_tool("entity", {"entity_id": "person/sarah"}))
    assert ent["label"] == "Sarah"

    rels = _result(await server.call_tool(
        "relate", {"a": "person/sarah", "b": "project/atlas"}
    ))
    assert rels[0]["rel_type"] == "works-on"
    assert rels[0]["method"] == "extracted"

    nbrs = _result(await server.call_tool("neighbors", {"entity_id": "person/sarah"}))
    assert any(n["id"] == "project/atlas" for n in nbrs)
