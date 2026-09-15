"""Ontology crystallisation (BUILD-BRIEF §1.5, Phase 6).

Types are discovered, not decreed. A type is `proposed` when first observed and
flips to `crystallised` only once at least `instance_min` (default 3) entities
of that type exist — i.e. the shape has recurred enough to be real. The inferred
`shape` (which prop keys are common vs merely seen) is descriptive metadata.

`infer_shape` is pure and unit-tested offline; the count/flip logic runs `-m db`.
"""
from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

DEFAULT_INSTANCE_MIN = 3


def infer_shape(prop_key_sets: list[set[str]]) -> dict[str, Any]:
    """Summarise instances' prop keys into a shape.

    Returns {"common_keys": sorted keys present in EVERY instance,
             "seen_keys":   sorted keys present in ANY instance,
             "instances":   count}. Pure and deterministic.
    """
    if not prop_key_sets:
        return {"common_keys": [], "seen_keys": [], "instances": 0}
    common = set(prop_key_sets[0])
    seen: set[str] = set()
    for keys in prop_key_sets:
        common &= keys
        seen |= keys
    return {
        "common_keys": sorted(common),
        "seen_keys": sorted(seen),
        "instances": len(prop_key_sets),
    }


def register_type(
    conn: psycopg.Connection, name: str, *, instance_min: int = DEFAULT_INSTANCE_MIN
) -> None:
    """Record a type as `proposed` if not already known (idempotent)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ontology_type (name, status, instance_min) "
            "VALUES (%s, 'proposed', %s) ON CONFLICT (name) DO NOTHING",
            (name, instance_min),
        )


def _instance_key_sets(conn: psycopg.Connection, type_: str) -> list[set[str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT props FROM entity WHERE type = %s", (type_,))
        return [set((row[0] or {}).keys()) for row in cur.fetchall()]


def refresh_type(conn: psycopg.Connection, name: str) -> dict[str, Any]:
    """Recompute a type's shape + instance count and crystallise if ready.

    A `proposed` type flips to `crystallised` once instances ≥ instance_min.
    Crystallisation is monotonic — a crystallised type is never demoted here.
    Returns the type's current record.
    """
    register_type(conn, name)
    key_sets = _instance_key_sets(conn, name)
    shape = infer_shape(key_sets)
    count = shape["instances"]
    with conn.cursor() as cur:
        cur.execute("SELECT status, instance_min FROM ontology_type WHERE name = %s", (name,))
        status, instance_min = cur.fetchone()
        new_status = "crystallised" if (status == "crystallised" or count >= instance_min) else "proposed"
        cur.execute(
            "UPDATE ontology_type SET shape = %s, status = %s WHERE name = %s",
            (Jsonb(shape), new_status, name),
        )
    return {"name": name, "status": new_status, "instances": count,
            "instance_min": instance_min, "shape": shape}


def refresh_all(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Register + refresh every type currently present among entities."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT type FROM entity ORDER BY type")
        types = [r[0] for r in cur.fetchall()]
    return [refresh_type(conn, t) for t in types]


def list_types(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """List known types with status, instance_min, and live instance count."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT o.name, o.status, o.instance_min, o.shape, "
            "       (SELECT count(*) FROM entity e WHERE e.type = o.name) AS instances "
            "FROM ontology_type o ORDER BY o.name"
        )
        return [
            {"name": r[0], "status": r[1], "instance_min": r[2],
             "shape": r[3], "instances": r[4]}
            for r in cur.fetchall()
        ]
