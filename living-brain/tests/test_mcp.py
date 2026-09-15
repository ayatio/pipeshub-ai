"""Offline test: the MCP server registers the expected tools (no DB needed)."""
from living_brain.mcp_server import build_server


async def test_server_registers_expected_tools():
    server = build_server()
    names = {t.name for t in await server.list_tools()}
    assert names == {"search", "relate", "neighbors", "entity", "capture"}


async def test_every_tool_has_a_description():
    server = build_server()
    for tool in await server.list_tools():
        assert tool.description, f"tool {tool.name} is missing a description"
