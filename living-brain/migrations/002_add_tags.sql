-- 002_add_tags.sql — free-form tags on memories, plus a helpful index.
-- Demonstrates that the migration runner chains multiple files in order.

ALTER TABLE memories ADD COLUMN tags TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
