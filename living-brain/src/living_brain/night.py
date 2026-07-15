"""The nightly consolidation loop — the 'living' part of the Living Brain.

Each cycle:
  1. pull the most salient un-consolidated observations,
  2. cluster the seed with its semantic neighbours,
  3. ask the reflector (LLM or fallback) for one insight,
  4. store the insight as a new memory and fold the cluster into it.

The loop runs until the time budget is spent OR there is nothing left to
consolidate (converged) — so a "night" naturally ends when the brain is at rest.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from . import embeddings, llm, memory
from .config import CONFIG
from .db import Database


def _now_monotonic() -> float:
    return time.monotonic()


def run_night(
    minutes: float | None = None,
    *,
    batch_size: int | None = None,
    stop_when_idle: bool | None = None,
    log: Callable[[str], None] = print,
    clock: Callable[[], float] = _now_monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    minutes = CONFIG.night_default_minutes if minutes is None else minutes
    batch_size = CONFIG.night_batch_size if batch_size is None else batch_size
    stop_when_idle = CONFIG.night_stop_when_idle if stop_when_idle is None else stop_when_idle
    budget_s = max(0.0, minutes * 60.0)

    db = Database()
    run_cur = db.execute(
        "INSERT INTO night_runs (budget_minutes, mode, status) VALUES (?, 'live', 'running')",
        (minutes,),
    )
    db.commit()
    run_id = int(run_cur.lastrowid) if run_cur.lastrowid is not None else (
        int((db.query_one("SELECT MAX(id) AS id FROM night_runs") or {"id": 0})["id"])
    )

    started = clock()
    cycles = 0
    insights = 0
    consolidated = 0
    degraded = False
    status = "converged"

    log(f"🌙 night run #{run_id} starting — budget {minutes:g} min, batch {batch_size}")
    try:
        while True:
            if budget_s and (clock() - started) >= budget_s:
                status = "timeout"
                log("⏰ time budget reached")
                break

            batch = memory.pending_observations(db, batch_size)
            if not batch:
                if stop_when_idle:
                    status = "converged"
                    log("✅ nothing left to consolidate — brain at rest")
                    break
                # idle-wait mode: sleep briefly, then re-check
                sleep(0.5)
                continue

            seed = batch[0]
            cluster = memory.select_cluster(db, seed, batch)
            observations = [c["content"] for c in cluster]

            insight_text = llm.reflect(observations)
            if llm.LAST_LLM_DEGRADED or embeddings.LAST_EMBED_DEGRADED:
                degraded = True

            salience = min(1.0, 0.5 + 0.1 * len(cluster))
            insight_id = memory.remember(
                db,
                insight_text,
                kind="insight",
                source=f"night#{run_id}",
                salience=salience,
            )
            memory.mark_consolidated(db, [c["id"] for c in cluster], insight_id)

            cycles += 1
            insights += 1
            consolidated += len(cluster)
            log(
                f"  cycle {cycles}: folded {len(cluster)} → insight #{insight_id}: "
                f"{insight_text[:88]}"
            )

        mode = "degraded" if degraded else "live"
        db.execute(
            """
            UPDATE night_runs
            SET ended_at = datetime('now'), cycles = ?, insights_created = ?,
                memories_consolidated = ?, mode = ?, status = ?
            WHERE id = ?
            """,
            (cycles, insights, consolidated, mode, status, run_id),
        )
        db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        db.execute(
            "UPDATE night_runs SET ended_at = datetime('now'), status = 'error' WHERE id = ?",
            (run_id,),
        )
        db.commit()
        log(f"💥 night run failed: {exc}")
        raise
    finally:
        db.close()

    summary = {
        "run_id": run_id,
        "cycles": cycles,
        "insights_created": insights,
        "memories_consolidated": consolidated,
        "mode": "degraded" if degraded else "live",
        "status": status,
        "elapsed_s": round(clock() - started, 2),
    }
    log(
        f"🧠 night run #{run_id} done — {insights} insight(s) from "
        f"{consolidated} memory(ies) in {cycles} cycle(s) "
        f"[{summary['mode']}, {status}]"
    )
    return summary
