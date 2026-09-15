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
        result = capture.capture_file(conn, path, embed=args.embed, extract=args.extract)
    if result.created:
        msg = f"captured episode {result.episode_id}: {result.chunk_count} chunk(s)"
        if args.extract:
            msg += f", {result.entity_count} entity(ies)"
        print(msg)
    else:
        print(f"already captured (episode {result.episode_id}); no changes")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    from . import db, retrieval
    from .embedding import Embedder

    cfg = Config.load()
    embedder: Embedder | None = None
    if not args.no_vector:
        # Probe Ollama; fall back to FTS-only if it isn't reachable.
        try:
            e = Embedder(cfg)
            e.embed("probe")
            embedder = e
        except Exception:  # noqa: BLE001
            print("(ollama unavailable — FTS-only search)", file=sys.stderr)
    with db.connect(cfg) as conn:
        hits = retrieval.hybrid_search(conn, args.query, k=args.k, cfg=cfg, embedder=embedder)
    if not hits:
        print("no matches")
        return 0
    for h in hits:
        head = h.heading_path or "(no heading)"
        signals = "+".join(h.signals)
        snippet = " ".join(h.content.split())[:160]
        print(f"[{h.score:.4f} {signals}] ep{h.episode_id} · {head}\n    {snippet}")
    return 0


def _cmd_relate(args: argparse.Namespace) -> int:
    from . import db, links

    with db.connect() as conn:
        rels = links.relate(conn, args.a, args.b)
    if not rels:
        print(f"no known relations between {args.a} and {args.b}")
        return 0
    print(f"{args.a} ── {args.b}")
    for r in rels:
        ev = json.dumps(r["evidence"], separators=(",", ":"))
        decided = f" ({r['decided_by']})" if r["decided_by"] else ""
        print(
            f"  [{r['status']}] {r['rel_type']} · {r['method']} "
            f"score={r['score']:.3f}{decided}\n      evidence: {ev}"
        )
    return 0


def _cmd_link(args: argparse.Namespace) -> int:
    from . import db, links

    with db.connect() as conn:
        shared = links.generate_shared_attr_links(conn)
        semantic = links.generate_semantic_links(conn)
        conn.commit()
    print(f"generated links — shared_attr: {shared}, semantic: {semantic}")
    return 0


def _cmd_types(_args: argparse.Namespace) -> int:
    from . import db, ontology

    with db.connect() as conn:
        ontology.refresh_all(conn)
        conn.commit()
        rows = ontology.list_types(conn)
    if not rows:
        print("no types yet")
        return 0
    for r in rows:
        common = ",".join(r["shape"].get("common_keys", [])) if r["shape"] else ""
        common = f" · common:[{common}]" if common else ""
        print(f"{r['status']:>12}  {r['name']}  ({r['instances']}/{r['instance_min']}){common}")
    return 0


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
    p_cap.add_argument("--extract", action="store_true", help="extract + resolve entities (needs Ollama)")
    p_cap.set_defaults(func=_cmd_capture)

    p_search = sub.add_parser("search", help="hybrid vector+FTS search")
    p_search.add_argument("query")
    p_search.add_argument("-k", type=int, default=8)
    p_search.add_argument("--no-vector", action="store_true", help="FTS only (skip Ollama)")
    p_search.set_defaults(func=_cmd_search)

    p_rel = sub.add_parser("relate", help="explain relations between two entities")
    p_rel.add_argument("a", help="entity id, e.g. person/sarah-chen")
    p_rel.add_argument("b", help="entity id, e.g. project/atlas")
    p_rel.set_defaults(func=_cmd_relate)

    sub.add_parser(
        "link", help="(re)generate global links: shared-attr + semantic"
    ).set_defaults(func=_cmd_link)

    sub.add_parser(
        "types", help="list ontology types (proposed/crystallised) + instances"
    ).set_defaults(func=_cmd_types)

    sub.add_parser("mcp", help="serve the graph over MCP (Phase 7)").set_defaults(func=_cmd_mcp)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
