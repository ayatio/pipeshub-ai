-- Audit log of nightly consolidation passes.
CREATE TABLE IF NOT EXISTS night_runs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    ended_at                TEXT,
    budget_minutes          REAL    NOT NULL DEFAULT 0,
    cycles                  INTEGER NOT NULL DEFAULT 0,
    insights_created        INTEGER NOT NULL DEFAULT 0,
    memories_consolidated   INTEGER NOT NULL DEFAULT 0,
    mode                    TEXT    NOT NULL DEFAULT 'live',   -- live | degraded
    status                  TEXT    NOT NULL DEFAULT 'running' -- running | converged | timeout | error
);

CREATE INDEX IF NOT EXISTS idx_night_runs_status ON night_runs(status);
