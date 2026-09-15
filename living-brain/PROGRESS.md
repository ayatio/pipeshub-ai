# PROGRESS

**Current phase:** Phase 3 (Embed & search) — next. Phases 1 and 2 are green
(schema + capture verified against a live Postgres + pgvector).

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
- Core modules: `config`, `ids`, `chunking`, `linking` (canonical form +
  scoring, pure), `db`, `embedding` (Ollama), `capture`, `cli`.
- Tests: **24 green** — 21 offline (chunking / ids / linking) + 3 `-m db`
  (capture creation, idempotency, whitespace-normalised hash). DB tests skip
  cleanly when no Postgres is reachable, so the offline tier stays green.
- Infra fallback: `scripts/pg_local.sh` + `make db-local` bring up a NATIVE
  PG16+pgvector cluster when there is no Docker daemon.
- `scripts/run_night.sh` overnight loop; sample note `vault/samples/note.md`.

## Next action
1. **Phase 3 (embed & search).** Populate `chunk.embedding` via Ollama
   (`brain capture --embed`), then implement hybrid retrieval: vector ANN over
   `chunk.embedding` + FTS over `chunk.tsv`, reciprocal-rank fused, behind
   `brain search "<q>"`. Add `-m ollama` + `-m db` tests.
2. Then Phase 4 (extract & resolve), 5 (link), 6 (crystallise), 7 (MCP).

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
