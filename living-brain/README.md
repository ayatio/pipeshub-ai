# living-brain

A local, **offline-first "second brain."** Drop your notes into a folder and it
ingests them, embeds each chunk into a vector, and — on a nightly run —
consolidates everything into a digest that surfaces recurring **themes** and
unexpected **connections** between ideas. The nightly step is modelled on memory
consolidation during sleep.

It runs with **zero third-party Python dependencies**. If an
[Ollama](https://ollama.com) server is available it uses real models
(`nomic-embed-text` for embeddings, `qwen2.5:14b` for summarization); if not, it
transparently falls back to a built-in deterministic embedder and an extractive
summarizer, so the whole thing works with no network and no model server.

## Quick start

```bash
uv sync
cp .env.example .env

# Optional — only if you have Ollama installed and want real models:
ollama pull nomic-embed-text && ollama pull qwen2.5:14b

make db && make migrate
bash scripts/run_night.sh 60
```

`run_night.sh 60` ingests your notes repeatedly for 60 seconds (cheap — only
changed files are re-embedded), then writes a consolidation digest to
`data/reports/digest-<timestamp>.md`.

## Commands

| Command | What it does |
| --- | --- |
| `make db` | Create the SQLite database file |
| `make migrate` | Apply migrations in `migrations/` |
| `make ingest` | Ingest / refresh notes from `data/notes` |
| `make consolidate` | Run one nightly digest now |
| `make night [SECONDS=60]` | Run the nightly loop |
| `make search Q="..."` | Semantic search over your notes |
| `make test` | Run the offline smoke tests |

You can also call the CLI directly:

```bash
PYTHONPATH=src uv run --no-project python -m living_brain search "vector databases"
```

## How it works

```
data/notes/*.md ──► ingest ──► chunk ──► embed ──► SQLite (documents, chunks)
                                                        │
                                   nightly consolidate ─┘──► themes + connections
                                                            ──► data/reports/*.md
```

- **Embeddings** — `nomic-embed-text` via Ollama, else a signed
  feature-hashing vector (`LB_EMBED_DIM` dims). Cosine similarity for retrieval.
- **Summarization** — `qwen2.5:14b` via Ollama, else frequency-scored
  extractive summarization.
- **Storage** — SQLite via the Python standard library. Embeddings are stored
  as JSON; a linear cosine scan is plenty fast for a personal corpus.

## Configuration

All settings live in `.env` (see `.env.example`). Every value has a default, so
an empty `.env` works. Key ones:

- `LB_NOTES_DIR` — where your notes live (default `data/notes`)
- `LB_OLLAMA_URL` — Ollama endpoint; unreachable ⇒ offline fallback
- `LB_EMBED_MODEL` / `LB_LLM_MODEL` — model names when Ollama is present

## Project layout

```
living-brain/
├── pyproject.toml         # uv project (no third-party deps)
├── Makefile               # db / migrate / ingest / night / search / test
├── scripts/run_night.sh   # the nightly loop
├── migrations/*.sql       # schema migrations
├── data/notes/            # your notes (sample notes included)
├── data/reports/          # generated digests
└── src/living_brain/      # the package
    ├── config.py  db.py  embeddings.py  llm.py
    ├── ingest.py  search.py  consolidate.py  cli.py
```

## Notes on the setup commands

The original setup referenced Postgres (`make db`/`make migrate`) and Ollama.
This implementation keeps the **same command sequence** but uses SQLite (stdlib)
and makes Ollama optional, so `uv sync && make db && make migrate &&
bash scripts/run_night.sh 60` runs anywhere — including CI and offline
environments — with nothing to install.
