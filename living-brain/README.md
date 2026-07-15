# living-brain

A local-first **living brain**: a personal memory that ingests your notes,
embeds them, and — like a brain during sleep — **consolidates itself every
night**, forming associative links between related memories and distilling
recurring ones into higher-level *insights*. Everything runs on your machine.

```
notes ─▶ ingest ─▶ memories ──┐
                              │   nightly consolidation (replay)
                              ├─▶ embed new memories
                              ├─▶ link nearest neighbours (associations)
                              ├─▶ cluster + summarize into themes (LLM)
                              └─▶ decay un-accessed memories (forgetting curve)
                                          │
query ─▶ embed ─▶ semantic search ◀───────┘
```

## Stack

- **Python** managed by [`uv`](https://docs.astral.sh/uv/)
- **Embeddings**: Ollama `nomic-embed-text` (768-d)
- **LLM** (theme synthesis): Ollama `qwen2.5:14b`
- **Storage**: SQLite by default (zero setup); **Postgres + pgvector** for production

If Ollama isn't running, living-brain **degrades gracefully** to a deterministic
local embedding + an extractive summarizer, so every command still works — just
at lower quality. This is what makes the project runnable with no external
services.

## Quickstart

```bash
uv sync && cp .env.example .env

# Optional but recommended — real models via Ollama:
ollama pull nomic-embed-text && ollama pull qwen2.5:14b

make db && make migrate          # provision + migrate the database
bash scripts/run_night.sh 60     # run a 60-second consolidation pass
```

Then explore:

```bash
uv run brain ingest data/notes   # ingest the sample notes
bash scripts/run_night.sh 30     # consolidate them
uv run brain search "how does sleep help memory?"
uv run brain insights            # themes the brain formed overnight
uv run brain stats
```

Or do it all at once:

```bash
make demo
```

## Commands

| Command | What it does |
| --- | --- |
| `make sync` | install dependencies (`uv sync`) |
| `make db` | provision the DB (SQLite dir, or Postgres via docker if configured) |
| `make migrate` | apply schema migrations |
| `make night` / `bash scripts/run_night.sh N` | run a consolidation pass for N seconds |
| `make demo` | ingest samples + run a night pass end-to-end |
| `make test` | run the test suite |
| `brain ingest [PATH]` | ingest a file or directory of `.md`/`.txt` notes |
| `brain search "…"` | semantic search over memories |
| `brain insights` | list consolidated themes |
| `brain stats` | counts + active backends |

## How consolidation works

`scripts/run_night.sh N` loops **consolidation cycles** until the `N`-second
budget expires (or there's nothing left to do). Each cycle:

1. **Embed** any memory that doesn't yet have a vector.
2. **Link** every memory to its top-K nearest neighbours above a similarity
   threshold — building an associative graph.
3. **Theme**: find connected clusters of strongly-linked memories and ask the
   LLM to name and summarize the shared theme, stored as an `insight`.
4. **Decay**: multiply every memory's `importance` by a factor < 1, so notes you
   never revisit gently fade — a forgetting curve.

Runs are recorded in the `night_runs` table.

## Configuration

All settings live in `.env` (see `.env.example`). The important switch:

```bash
# Default — local SQLite, no services needed:
DATABASE_URL=sqlite:///./data/living_brain.db

# Production — Postgres + pgvector (start it with `make db-postgres`):
# DATABASE_URL=postgresql://brain:brain@localhost:5433/living_brain
```

## Using the Postgres + pgvector backend

```bash
docker compose up -d db          # or: make db-postgres
# set DATABASE_URL=postgresql://brain:brain@localhost:5433/living_brain in .env
make migrate
```

The same code path then stores real `vector(768)` columns and ranks with
pgvector's `<=>` operator inside the database.

## Layout

```
living-brain/
├── Makefile                 # db / migrate / night / demo / test
├── docker-compose.yml       # Postgres + pgvector (production backend)
├── scripts/run_night.sh     # timed nightly consolidation entrypoint
├── data/notes/              # sample notes to ingest
├── src/living_brain/
│   ├── config.py            # settings from .env
│   ├── db.py                # SQLite/Postgres connection abstraction
│   ├── migrate.py           # forward-only migration runner
│   ├── embeddings.py        # Ollama embeddings + deterministic fallback
│   ├── llm.py               # Ollama chat + extractive fallback
│   ├── store.py             # memories / links / insights + similarity search
│   ├── ingest.py            # chunk + ingest notes
│   ├── consolidate.py       # one consolidation cycle
│   ├── night.py             # timed night runner
│   ├── search.py            # semantic search
│   └── cli.py               # `brain` command line
└── tests/test_pipeline.py   # end-to-end pipeline test
```

## License

MIT
