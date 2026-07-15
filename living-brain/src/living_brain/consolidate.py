"""Nightly consolidation — the "sleep" phase of the Living Brain.

Each cycle:
  1. Applies a forgetting curve (importance decay by age since last recall).
  2. Greedily clusters active memories by embedding similarity.
  3. For each fresh multi-memory cluster, synthesises an insight and boosts
     the importance of its members (they proved connected).
  4. Archives near-duplicates and memories that have decayed below the floor.

The loop runs until a wall-clock time budget is exhausted or there is no more
work to do, whichever comes first.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time

from .config import Config
from .db import connect
from .llm import Summarizer
from .util import cosine, now_iso, parse_iso, unpack_vector

log = logging.getLogger("living_brain.consolidate")


def _decay_factor(last_seen_iso: str, half_life_days: float) -> float:
    """Exponential decay: importance halves every ``half_life_days``."""
    try:
        age_days = (parse_iso(now_iso()) - parse_iso(last_seen_iso)).total_seconds() / 86400.0
    except Exception:  # noqa: BLE001
        return 1.0
    if half_life_days <= 0:
        return 1.0
    return 0.5 ** (age_days / half_life_days)


def _signature(ids: list[int]) -> str:
    key = ",".join(str(i) for i in sorted(ids))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


class Consolidator:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.summarizer = Summarizer(cfg)

    def _load_active(self, conn):
        rows = conn.execute(
            """SELECT m.id, m.content, m.importance, m.last_seen_at,
                      e.model AS model, e.dim AS dim, e.vector AS vec
               FROM memories m JOIN embeddings e ON e.memory_id = m.id
               WHERE m.archived = 0"""
        ).fetchall()
        items = []
        for r in rows:
            items.append(
                {
                    "id": r["id"],
                    "content": r["content"],
                    "importance": r["importance"],
                    "last_seen_at": r["last_seen_at"],
                    "model": r["model"],
                    "dim": r["dim"],
                    "vec": unpack_vector(r["vec"]),
                }
            )
        return items

    def _thresholds(self, items) -> tuple[float, float]:
        """Pick cluster/duplicate thresholds appropriate to the embedding space.

        The hash fallback and a real embedding model (e.g. nomic-embed-text)
        have very different similarity distributions, so thresholds are chosen
        per backend based on the models actually recorded on the memories.
        """
        if not items:
            return self.cfg.cluster_threshold, self.cfg.duplicate_threshold
        fallback = sum(1 for it in items if str(it["model"]).startswith("fallback"))
        if fallback * 2 >= len(items):  # majority (or tie) are fallback vectors
            return self.cfg.fallback_cluster_threshold, self.cfg.fallback_duplicate_threshold
        return self.cfg.cluster_threshold, self.cfg.duplicate_threshold

    def _apply_decay(self, conn, items) -> None:
        for it in items:
            factor = _decay_factor(it["last_seen_at"], self.cfg.decay_half_life_days)
            new_imp = round(max(0.0, it["importance"] * factor), 6)
            it["importance"] = new_imp
            conn.execute("UPDATE memories SET importance = ? WHERE id = ?", (new_imp, it["id"]))
        conn.commit()

    def _cluster(self, items, threshold: float) -> list[list[dict]]:
        """Greedy single-pass clustering by cosine similarity."""
        clusters: list[list[dict]] = []
        for it in items:
            placed = False
            for cluster in clusters:
                head = cluster[0]
                if head["dim"] != it["dim"]:
                    continue
                if cosine(head["vec"], it["vec"]) >= threshold:
                    cluster.append(it)
                    placed = True
                    break
            if not placed:
                clusters.append([it])
        return clusters

    def _archive_duplicates(self, conn, cluster, dup_threshold: float) -> int:
        """Within a cluster, archive near-duplicates keeping the most important."""
        archived = 0
        kept: list[dict] = []
        cluster_sorted = sorted(cluster, key=lambda x: x["importance"], reverse=True)
        for it in cluster_sorted:
            dup_of = None
            for k in kept:
                if k["dim"] == it["dim"] and cosine(k["vec"], it["vec"]) >= dup_threshold:
                    dup_of = k
                    break
            if dup_of is not None:
                conn.execute("UPDATE memories SET archived = 1 WHERE id = ?", (it["id"],))
                archived += 1
            else:
                kept.append(it)
        cluster[:] = kept
        return archived

    def _make_insight(self, conn, cluster) -> bool:
        ids = [it["id"] for it in cluster]
        sig = _signature(ids)
        exists = conn.execute("SELECT 1 FROM insights WHERE signature = ?", (sig,)).fetchone()
        if exists:
            return False
        text, backend = self.summarizer.synthesize([it["content"] for it in cluster])
        if not text.strip():
            return False
        conn.execute(
            """INSERT INTO insights(content, kind, created_at, source_ids, signature)
               VALUES (?, 'summary', ?, ?, ?)""",
            (text.strip(), now_iso(), json.dumps(ids), sig),
        )
        # Members proved connected -> reinforce them slightly.
        for it in cluster:
            boosted = min(1.0, it["importance"] + 0.1)
            conn.execute("UPDATE memories SET importance = ? WHERE id = ?", (boosted, it["id"]))
        log.info("insight (%s) from %d memories: %s", backend, len(ids), text[:80])
        return True

    def _forget(self, conn) -> int:
        cur = conn.execute(
            "UPDATE memories SET archived = 1 WHERE archived = 0 AND importance < ?",
            (self.cfg.importance_floor,),
        )
        return cur.rowcount

    def run(self, duration_s: float) -> dict:
        """Run consolidation for up to ``duration_s`` seconds. Returns a summary."""
        start = time.monotonic()
        started_iso = now_iso()
        conn = connect(self.cfg.db_path)
        run_id = conn.execute(
            "INSERT INTO night_runs(started_at) VALUES (?)", (started_iso,)
        ).lastrowid
        conn.commit()

        cycles = 0
        insights_created = 0
        archived_count = 0
        memories_seen = 0
        try:
            while time.monotonic() - start < duration_s:
                cycles += 1
                items = self._load_active(conn)
                memories_seen = len(items)
                if not items:
                    log.info("no active memories; nothing to consolidate.")
                    break

                self._apply_decay(conn, items)
                cluster_thr, dup_thr = self._thresholds(items)
                clusters = self._cluster(items, cluster_thr)

                did_work = False
                for cluster in clusters:
                    archived = self._archive_duplicates(conn, cluster, dup_thr)
                    if archived:
                        archived_count += archived
                        did_work = True
                    if len(cluster) >= 2:
                        if self._make_insight(conn, cluster):
                            insights_created += 1
                            did_work = True
                    conn.commit()

                forgotten = self._forget(conn)
                conn.commit()
                if forgotten:
                    archived_count += forgotten
                    did_work = True

                log.info(
                    "cycle %d: %d memories, %d clusters, +%d insights, %d archived",
                    cycles, len(items), len(clusters), insights_created, archived_count,
                )

                if not did_work:
                    # Steady state reached — no need to keep spinning.
                    log.info("steady state reached after %d cycle(s).", cycles)
                    break
                # Small pause so a long budget doesn't busy-loop the CPU.
                time.sleep(min(1.0, max(0.0, duration_s - (time.monotonic() - start))))

            ended_iso = now_iso()
            elapsed = round(time.monotonic() - start, 3)
            conn.execute(
                """UPDATE night_runs
                   SET ended_at = ?, duration_s = ?, cycles = ?, memories_seen = ?,
                       insights_created = ?, archived_count = ?, notes = ?
                   WHERE id = ?""",
                (
                    ended_iso, elapsed, cycles, memories_seen,
                    insights_created, archived_count,
                    "ok", run_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "run_id": run_id,
            "cycles": cycles,
            "memories_seen": memories_seen,
            "insights_created": insights_created,
            "archived_count": archived_count,
            "duration_s": round(time.monotonic() - start, 3),
        }


def morning_brief(cfg: Config, limit: int = 5) -> dict:
    """A concise digest to read after a night of consolidation."""
    conn = connect(cfg.db_path)
    try:
        insights = conn.execute(
            "SELECT content, created_at FROM insights ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        top_mem = conn.execute(
            """SELECT content, importance FROM memories
               WHERE archived = 0 ORDER BY importance DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        last_run = conn.execute(
            "SELECT * FROM night_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {
            "insights": [dict(r) for r in insights],
            "top_memories": [dict(r) for r in top_mem],
            "last_run": dict(last_run) if last_run else None,
        }
    finally:
        conn.close()
