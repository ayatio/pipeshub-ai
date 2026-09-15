# PROGRESS

**Current phase:** Phase 7 (MCP) — last. Phases 1-6 are green. The LLM-backed
paths (vector search, extraction) are written and `-m ollama`-tested, but not
run live here (no Ollama in this sandbox); the DB-only paths (schema, capture,
FTS search, resolution, all link generators, relate, crystallisation) are
verified live.

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
- **Phase 5 — Link (DoD green).** `links.py` persists evidenced
  `candidate_link`s (canonical `a_id<=b_id`, unique per `rel_type`, born
  `proposed`) and generates all five methods: `extracted` (LLM relationships,
  endpoints must resolve to real entities), `temporal` (co-mention per episode),
  `shared_attr` (normalised shared prop value), `semantic` (entity-embedding
  cosine ≥ τ), `structural` (`[[wikilinks]]` → minted concept entities, pure
  parser in `wikilinks.py`). Capture's `_build_links` runs extracted+structural+
  co-mention per episode; `brain link` runs the global generators. `brain relate
  A B` explains every relation with method + score + status + evidence;
  `set_status` is the only path out of `proposed` (§1.4). Verified end-to-end
  (person↔project extracted+temporal, person↔concept structural).
- **Phase 6 — Crystallise (DoD green).** `ontology.py`: types are discovered,
  not decreed — first sighting registers a `proposed` `ontology_type`; it flips
  to `crystallised` (monotonically) once instances ≥ `instance_min` (default 3).
  `infer_shape` (pure) summarises common vs seen prop keys. Capture calls
  `refresh_all` after linking; `brain types` lists status + n/instance_min +
  common shape keys. Verified live (widget crystallises at 3 with
  common:[color,size]; gadget stays proposed at 2).
- Core modules: `config`, `ids`, `chunking`, `linking`, `wikilinks` (pure),
  `db`, `embedding`, `extraction`, `resolution`, `links`, `ontology`, `capture`,
  `retrieval`, `cli`.
- **Test isolation:** DB tests now run against an isolated `<db>_test` database,
  migrated once and truncated after each test — tests never pollute the real
  vault index and never interfere with each other.
- Tests: **60 passing + 2 ollama-skips** — offline (chunking / ids / linking /
  RRF fusion / extraction parsing / wikilinks / shape inference) + `-m db`
  (capture idempotency, FTS search, resolution ladder incl. trigram, append-only
  versioning, capture→extract wiring, all link generators, relate, confirm,
  crystallisation) + `-m ollama` (semantic vector match, live extraction).
  Non-offline tiers skip cleanly when their backend is absent, so `pytest -q`
  stays green anywhere.
- Infra fallback: `scripts/pg_local.sh` + `make db-local` bring up a NATIVE
  PG16+pgvector cluster when there is no Docker daemon.
- `scripts/run_night.sh` overnight loop; sample note `vault/samples/note.md`.

## Next action
1. **Phase 7 (MCP).** `mcp_server.py`: expose the core functions as MCP tools —
   `brain.search`, `brain.relate`, `brain.neighbors`, `brain.entity`,
   `brain.capture` — over the MCP Python SDK with bearer-token auth (`MCP_TOKEN`).
   Wire `brain mcp` / `make mcp`. Tools call the same functions the CLI uses (a
   thin read/traverse layer). DoD: server starts; a client can search + traverse.
   After Phase 7's DoD is green, write "ALL PHASES COMPLETE" as line 1.

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
