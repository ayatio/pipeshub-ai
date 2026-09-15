"""MCP server (BUILD-BRIEF §8, Phase 7).

A thin read/traverse layer over the same core functions the CLI uses. Tools:
  * brain.search    — hybrid vector+FTS search
  * brain.relate    — every link between two entities (with evidence)
  * brain.neighbors — linked neighbours of an entity (graph walk)
  * brain.entity    — an entity's snapshot + aliases + mention count
  * brain.capture   — ingest a note (extraction is opt-in; needs Ollama)

Transport: stdio by default (local-first — MCP clients spawn the server as a
subprocess, so no network token is required). Over streamable-http a bearer
token (MCP_TOKEN) is enforced by a Starlette middleware.
"""
from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from . import db, links, retrieval
from . import resolution as R
from .capture import capture_text
from .config import Config
from .embedding import Embedder


def _search_embedder(cfg: Config) -> Embedder | None:
    """Return a working embedder, or None if Ollama is unreachable (FTS-only)."""
    try:
        e = Embedder(cfg)
        e.embed("probe")
        return e
    except Exception:  # noqa: BLE001
        return None


def build_server(cfg: Config | None = None) -> MCPServer:
    """Construct the MCP server with all Living Brain tools registered."""
    cfg = cfg or Config.load()
    server = MCPServer(
        name="living-brain",
        instructions="Query and grow a local, evidence-linked knowledge graph "
        "built from a markdown vault.",
    )

    @server.tool(description="Hybrid vector+FTS search over captured notes.")
    def search(query: str, k: int = 8) -> list[dict[str, Any]]:
        with db.connect(cfg) as conn:
            hits = retrieval.hybrid_search(
                conn, query, k=k, cfg=cfg, embedder=_search_embedder(cfg)
            )
        return [
            {
                "episode_id": h.episode_id, "heading_path": h.heading_path,
                "content": h.content, "score": h.score, "signals": list(h.signals),
            }
            for h in hits
        ]

    @server.tool(description="Every relationship between two entities, with evidence.")
    def relate(a: str, b: str) -> list[dict[str, Any]]:
        with db.connect(cfg) as conn:
            return links.relate(conn, a, b)

    @server.tool(description="Linked neighbours of an entity (graph traversal).")
    def neighbors(entity_id: str, min_score: float = 0.0, limit: int = 25) -> list[dict[str, Any]]:
        with db.connect(cfg) as conn:
            return links.neighbors(conn, entity_id, min_score=min_score, limit=limit)

    @server.tool(description="An entity's snapshot: type, label, props, aliases, mentions.")
    def entity(entity_id: str) -> dict[str, Any] | None:
        with db.connect(cfg) as conn:
            return R.get_entity(conn, entity_id)

    @server.tool(description="Capture a markdown note. extract=True resolves entities (needs Ollama).")
    def capture(text: str, title: str = "", extract: bool = False) -> dict[str, Any]:
        with db.connect(cfg) as conn:
            res = capture_text(conn, text, title=title, source="mcp://capture",
                               extract=extract, cfg=cfg)
        return {
            "episode_id": res.episode_id, "chunks": res.chunk_count,
            "entities": res.entity_count, "created": res.created,
        }

    return server


class _BearerMiddleware:
    """Reject streamable-http requests without a valid Bearer MCP_TOKEN."""

    def __init__(self, app, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"").decode()
            if auth != f"Bearer {self.token}":
                from starlette.responses import JSONResponse

                resp = JSONResponse({"error": "unauthorized"}, status_code=401)
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)


def serve(transport: str = "stdio", cfg: Config | None = None) -> None:
    """Run the server. 'stdio' (default) or 'streamable-http' (bearer-guarded)."""
    cfg = cfg or Config.load()
    server = build_server(cfg)
    if transport == "streamable-http":
        import uvicorn

        app = _BearerMiddleware(server.streamable_http_app(), cfg.mcp_token)
        uvicorn.run(app, host="127.0.0.1", port=cfg.mcp_port)
    else:
        server.run(transport="stdio")
