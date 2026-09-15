# PROGRESS

**Current phase:** Phase 4 (Extract & resolve) — next. Phases 1-3 are green;
Phase 3's vector path is written + `-m ollama`-tested but not yet run live here
(no Ollama in this sandbox).

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
- Core modules: `config`, `ids`, `chunking`, `linking` (pure), `db`,
  `embedding` (Ollama), `capture`, `retrieval`, `cli`.
- Tests: **31 passing + 1 ollama-skip** — offline (chunking / ids / linking /
  RRF fusion) + `-m db` (capture idempotency, FTS search) + `-m ollama`
  (semantic vector match, skips without Ollama). All non-offline tiers skip
  cleanly when their backend is absent, so `pytest -q` stays green anywhere.
- Infra fallback: `scripts/pg_local.sh` + `make db-local` bring up a NATIVE
  PG16+pgvector cluster when there is no Docker daemon.
- `scripts/run_night.sh` overnight loop; sample note `vault/samples/note.md`.

## Next action
1. **Phase 4 (extract & resolve).** `extraction.py`: local-LLM strict-JSON
   extraction of typed entities + relationships from a chunk (pydantic-validated,
   with the EXTRACT_FALLBACK path when local JSON fails). `resolution.py`:
   alias → exact label → trigram → embedding cosine → mint; record
   entity_mention + entity_version. Pure JSON-validation/normalisation split out
   for offline tests; live extraction under `-m ollama`.
2. Then Phase 5 (link), 6 (crystallise), 7 (MCP).

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
