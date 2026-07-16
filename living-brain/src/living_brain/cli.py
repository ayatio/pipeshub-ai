"""Command-line entry point for living-brain."""

from __future__ import annotations

import argparse
import sys

from .config import Config
from . import db, ingest as ingest_mod, search as search_mod, consolidate as consolidate_mod


def _cmd_init_db(cfg: Config, args) -> int:
    path = db.init_db(cfg)
    print(f"[db] initialized database at {path}")
    return 0


def _cmd_migrate(cfg: Config, args) -> int:
    applied = db.migrate(cfg)
    if applied:
        print(f"[migrate] applied: {', '.join(applied)}")
    else:
        print("[migrate] up to date, nothing to apply")
    return 0


def _cmd_ingest(cfg: Config, args) -> int:
    r = ingest_mod.ingest(cfg)
    print(
        f"[ingest] scanned={r.scanned} ingested={r.ingested} "
        f"unchanged={r.unchanged} chunks+={r.chunks} backend={r.backend}"
    )
    return 0


def _cmd_search(cfg: Config, args) -> int:
    hits = search_mod.search(cfg, args.query, top_k=args.k)
    if not hits:
        print("[search] no results (is anything ingested?)")
        return 0
    for h in hits:
        snippet = " ".join(h.text.split())[:120]
        print(f"{h.score:.3f}  {h.path}#{h.ordinal}  {snippet}")
    return 0


def _cmd_consolidate(cfg: Config, args) -> int:
    path, _body = consolidate_mod.consolidate(cfg, stamp=args.stamp)
    print(f"[consolidate] wrote {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="living-brain",
        description="A local, offline-first second brain.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create the database file")
    sub.add_parser("migrate", help="apply pending migrations")
    sub.add_parser("ingest", help="ingest/refresh notes into the brain")

    s = sub.add_parser("search", help="semantic search over ingested notes")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=5, help="number of results")

    c = sub.add_parser("consolidate", help="run a nightly consolidation digest")
    c.add_argument("--stamp", default=None, help="override the timestamp label")

    return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = Config.load()

    dispatch = {
        "init-db": _cmd_init_db,
        "migrate": _cmd_migrate,
        "ingest": _cmd_ingest,
        "search": _cmd_search,
        "consolidate": _cmd_consolidate,
    }
    handler = dispatch[args.command]
    return handler(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
