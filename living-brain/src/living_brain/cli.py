"""Command-line interface for the Living Brain.

    brain init                 # create db + run migrations
    brain migrate              # apply pending migrations
    brain seed                 # load sample memories if empty
    brain ingest "text..."     # add a memory
    brain search "query"       # semantic search
    brain night [--duration N] # run nightly consolidation
    brain brief                # print the morning brief
    brain status               # counts + backend + migration state
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import ollama_client
from .config import load_config
from .consolidate import Consolidator, morning_brief
from .db import ensure_db, migrate, migration_status
from .memory import MemoryStore
from .seed import seed_if_empty


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _backend_line(cfg) -> str:
    if ollama_client.is_available(cfg.ollama_url):
        return f"ollama @ {cfg.ollama_url} (embed={cfg.embed_model}, llm={cfg.llm_model})"
    return "local fallback (Ollama unreachable — hash embeddings + extractive summaries)"


def cmd_init(args, cfg) -> int:
    ensure_db(cfg.db_path)
    applied = migrate(cfg.db_path)
    print(f"db ready at {cfg.db_path}")
    print(f"migrations applied: {applied or 'none (already up to date)'}")
    return 0


def cmd_createdb(args, cfg) -> int:
    ensure_db(cfg.db_path)
    print(f"db ready at {cfg.db_path}")
    return 0


def cmd_migrate(args, cfg) -> int:
    applied = migrate(cfg.db_path)
    print(f"migrations applied: {applied or 'none (already up to date)'}")
    return 0


def cmd_seed(args, cfg) -> int:
    n = seed_if_empty(cfg)
    print(f"seeded {n} memories" if n else "brain already has memories; nothing seeded")
    return 0


def cmd_ingest(args, cfg) -> int:
    store = MemoryStore(cfg)
    mem_id = store.add(
        args.text, source=args.source, kind=args.kind,
        importance=args.importance, tags=args.tags or "",
    )
    print(f"stored memory #{mem_id}")
    return 0


def cmd_search(args, cfg) -> int:
    store = MemoryStore(cfg)
    results = store.search(args.query, top_k=args.top_k)
    if not results:
        print("no matches")
        return 0
    for mem, score in results:
        print(f"[{score:0.3f}] (#{mem.id}, {mem.kind}) {mem.content}")
    return 0


def cmd_night(args, cfg) -> int:
    if not args.no_seed:
        added = seed_if_empty(cfg)
        if added:
            print(f"seeded {added} sample memories for first run")
    print(f"backend: {_backend_line(cfg)}")
    print(f"consolidating for up to {args.duration}s ...")
    summary = Consolidator(cfg).run(float(args.duration))
    print("night run complete:")
    print(json.dumps(summary, indent=2))
    print("\n--- morning brief ---")
    _print_brief(morning_brief(cfg))
    return 0


def _print_brief(brief) -> None:
    insights = brief.get("insights") or []
    if insights:
        print("Insights:")
        for i in insights:
            print(f"  • {i['content']}")
    else:
        print("Insights: (none yet)")
    top = brief.get("top_memories") or []
    if top:
        print("Top of mind:")
        for m in top:
            print(f"  • [{m['importance']:0.2f}] {m['content']}")


def cmd_brief(args, cfg) -> int:
    _print_brief(morning_brief(cfg, limit=args.limit))
    return 0


def cmd_status(args, cfg) -> int:
    store = MemoryStore(cfg)
    counts = store.counts()
    print(f"db:       {cfg.db_path}")
    print(f"backend:  {_backend_line(cfg)}")
    print(f"memories: {counts['active']} active, {counts['archived']} archived")
    print(f"insights: {counts['insights']}")
    print("migrations:")
    for version, done in migration_status(cfg.db_path):
        print(f"  [{'x' if done else ' '}] {version}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="brain", description="Living Brain CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create db and run migrations").set_defaults(func=cmd_init)
    sub.add_parser("createdb", help="create the database file only").set_defaults(func=cmd_createdb)
    sub.add_parser("migrate", help="apply pending migrations").set_defaults(func=cmd_migrate)
    sub.add_parser("seed", help="load sample memories if empty").set_defaults(func=cmd_seed)

    pi = sub.add_parser("ingest", help="add a memory")
    pi.add_argument("text")
    pi.add_argument("--source", default="manual")
    pi.add_argument("--kind", default="note")
    pi.add_argument("--importance", type=float, default=0.5)
    pi.add_argument("--tags", default="")
    pi.set_defaults(func=cmd_ingest)

    ps = sub.add_parser("search", help="semantic search")
    ps.add_argument("query")
    ps.add_argument("--top-k", type=int, default=None)
    ps.set_defaults(func=cmd_search)

    pn = sub.add_parser("night", help="run nightly consolidation")
    pn.add_argument("--duration", type=float, default=60.0, help="time budget in seconds")
    pn.add_argument("--no-seed", action="store_true", help="do not auto-seed an empty brain")
    pn.set_defaults(func=cmd_night)

    pb = sub.add_parser("brief", help="print the morning brief")
    pb.add_argument("--limit", type=int, default=5)
    pb.set_defaults(func=cmd_brief)

    sub.add_parser("status", help="show counts and backend").set_defaults(func=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config()
    _setup_logging(cfg.log_level)
    return args.func(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
