# Living Brain

An autonomous **memory & nightly-reflection engine**. It ingests observations,
embeds them with a local Ollama model, and — during a "night run" — consolidates
related memories into higher-level insights using a local LLM. When Ollama is not
available it transparently falls back to a deterministic **degraded mode** so the
whole pipeline still runs end-to-end.

## Quick start

```bash
uv sync && cp .env.example .env      # install deps + config
ollama pull nomic-embed-text         # embeddings model   (optional*)
ollama pull qwen2.5:14b              # reflection model   (optional*)
make db && make migrate              # create DB + schema
bash scripts/run_night.sh 60         # run a 60-minute night pass
```

\* Optional: without Ollama the engine uses a hashing embedding and an
extractive reflector, and every night run is recorded with `mode = degraded`.

## How it works

```
observations ──embed──► memories ──┐
                                   │  night run (cluster → reflect → fold)
insights  ◄───────────────────────┘
```

- **`brain remember "..."`** — store one observation (auto-embedded).
- **`brain ingest --seed`** — load the bundled starter observations.
- **`brain recall "query"`** — semantic search by cosine similarity.
- **`brain night --minutes N`** — consolidate until the time budget is spent
  *or* the brain is at rest (nothing left to consolidate → `converged`).
- **`brain stats`** — counts of observations / insights / night runs.

A night run stops early when idle, so `run_night.sh 60` finishes in seconds on a
small brain and only uses the full budget when there is real work to do.

## Configuration

All settings live in `.env` (see `.env.example`). Highlights:

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/brain.db` | SQLite (default) or `postgresql://…` |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint |
| `EMBED_MODEL` | `nomic-embed-text` | embedding model |
| `LLM_MODEL` | `qwen2.5:14b` | reflection model |
| `NIGHT_DEFAULT_MINUTES` | `60` | default night budget |

Postgres backend: `uv sync --extra postgres` and set a `postgresql://` URL.

## Make targets

`make db · migrate · seed · night · stats · test · clean` (see `make help`).

## Tests

```bash
make test     # or: uv run pytest
```
