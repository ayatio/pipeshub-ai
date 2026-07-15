"""Tiny forward-only migration runner (no alembic dependency).

Each migration provides dialect-specific SQL. Applied versions are tracked in a
``schema_migrations`` table so ``make migrate`` is idempotent.

Run:  python -m living_brain.migrate
"""
from __future__ import annotations

from . import db


# Each entry: (version, description, {"sqlite": [...stmts], "postgres": [...stmts]})
MIGRATIONS: list[tuple[int, str, dict[str, list[str]]]] = [
    (
        1,
        "core schema: memories, links, insights, night_runs",
        {
            "sqlite": [
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    source      TEXT,
                    title       TEXT,
                    content     TEXT NOT NULL,
                    kind        TEXT NOT NULL DEFAULT 'note',
                    embedding   TEXT,           -- JSON array of floats
                    importance  REAL NOT NULL DEFAULT 1.0,
                    meta        TEXT NOT NULL DEFAULT '{}',
                    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    accessed_at TIMESTAMP
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind)",
                "CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_at)",
                """
                CREATE TABLE IF NOT EXISTS links (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    src_id      INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    dst_id      INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    kind        TEXT NOT NULL DEFAULT 'associative',
                    weight      REAL NOT NULL DEFAULT 0.0,
                    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (src_id, dst_id, kind)
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_links_src ON links(src_id)",
                """
                CREATE TABLE IF NOT EXISTS insights (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind        TEXT NOT NULL DEFAULT 'theme',
                    title       TEXT,
                    content     TEXT NOT NULL,
                    embedding   TEXT,
                    source_ids  TEXT NOT NULL DEFAULT '[]',
                    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS night_runs (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    ended_at           TIMESTAMP,
                    duration_s         REAL,
                    memories_embedded  INTEGER NOT NULL DEFAULT 0,
                    links_created      INTEGER NOT NULL DEFAULT 0,
                    insights_created   INTEGER NOT NULL DEFAULT 0,
                    cycles             INTEGER NOT NULL DEFAULT 0,
                    notes              TEXT
                )
                """,
            ],
            "postgres": [
                "CREATE EXTENSION IF NOT EXISTS vector",
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id          BIGSERIAL PRIMARY KEY,
                    source      TEXT,
                    title       TEXT,
                    content     TEXT NOT NULL,
                    kind        TEXT NOT NULL DEFAULT 'note',
                    embedding   vector(768),
                    importance  REAL NOT NULL DEFAULT 1.0,
                    meta        JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                    accessed_at TIMESTAMPTZ
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind)",
                "CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_at)",
                """
                CREATE TABLE IF NOT EXISTS links (
                    id          BIGSERIAL PRIMARY KEY,
                    src_id      BIGINT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    dst_id      BIGINT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    kind        TEXT NOT NULL DEFAULT 'associative',
                    weight      REAL NOT NULL DEFAULT 0.0,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (src_id, dst_id, kind)
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_links_src ON links(src_id)",
                """
                CREATE TABLE IF NOT EXISTS insights (
                    id          BIGSERIAL PRIMARY KEY,
                    kind        TEXT NOT NULL DEFAULT 'theme',
                    title       TEXT,
                    content     TEXT NOT NULL,
                    embedding   vector(768),
                    source_ids  JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS night_runs (
                    id                 BIGSERIAL PRIMARY KEY,
                    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
                    ended_at           TIMESTAMPTZ,
                    duration_s         REAL,
                    memories_embedded  INTEGER NOT NULL DEFAULT 0,
                    links_created      INTEGER NOT NULL DEFAULT 0,
                    insights_created   INTEGER NOT NULL DEFAULT 0,
                    cycles             INTEGER NOT NULL DEFAULT 0,
                    notes              TEXT
                )
                """,
            ],
        },
    ),
]


def _ensure_migrations_table(conn: db.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _applied_versions(conn: db.Connection) -> set[int]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {int(r["version"]) for r in rows}


def run() -> int:
    dial = db.dialect()
    applied_count = 0
    with db.connection() as conn:
        _ensure_migrations_table(conn)
        done = _applied_versions(conn)
        for version, desc, sql_by_dialect in sorted(MIGRATIONS):
            if version in done:
                continue
            for stmt in sql_by_dialect[dial]:
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )
            applied_count += 1
            print(f"  applied #{version}: {desc}")
    if applied_count == 0:
        print("  database already up to date")
    return applied_count


def main() -> None:
    print(f"migrate: dialect={db.dialect()}")
    run()
    print("migrate: done")


if __name__ == "__main__":
    main()
