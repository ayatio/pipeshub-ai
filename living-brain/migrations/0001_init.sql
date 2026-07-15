-- Core memory store.
-- kind: observation (raw ingested), insight (LLM-derived), reflection (meta)
CREATE TABLE IF NOT EXISTS memories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT    NOT NULL DEFAULT 'observation',
    content       TEXT    NOT NULL,
    source        TEXT,
    salience      REAL    NOT NULL DEFAULT 0.5,
    embedding     TEXT,                       -- JSON array of floats
    consolidated  INTEGER NOT NULL DEFAULT 0, -- 0/1: folded into an insight yet?
    parent_id     INTEGER,                    -- insight this memory rolled up into
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (parent_id) REFERENCES memories(id)
);

CREATE INDEX IF NOT EXISTS idx_memories_kind        ON memories(kind);
CREATE INDEX IF NOT EXISTS idx_memories_consolidated ON memories(consolidated);
CREATE INDEX IF NOT EXISTS idx_memories_salience    ON memories(salience);
