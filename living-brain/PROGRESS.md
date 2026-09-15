# PROGRESS

**Current phase:** Phase 1 (Foundation) — scaffolding + offline core complete;
DB integration (`make db && make migrate`, `brain health`) pending a live
Postgres in this environment.

## Done
- Repo scaffold: `pyproject.toml` (uv/hatchling, `brain` console script),
  `Makefile`, `docker-compose.yml` (Postgres 16 + pgvector on :5433),
  `.env.example`, `.gitignore`, `.claude/settings.json`.
- Design + harness docs: `BUILD-BRIEF.md` (constitution §1, architecture,
  data model, phases + DoD §7), `CLAUDE.md`, `README.md`.
- Schema: `migrations/0001_init.sql` — episode / chunk / entity / entity_alias /
  entity_version / entity_mention / candidate_link / ontology_type, with HNSW,
  GIN-FTS, and trigram indexes; constitution invariants encoded as constraints.
- Core modules: `config`, `ids` (slug/hash, pure), `chunking` (heading-aware,
  pure), `linking` (canonical form + scoring, pure), `db` (connect / migrate /
  health), `embedding` (Ollama client + pgvector formatting), `capture`
  (idempotent episode+chunk ingest), `cli` (`brain` dispatch).
- Offline tests green: `tests/test_chunking.py`, `test_ids.py`, `test_linking.py`.
- `scripts/run_night.sh` overnight loop; sample note `vault/samples/note.md`.

## Next action
1. Run `uv sync` and confirm `uv run pytest -q` is green offline (no DB/Ollama).
2. Bring up the DB: `make db && make migrate`, then `uv run brain health`
   (expects `ok: true`). Add `-m db` tests for capture idempotency.
3. Begin **Phase 3** (embed & search): populate chunk embeddings via Ollama and
   implement hybrid vector+FTS search behind `brain search`.

## NEEDS-DECISION
- *(none open)*

## Notes / lessons
- The execution container is ephemeral and was reclaimed once mid-build, wiping
  all **uncommitted** work. Rule going forward (now in CLAUDE.md §2): commit AND
  push on every green checkpoint — a pushed commit is the only durable state.
- `EMBED_DIM` (768) is coupled to `MODEL_EMBED` (nomic-embed-text) and the
  `vector(768)` columns. Changing the embed model means changing all three and
  rebuilding the index from the vault.
