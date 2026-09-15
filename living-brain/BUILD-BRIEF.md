# BUILD-BRIEF — The Living Brain

A local-first, AI-agnostic **second brain**: an evolving graph of typed objects
distilled from plain markdown notes. You write markdown; the system reads it,
extracts typed entities and evidenced relationships, embeds everything for
hybrid search, and exposes the whole graph to any AI client over MCP. No cloud
dependency is required to run it; no single model vendor is baked in.

The north star: **the notes are the truth, and the brain grows itself from
them.** Structure is discovered, not decreed.

---

## §1. Constitution (non-negotiable invariants)

These rules win over any feature. Never weaken one to make a test pass.

1. **Files are truth.** The markdown vault is the source of record. The database
   is a derived, rebuildable index. Deleting the DB and re-ingesting the vault
   must reproduce the same graph (modulo model nondeterminism).
2. **Every row has provenance.** Every entity, version, and link traces back to
   the `episode` (and ideally the chunk) it came from. Nothing exists "just
   because."
3. **Append-only & bi-temporal.** Facts are never overwritten in place. To
   change a fact, close the old `entity_version` (`valid_to`) and append a new
   one. We track **world-time** (`valid_from`/`valid_to`, when it was true) and
   **system-time** (`recorded_at`, when we learned it).
4. **No link without evidence.** A `candidate_link` requires a `method`, a
   `score`, and an `evidence` payload. Links are born `proposed`; they become
   `confirmed` only by a human or an explicit, allow-listed rule.
5. **Types crystallise, they are not decreed.** A new `ontology_type` starts
   `proposed`. It flips to `crystallised` only once `instance_min` (default 3)
   entities independently share its shape.
6. **Local-first, AI-agnostic.** Embedding and extraction run against local
   Ollama by default. Any cloud model is an opt-in fallback for extraction only,
   never a hard requirement.
7. **Deterministic where it can be.** IDs, slugs, chunk boundaries, link
   canonical form, and scoring are pure functions — same input, same output,
   unit-testable with no DB or network.

---

## §2. Architecture

```
markdown vault ──capture──▶ episode (append-only log)
                              │
                     chunk (heading-aware, embedded, FTS)
                              │
                   extract (local LLM → typed candidates, strict JSON)
                              │
                 resolve (alias/embedding/trigram → entity + version)
                              │
                    link (semantic · structural · extracted · shared-attr · temporal)
                              │
                 candidate_link (scored, evidenced, proposed)
                              │
   retrieve (hybrid: vector + FTS + graph walk)  ◀── MCP tools ── any AI client
```

Pipeline stages are independent and each is separately testable. The MCP server
is a thin read/traverse layer over the same functions the CLI uses.

---

## §3. Stack

- **Python ≥ 3.11**, packaged with `uv` / hatchling; console script `brain`.
- **Postgres 16 + pgvector + pg_trgm** (via `docker-compose`, host port 5433).
- **psycopg 3** for DB access (no ORM; explicit SQL).
- **Ollama** for local embeddings (`nomic-embed-text`, dim 768) and extraction
  (`qwen2.5:14b`), configured in `.env`.
- **MCP Python SDK** for the server; **pydantic** for typed models & JSON
  validation; **httpx** for the Ollama/cloud clients.

---

## §4. Data model (see `migrations/0001_init.sql`)

- `episode` — append-only capture log; `content_hash` unique (idempotent
  ingest); `occurred_at` (world) vs `recorded_at` (system).
- `chunk` — heading-aware slice of an episode; `embedding vector(768)`; `tsv`
  generated FTS column. HNSW + GIN indexes.
- `entity` — current denormalised snapshot; stable slug id (`person/michel`);
  `props jsonb`; optional `embedding`.
- `entity_alias` — surface forms → entity (trigram-indexed).
- `entity_version` — bi-temporal history; append-only.
- `entity_mention` — entity × episode provenance (drives co-mention).
- `candidate_link` — canonicalised (`a_id <= b_id`), unique on
  `(a_id,b_id,rel_type)`, `method`+`score`+`evidence` required, `status`
  proposed→confirmed/rejected.
- `ontology_type` — proposed→crystallised, `instance_min`, `shape`.

---

## §5. Resolution & linking

**Entity resolution** (deterministic first, then fuzzy): exact alias → exact
label → trigram similarity above threshold → embedding cosine above threshold →
otherwise mint a new entity with a slugified id. Every resolution records an
`entity_mention`.

**Link methods** (each yields evidenced `candidate_link`s):
- `semantic` — entity embedding cosine ≥ τ (evidence: similarity).
- `structural` — explicit markdown links / `[[wikilinks]]` between notes.
- `extracted` — relationships the LLM emitted in strict JSON (evidence: chunk).
- `shared_attr` — same normalised prop value (evidence: attr + value).
- `temporal` — co-mention within the same episode / time window.

All scores are pure functions in `linking.py`, unit-tested offline.

---

## §6. Retrieval

Hybrid query: vector ANN over chunks + FTS over `tsv`, fused (reciprocal-rank),
then optional 1–2 hop graph walk over `confirmed` (and optionally high-score
`proposed`) links. Returns passages with provenance and the entities/links that
connect them.

---

## §7. Phases & Definition of Done

Work top to bottom. A phase is done only when its DoD is green, committed, and
**pushed**.

- **Phase 1 — Foundation.** Scaffold, schema, config, DB connect.
  *DoD:* `make db && make migrate` succeeds; `brain health` reports pgvector +
  all tables; offline `pytest` green.
- **Phase 2 — Capture & chunk.** Ingest markdown → episode + heading-aware
  chunks; idempotent by content hash.
  *DoD:* `brain capture` on a sample note creates 1 episode + N chunks; re-run
  creates nothing new; chunking unit tests green offline.
- **Phase 3 — Embed & search.** Ollama embeddings for chunks; hybrid
  vector+FTS search.
  *DoD:* `brain search "<q>"` returns ranked passages with provenance
  (`-m ollama`/`-m db`).
- **Phase 4 — Extract & resolve.** Local LLM strict-JSON extraction of typed
  entities; resolution into entity + version + mention.
  *DoD:* sample notes yield expected entities; JSON-failure fallback works;
  re-ingest doesn't duplicate entities.
- **Phase 5 — Link.** All five link methods produce evidenced candidate_links;
  `brain relate A B` explains every relation with evidence.
  *DoD:* golden linking tests green offline; `relate` shows method+score+evidence.
- **Phase 6 — Crystallise.** Ontology type proposal/crystallisation over
  `instance_min`.
  *DoD:* a type flips proposed→crystallised at threshold; below it stays proposed.
- **Phase 7 — MCP.** Serve search / relate / capture / traverse over MCP with a
  bearer token.
  *DoD:* `make mcp` serves; a client can search and traverse the graph.

---

## §8. MCP interface (Phase 7)

Read-mostly tools over the same core functions:
`brain.search(query, k)` · `brain.relate(a, b)` · `brain.neighbors(id, hops)` ·
`brain.capture(text)` · `brain.entity(id)`. Bearer-token auth via `MCP_TOKEN`.

---

## Working agreement

See `CLAUDE.md`. One phase at a time; commit **and push** on green; keep
`PROGRESS.md` current; log decisions instead of stalling; never weaken §1.
