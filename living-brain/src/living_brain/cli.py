"""`brain` CLI (BUILD-BRIEF §7).

Thin dispatch over the core functions. Phases fill in the subcommands; the
scaffold wires health + capture now and leaves search/relate/mcp as clearly
marked "not yet — Phase N" stubs so the surface is stable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config


def _cmd_health(_args: argparse.Namespace) -> int:
    from . import db

    cfg = Config.load()
    try:
        with db.connect(cfg) as conn:
            report = db.health(conn)
    except Exception as exc:  # noqa: BLE001 - surface any connection error plainly
        print(f"health: cannot reach database at {cfg.database_url}\n  {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


def _cmd_migrate(_args: argparse.Namespace) -> int:
    from . import db

    with db.connect() as conn:
        applied = db.apply_migrations(conn)
    print("applied:", ", ".join(applied) if applied else "(none)")
    return 0


def _cmd_capture(args: argparse.Namespace) -> int:
    from . import capture, db

    path = Path(args.path)
    if not path.exists():
        print(f"capture: no such file: {path}", file=sys.stderr)
        return 2
    with db.connect() as conn:
        result = capture.capture_file(conn, path, embed=args.embed)
    if result.created:
        print(f"captured episode {result.episode_id}: {result.chunk_count} chunk(s)")
    else:
        print(f"already captured (episode {result.episode_id}); no changes")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    print("search: not yet implemented — Phase 3 (embed & search)", file=sys.stderr)
    return 3


def _cmd_relate(args: argparse.Namespace) -> int:
    print("relate: not yet implemented — Phase 5 (link)", file=sys.stderr)
    return 3


def _cmd_mcp(_args: argparse.Namespace) -> int:
    print("mcp: not yet implemented — Phase 7 (MCP)", file=sys.stderr)
    return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brain", description="Living Brain CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="check DB connectivity, pgvector, tables").set_defaults(
        func=_cmd_health
    )
    sub.add_parser("migrate", help="apply SQL migrations").set_defaults(func=_cmd_migrate)

    p_cap = sub.add_parser("capture", help="ingest a markdown note")
    p_cap.add_argument("path", help="path to a .md file")
    p_cap.add_argument("--embed", action="store_true", help="compute embeddings (needs Ollama)")
    p_cap.set_defaults(func=_cmd_capture)

    p_search = sub.add_parser("search", help="hybrid search (Phase 3)")
    p_search.add_argument("query")
    p_search.add_argument("-k", type=int, default=8)
    p_search.set_defaults(func=_cmd_search)

    p_rel = sub.add_parser("relate", help="explain relations between two entities (Phase 5)")
    p_rel.add_argument("a")
    p_rel.add_argument("b")
    p_rel.set_defaults(func=_cmd_relate)

    sub.add_parser("mcp", help="serve the graph over MCP (Phase 7)").set_defaults(func=_cmd_mcp)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
