-- 001_init.sql — core schema for the Living Brain.

CREATE TABLE IF NOT EXISTS memories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content       TEXT    NOT NULL,
    source        TEXT    NOT NULL DEFAULT 'manual',
    kind          TEXT    NOT NULL DEFAULT 'note',   -- note | event | fact | task | insight
    importance    REAL    NOT NULL DEFAULT 0.5,      -- 0..1, decays over time
    created_at    TEXT    NOT NULL,
    last_seen_at  TEXT    NOT NULL,
    access_count  INTEGER NOT NULL DEFAULT 0,
    archived      INTEGER NOT NULL DEFAULT 0         -- 1 == "forgotten"
);

CREATE INDEX IF NOT EXISTS idx_memories_archived   ON memories(archived);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);

-- One embedding row per memory. Vector is stored as raw little-endian float32.
CREATE TABLE IF NOT EXISTS embeddings (
    memory_id  INTEGER PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
    model      TEXT    NOT NULL,
    dim        INTEGER NOT NULL,
    vector     BLOB    NOT NULL
);

-- Higher-level knowledge produced during nightly consolidation.
CREATE TABLE IF NOT EXISTS insights (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content    TEXT    NOT NULL,
    kind       TEXT    NOT NULL DEFAULT 'summary',   -- summary | pattern | connection
    created_at TEXT    NOT NULL,
    source_ids TEXT    NOT NULL DEFAULT '[]',        -- JSON array of memory ids
    signature  TEXT    NOT NULL UNIQUE               -- dedup key over source_ids
);

-- One row per `run_night.sh` invocation, for observability.
CREATE TABLE IF NOT EXISTS night_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TEXT    NOT NULL,
    ended_at         TEXT,
    duration_s       REAL,
    cycles           INTEGER NOT NULL DEFAULT 0,
    memories_seen    INTEGER NOT NULL DEFAULT 0,
    insights_created INTEGER NOT NULL DEFAULT 0,
    archived_count   INTEGER NOT NULL DEFAULT 0,
    notes            TEXT
);
