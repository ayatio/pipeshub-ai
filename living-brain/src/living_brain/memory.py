"""Memory operations: remember, recall (semantic), and cluster selection."""
from __future__ import annotations

import json
from typing import Any

from . import embeddings
from .db import Database


def remember(
    db: Database,
    content: str,
    *,
    kind: str = "observation",
    source: str | None = None,
    salience: float = 0.5,
    parent_id: int | None = None,
) -> int:
    emb = embeddings.embed(content)
    cur = db.execute(
        """
        INSERT INTO memories (kind, content, source, salience, embedding, parent_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (kind, content, source, salience, json.dumps(emb), parent_id),
    )
    db.commit()
    # lastrowid works for sqlite; for pg we'd use RETURNING, but sqlite is default.
    return int(cur.lastrowid) if cur.lastrowid is not None else _last_id(db)


def _last_id(db: Database) -> int:
    row = db.query_one("SELECT MAX(id) AS id FROM memories")
    return int(row["id"]) if row and row["id"] is not None else 0


def _row_embedding(row: dict[str, Any]) -> list[float]:
    raw = row.get("embedding")
    if not raw:
        return []
    try:
        return [float(x) for x in json.loads(raw)]
    except Exception:
        return []


def recall(db: Database, query: str, k: int = 5) -> list[dict[str, Any]]:
    q_emb = embeddings.embed(query)
    rows = db.query("SELECT * FROM memories")
    scored = []
    for r in rows:
        score = embeddings.cosine(q_emb, _row_embedding(r))
        scored.append((score, r))
    scored.sort(key=lambda t: t[0], reverse=True)
    out = []
    for score, r in scored[:k]:
        r = dict(r)
        r["score"] = round(score, 4)
        out.append(r)
    return out


def pending_observations(db: Database, limit: int) -> list[dict[str, Any]]:
    """Un-consolidated observations, most salient first."""
    return db.query(
        """
        SELECT * FROM memories
        WHERE kind = 'observation' AND consolidated = 0
        ORDER BY salience DESC, id ASC
        LIMIT ?
        """,
        (limit,),
    )


def pending_count(db: Database) -> int:
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM memories WHERE kind='observation' AND consolidated=0"
    )
    return int(row["n"]) if row else 0


def select_cluster(
    db: Database, seed: dict[str, Any], candidates: list[dict[str, Any]], threshold: float = 0.2
) -> list[dict[str, Any]]:
    """Group the seed with its most similar pending peers."""
    seed_emb = _row_embedding(seed)
    cluster = [seed]
    for c in candidates:
        if c["id"] == seed["id"]:
            continue
        if embeddings.cosine(seed_emb, _row_embedding(c)) >= threshold:
            cluster.append(c)
    return cluster


def mark_consolidated(db: Database, ids: list[int], parent_id: int) -> None:
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    db.execute(
        f"""
        UPDATE memories
        SET consolidated = 1, parent_id = ?, updated_at = datetime('now')
        WHERE id IN ({placeholders})
        """,
        [parent_id, *ids],
    )
    db.commit()


def stats(db: Database) -> dict[str, Any]:
    def count(where: str, params: tuple = ()) -> int:
        row = db.query_one(f"SELECT COUNT(*) AS n FROM memories WHERE {where}", params)
        return int(row["n"]) if row else 0

    total = db.query_one("SELECT COUNT(*) AS n FROM memories")
    return {
        "total": int(total["n"]) if total else 0,
        "observations": count("kind='observation'"),
        "insights": count("kind='insight'"),
        "reflections": count("kind='reflection'"),
        "pending": count("kind='observation' AND consolidated=0"),
        "night_runs": (
            int((db.query_one("SELECT COUNT(*) AS n FROM night_runs") or {"n": 0})["n"])
        ),
    }
