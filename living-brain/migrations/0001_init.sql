-- Living Brain — initial schema (Phase 1).
-- Postgres 16/17 + pgvector + pg_trgm.
--
-- Invariants enforced here (see BUILD-BRIEF §1):
--   * Files are truth; every row traces back to an episode (provenance).
--   * Append-only, bi-temporal: entity_version carries world-time
--     (valid_from/valid_to) and system-time (recorded_at). Never UPDATE a fact
--     in place — supersede it with a new version.
--   * No link without evidence: candidate_link.method + evidence + score are
--     NOT NULL. Everything starts status='proposed'.
--   * Types crystallise: ontology_type.status flips only after instance_min
--     entities share a shape.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Embedding dimension (nomic-embed-text = 768). If you change MODEL_EMBED to a
-- model with a different dimension, change vector(768) everywhere below and
-- re-run migrations against a fresh DB.

-- ---------------------------------------------------------------------------
-- Episodes: the append-only event log. The vault markdown is the source of
-- truth; each capture appends exactly one episode.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS episode (
    id            BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind          TEXT        NOT NULL DEFAULT 'note',
    source        TEXT,
    content       TEXT        NOT NULL,
    content_hash  TEXT        NOT NULL UNIQUE,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),  -- world-time
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),  -- system-time
    meta          JSONB       NOT NULL DEFAULT '{}'::jsonb
);

-- ---------------------------------------------------------------------------
-- Chunks: heading-aware, title-prefixed slices of an episode, embedded for
-- semantic search. tsv is a generated FTS column for hybrid retrieval.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunk (
    id            BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    episode_id    BIGINT      NOT NULL REFERENCES episode(id) ON DELETE CASCADE,
    heading_path  TEXT        NOT NULL DEFAULT '',
    content       TEXT        NOT NULL,
    embedding     vector(768),
    tsv           tsvector    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

-- ---------------------------------------------------------------------------
-- Entities: the current, denormalised snapshot of a typed object. History
-- lives in entity_version. id is a stable slug like 'person/michel'.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity (
    id            TEXT        PRIMARY KEY,           -- e.g. 'person/michel'
    type          TEXT        NOT NULL DEFAULT 'thing',
    label         TEXT        NOT NULL,
    props         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    embedding     vector(768),
    first_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Aliases resolve surface forms ("Sarah", "Sarah Chen") to one entity.
CREATE TABLE IF NOT EXISTS entity_alias (
    entity_id     TEXT        NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    alias         TEXT        NOT NULL,
    PRIMARY KEY (entity_id, alias)
);

-- ---------------------------------------------------------------------------
-- Bi-temporal versions. Append-only: to change a fact, insert a new row and
-- close the previous one's valid_to. recorded_at is system-time.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity_version (
    id            BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_id     TEXT        NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    type          TEXT        NOT NULL,
    label         TEXT        NOT NULL,
    props         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    valid_from    TIMESTAMPTZ NOT NULL,               -- world-time start
    valid_to      TIMESTAMPTZ,                        -- world-time end (NULL = current)
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(), -- system-time
    episode_id    BIGINT      REFERENCES episode(id) ON DELETE SET NULL
);

-- Provenance: which episode mentioned which entity (drives co-mention links).
CREATE TABLE IF NOT EXISTS entity_mention (
    entity_id     TEXT        NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    episode_id    BIGINT      NOT NULL REFERENCES episode(id) ON DELETE CASCADE,
    chunk_id      BIGINT      REFERENCES chunk(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (entity_id, episode_id)
);

-- ---------------------------------------------------------------------------
-- Candidate links: pre-materialised, scored, typed, evidenced. Canonicalised
-- so a_id <= b_id; unique on (a_id, b_id, rel_type). Everything is 'proposed'
-- until a human or an allow-listed rule confirms it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidate_link (
    id            BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    a_id          TEXT        NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    b_id          TEXT        NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    rel_type      TEXT        NOT NULL,   -- similar-to | co-occurs | owns | ...
    method        TEXT        NOT NULL,   -- semantic | structural | extracted | shared_attr | temporal
    score         DOUBLE PRECISION NOT NULL,
    evidence      JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- episode ids / similarity / rule name
    status        TEXT        NOT NULL DEFAULT 'proposed',   -- proposed | confirmed | rejected
    decided_by    TEXT,                                       -- 'human:<who>' | 'rule:<name>'
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT candidate_link_canonical CHECK (a_id <= b_id),
    CONSTRAINT candidate_link_no_self   CHECK (a_id <> b_id),
    CONSTRAINT candidate_link_status_ck CHECK (status IN ('proposed','confirmed','rejected')),
    CONSTRAINT candidate_link_uniq      UNIQUE (a_id, b_id, rel_type)
);

-- ---------------------------------------------------------------------------
-- Ontology types crystallise; they are not decreed. status flips to
-- 'crystallised' only after instance_min entities share the shape.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ontology_type (
    name          TEXT        PRIMARY KEY,
    status        TEXT        NOT NULL DEFAULT 'proposed',  -- proposed | crystallised
    instance_min  INT         NOT NULL DEFAULT 3,
    shape         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ontology_type_status_ck CHECK (status IN ('proposed','crystallised'))
);

-- --- Indexes -----------------------------------------------------------------
-- ANN over chunk + entity embeddings (HNSW, cosine).
CREATE INDEX IF NOT EXISTS chunk_embedding_hnsw
    ON chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS entity_embedding_hnsw
    ON entity USING hnsw (embedding vector_cosine_ops);

-- FTS + trigram (fuzzy label match for entity resolution).
CREATE INDEX IF NOT EXISTS chunk_tsv_gin      ON chunk USING gin (tsv);
CREATE INDEX IF NOT EXISTS entity_label_trgm  ON entity USING gin (label gin_trgm_ops);
CREATE INDEX IF NOT EXISTS entity_alias_trgm  ON entity_alias USING gin (alias gin_trgm_ops);

-- Graph-walk + provenance lookups.
CREATE INDEX IF NOT EXISTS candidate_link_a   ON candidate_link (a_id);
CREATE INDEX IF NOT EXISTS candidate_link_b   ON candidate_link (b_id);
CREATE INDEX IF NOT EXISTS candidate_link_st  ON candidate_link (status);
CREATE INDEX IF NOT EXISTS entity_mention_ep  ON entity_mention (episode_id);
CREATE INDEX IF NOT EXISTS entity_version_ent ON entity_version (entity_id);
