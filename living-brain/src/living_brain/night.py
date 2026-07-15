"""Timed night runner: loop consolidation cycles until the budget expires.

Entry point for scripts/run_night.sh. Records the run in ``night_runs`` and
stops early (idempotently) once there is no more work to do.

Usage:  python -m living_brain.night --duration 60
"""
from __future__ import annotations

import argparse
import time

from . import db
from .config import get_settings
from .consolidate import run_cycle
from .embeddings import backend_name as embed_backend
from .llm import backend_name as llm_backend


def _open_run() -> int:
    with db.connection() as conn:
        if db.dialect() == "postgres":
            row = conn.execute(
                "INSERT INTO night_runs (notes) VALUES (?) RETURNING id", ("running",)
            ).fetchone()
            return int(row["id"])
        cur = conn.execute("INSERT INTO night_runs (notes) VALUES (?)", ("running",))
        return int(cur._raw.lastrowid)


def _close_run(run_id: int, *, duration: float, embedded: int, links: int,
               insights: int, cycles: int, notes: str) -> None:
    with db.connection() as conn:
        conn.execute(
            "UPDATE night_runs SET ended_at = CURRENT_TIMESTAMP, duration_s = ?, "
            "memories_embedded = ?, links_created = ?, insights_created = ?, "
            "cycles = ?, notes = ? WHERE id = ?",
            (duration, embedded, links, insights, cycles, notes, run_id),
        )


def run_night(duration_s: float, *, idle_sleep: float = 1.0, verbose: bool = True) -> dict:
    start = time.monotonic()
    run_id = _open_run()
    totals = {"embedded": 0, "links": 0, "insights": 0, "cycles": 0}
    idle_streak = 0

    if verbose:
        print(f"[night] run #{run_id} starting — budget {duration_s:.0f}s")
        print(f"[night] embeddings={embed_backend()}  llm={llm_backend()}  db={db.dialect()}")

    while time.monotonic() - start < duration_s:
        report = run_cycle()
        totals["cycles"] += 1
        totals["embedded"] += report.embedded
        totals["links"] += report.links_created
        totals["insights"] += report.insights_created
        if verbose and report.did_work:
            elapsed = time.monotonic() - start
            msg = (f"[night] +{elapsed:5.1f}s cycle {totals['cycles']}: "
                   f"embedded={report.embedded} links={report.links_created} "
                   f"insights={report.insights_created}")
            print(msg)
            for d in report.detail:
                print(f"           · {d}")
        if not report.did_work:
            idle_streak += 1
            # Nothing changed two cycles running: brain is consolidated, rest.
            if idle_streak >= 2:
                if verbose:
                    print("[night] no further work — brain consolidated, resting")
                break
            remaining = duration_s - (time.monotonic() - start)
            if remaining <= 0:
                break
            time.sleep(min(idle_sleep, max(0.0, remaining)))
        else:
            idle_streak = 0

    duration = time.monotonic() - start
    notes = f"cycles={totals['cycles']} idle_stop={idle_streak >= 2}"
    _close_run(run_id, duration=duration, embedded=totals["embedded"],
               links=totals["links"], insights=totals["insights"],
               cycles=totals["cycles"], notes=notes)
    if verbose:
        print(f"[night] run #{run_id} done in {duration:.1f}s — "
              f"embedded={totals['embedded']} links={totals['links']} "
              f"insights={totals['insights']} cycles={totals['cycles']}")
    return {"run_id": run_id, "duration_s": duration, **totals}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a nightly consolidation pass.")
    parser.add_argument("--duration", type=float, default=60,
                        help="time budget in seconds (default 60)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    run_night(args.duration, verbose=not args.quiet)


if __name__ == "__main__":
    main()
