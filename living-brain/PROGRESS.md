# PROGRESS

**Current phase:** Phase 5 (Link) — next. Phases 1-4 are green. The LLM-backed
paths (vector search, extraction) are written and `-m ollama`-tested, but not
run live here (no Ollama in this sandbox); the DB-only paths are verified live.

## Done
- **Phase 1 — Foundation (DoD green).** Scaffold (`pyproject.toml` uv/hatchling,
  `brain` console script; `Makefile`; `docker-compose.yml`; `.env.example`;
  `.gitignore`; `.claude/settings.json`). Schema `migrations/0001_init.sql`
  (episode / chunk / entity / entity_alias / entity_version / entity_mention /
  candidate_link / ontology_type) with pgvector HNSW, GIN-FTS, trigram indexes
  and constitution invariants as constraints. `brain health` → `ok: true`
  (pgvector + pg_trgm + all 8 tables present).
- **Phase 2 — Capture & chunk (DoD green).** Heading-aware chunker (pure);
  idempotent `capture` (episode + chunks, dedup by content_hash). Verified:
  sample note → 1 episode + 4 chunks; re-run is a no-op.
- **Phase 3 — Embed & search (DoD green, vector path pending live Ollama).**
  `retrieval.hybrid_search`: FTS (chunk.tsv) + optional vector ANN
  (chunk.embedding) fused with Reciprocal Rank Fusion; degrades to FTS-only when
  Ollama is down. `brain search "<q>"` returns ranked passages with provenance
  (episode + heading path + which signals surfaced each hit). Verified live via
  CLI (FTS path). `capture --embed` populates embeddings when Ollama is up.
- **Phase 4 — Extract & resolve (DoD green; live extraction pending Ollama).**
  `extraction.py`: strict-JSON typed extraction over Ollama (pydantic-validated
  entities + relationships) with retries and an optional cloud fallback
  (`EXTRACT_FALLBACK=openai|anthropic:model`, extraction only). Pure parsing /
  prompt-building unit-tested offline. `resolution.py`: alias → slug/label →
  trigram → embedding-cosine → mint ladder; append-only, change-gated
  bi-temporal versions; provenance mentions. `capture --extract` wires it end
  to end (entity embeddings opt-in via `--embed`).
- Core modules: `config`, `ids`, `chunking`, `linking` (pure), `db`,
  `embedding`, `extraction`, `resolution`, `capture`, `retrieval`, `cli`.
- Tests: **44 passing + 2 ollama-skips** — offline (chunking / ids / linking /
  RRF fusion / extraction parsing) + `-m db` (capture idempotency, FTS search,
  resolution ladder incl. trigram, append-only versioning, capture→extract
  wiring via an injected fake extractor) + `-m ollama` (semantic vector match,
  live extraction). Non-offline tiers skip cleanly when their backend is
  absent, so `pytest -q` stays green anywhere.
- Infra fallback: `scripts/pg_local.sh` + `make db-local` bring up a NATIVE
  PG16+pgvector cluster when there is no Docker daemon.
- `scripts/run_night.sh` overnight loop; sample note `vault/samples/note.md`.

## Next action
1. **Phase 5 (link).** Persist all five link methods as evidenced
   `candidate_link`s: `extracted` (from relationships the LLM emits — resolve
   both ends, evidence = quote), `temporal`/co-mention (entities sharing an
   episode), `shared_attr` (same normalised prop value), `semantic` (entity
   embedding cosine ≥ τ), `structural` ([[wikilinks]] between notes). Add
   `brain relate A B` to explain every relation with method + score + evidence.
   Reuse the pure `linking.py` builders; add a DB writer with the canonical
   unique-constraint upsert; `-m db` golden tests.
2. Then Phase 6 (crystallise), 7 (MCP).

## NEEDS-DECISION
- *(none open)*

## Environment notes / lessons
- **The execution container is ephemeral and was reclaimed once mid-build,
  wiping all uncommitted work.** Rule (now CLAUDE.md §2): commit AND push on
  every green checkpoint — a pushed commit is the only durable state.
- **No Docker daemon in this sandbox.** `make db` (docker compose) does not work
  here; use `make db-local` (native PG16 + `postgresql-16-pgvector`, trust auth,
  port 5433). Data dir: `/home/user/pgdata`.
- Ollama is not running in this sandbox, so `--embed` and `-m ollama` tests
  can't be exercised here yet; Phase 3 code will be written to work when a live
  Ollama is present and to degrade/skip cleanly when it isn't.
- `EMBED_DIM` (768) is coupled to `MODEL_EMBED` (nomic-embed-text) and the
  `vector(768)` columns — change all three together and rebuild from the vault.
