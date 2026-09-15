# Living Brain

A **local-first, AI-agnostic second brain**: an evolving graph of typed objects
built from your plain-markdown notes. You write markdown; Living Brain reads it,
extracts typed entities and evidenced relationships, embeds everything for
hybrid search, and serves the whole graph to any AI client over MCP.

- **Files are truth.** The markdown vault is the source of record; Postgres is a
  rebuildable index.
- **Nothing without provenance.** Every entity, fact, and link points back to
  the note it came from.
- **Append-only & bi-temporal.** Facts are superseded, never overwritten; world-
  time and system-time are both tracked.
- **No link without evidence.** Relationships carry a method, a score, and
  evidence, and start life *proposed*.
- **Local by default.** Embeddings and extraction run on local Ollama; cloud
  models are an opt-in extraction fallback only.

See [`BUILD-BRIEF.md`](./BUILD-BRIEF.md) for the full design and
[`CLAUDE.md`](./CLAUDE.md) for the build harness.

## Quick start

```bash
cp .env.example .env          # adjust if needed
uv sync                       # install deps
make db && make migrate       # Postgres + pgvector, apply schema
uv run brain health           # verify DB + pgvector + tables

# ingest a note, search, explain a relationship
uv run brain capture vault/samples/note.md
uv run brain search "what did we decide about pricing?"
uv run brain relate person/sarah project/atlas
```

Prerequisites: Docker (for Postgres), [`uv`](https://docs.astral.sh/uv/), and —
for embedding/extraction — a local [Ollama](https://ollama.com):

```bash
ollama pull nomic-embed-text
ollama pull qwen2.5:14b
```

## Tests

```bash
uv run pytest -q          # offline: pure functions, no DB/Ollama needed
uv run pytest -m db       # integration: needs make db && make migrate
uv run pytest -m ollama   # end-to-end: needs a live Ollama with models pulled
```

## MCP

```bash
make mcp                  # serve the graph to any MCP client (bearer: MCP_TOKEN)
```

## Layout

```
BUILD-BRIEF.md      the design + phased plan + Definition of Done
CLAUDE.md           how the autonomous build loop works
PROGRESS.md         live build status (updated every checkpoint)
migrations/         SQL schema (files are truth; DB is derived)
src/living_brain/   config, db, chunking, embedding, extraction, linking, retrieval, cli, mcp
tests/              offline + -m db + -m ollama tiers
vault/samples/      sample notes for golden tests
scripts/run_night.sh  overnight autonomous build loop
```

## License

MIT.
