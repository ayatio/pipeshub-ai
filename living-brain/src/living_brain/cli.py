"""Command-line interface: `brain <subcommand>`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import CONFIG, PROJECT_ROOT
from .db import Database, init_db
from .migrate import pending, run_migrations


def _cmd_db_init(_args: argparse.Namespace) -> int:
    print(init_db())
    return 0


def _cmd_migrate(args: argparse.Namespace) -> int:
    if args.status:
        with Database() as db:
            todo = [p.name for p in pending(db)]
        if todo:
            print("Pending migrations:")
            for name in todo:
                print(f"  - {name}")
        else:
            print("All migrations applied.")
        return 0
    applied = run_migrations()
    if applied:
        for name in applied:
            print(f"applied {name}")
    else:
        print("No pending migrations.")
    return 0


def _cmd_remember(args: argparse.Namespace) -> int:
    from . import memory

    with Database() as db:
        mid = memory.remember(db, args.text, source=args.source or "cli", salience=args.salience)
    print(f"remembered #{mid}")
    return 0


def _cmd_recall(args: argparse.Namespace) -> int:
    from . import memory

    with Database() as db:
        hits = memory.recall(db, args.query, k=args.k)
    for h in hits:
        print(f"[{h['score']:.3f}] ({h['kind']}) {h['content']}")
    if not hits:
        print("(no memories yet)")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    from . import memory

    paths: list[Path] = []
    if args.seed:
        paths = sorted((PROJECT_ROOT / "seed").glob("*.txt"))
    paths += [Path(p) for p in args.files]
    if not paths:
        print("nothing to ingest (pass files or --seed)")
        return 1

    count = 0
    with Database() as db:
        for path in paths:
            if not path.exists():
                print(f"  skip (missing): {path}")
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                memory.remember(db, line, source=path.name)
                count += 1
    print(f"ingested {count} observation(s)")
    return 0


def _cmd_night(args: argparse.Namespace) -> int:
    from .night import run_night

    summary = run_night(minutes=args.minutes, batch_size=args.batch)
    if args.json:
        print(json.dumps(summary, indent=2))
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    from . import memory

    with Database() as db:
        s = memory.stats(db)
    if args.json:
        print(json.dumps(s, indent=2))
    else:
        print("Living Brain — memory stats")
        for key, val in s.items():
            print(f"  {key:>14}: {val}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="brain", description="Living Brain CLI")
    p.add_argument("--version", action="version", version=f"living-brain {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("db-init", help="ensure the database exists").set_defaults(func=_cmd_db_init)

    mig = sub.add_parser("migrate", help="apply pending migrations")
    mig.add_argument("--status", action="store_true", help="show pending migrations only")
    mig.set_defaults(func=_cmd_migrate)

    rem = sub.add_parser("remember", help="store one observation")
    rem.add_argument("text")
    rem.add_argument("--source")
    rem.add_argument("--salience", type=float, default=0.5)
    rem.set_defaults(func=_cmd_remember)

    rec = sub.add_parser("recall", help="semantic recall")
    rec.add_argument("query")
    rec.add_argument("-k", type=int, default=5)
    rec.set_defaults(func=_cmd_recall)

    ing = sub.add_parser("ingest", help="ingest text files (one observation per line)")
    ing.add_argument("files", nargs="*")
    ing.add_argument("--seed", action="store_true", help="ingest bundled seed/*.txt")
    ing.set_defaults(func=_cmd_ingest)

    night = sub.add_parser("night", help="run the nightly consolidation loop")
    night.add_argument("--minutes", type=float, default=None)
    night.add_argument("--batch", type=int, default=None)
    night.add_argument("--json", action="store_true")
    night.set_defaults(func=_cmd_night)

    st = sub.add_parser("stats", help="show memory statistics")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=_cmd_stats)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
