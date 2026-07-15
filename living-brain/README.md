# Living Brain 🧠

A local, private **second brain** that captures memories during the day and
**consolidates them at night** — inspired by how sleep replays and prunes
memories in the hippocampus.

- **Capture** notes, facts, events, and tasks.
- **Retrieve** them semantically (vector search).
- **Consolidate** overnight: cluster related memories, synthesise higher-level
  *insights*, reinforce what matters, and forget what has decayed.
- **100% local & private.** Uses [Ollama](https://ollama.com) for embeddings
  (`nomic-embed-text`) and reasoning (`qwen2.5:14b`). Everything is stored in a
  single SQLite file.

> No Ollama? No problem. The brain automatically falls back to a deterministic
> local embedder and an extractive summariser, so the whole pipeline runs
> offline (that's also how the test suite stays hermetic).

## Quick start

```bash
unzip living-brain.zip && cd living-brain
uv sync && cp .env.example .env

# Optional but recommended — the real models:
ollama pull nomic-embed-text && ollama pull qwen2.5:14b

make db && make migrate
bash scripts/run_night.sh 60
```

That last command seeds a few sample memories on first run, consolidates them
for up to 60 seconds, and prints a **morning brief**.

## CLI

```bash
brain status                         # counts, active backend, migration state
brain ingest "Met Priya about the ingestion pipeline" --kind note
brain search "problems with ingestion"
brain night --duration 60            # a consolidation pass ("sleep")
brain brief                          # re-print the latest morning brief
```

(Run via `uv run brain ...`, or `python -m living_brain ...`.)

## How consolidation works

Each **sleep cycle** inside a night run:

1. **Forgetting curve** — importance decays exponentially with time since a
   memory was last recalled (`LB_DECAY_HALF_LIFE_DAYS`).
2. **Clustering** — active memories are greedily grouped by embedding cosine
   similarity (`LB_CLUSTER_THRESHOLD`).
3. **Insight synthesis** — each fresh multi-memory cluster is summarised into a
   single insight (via `qwen2.5:14b`, or extractively offline), and its members
   are reinforced.
4. **Dedup & forget** — near-duplicates (`LB_DUPLICATE_THRESHOLD`) and memories
   that decayed below `LB_IMPORTANCE_FLOOR` are archived.

The loop runs until its time budget is spent **or** a steady state is reached.

## Configuration

All configuration lives in `.env` (see `.env.example`). Key knobs:

| Variable | Default | Meaning |
|---|---|---|
| `LB_DB_PATH` | `./data/brain.db` | SQLite database location |
| `LB_OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint |
| `LB_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `LB_LLM_MODEL` | `qwen2.5:14b` | Reasoning model |
| `LB_CLUSTER_THRESHOLD` | `0.72` | Cosine threshold to group memories |
| `LB_DUPLICATE_THRESHOLD` | `0.95` | Cosine threshold to treat as duplicate |
| `LB_DECAY_HALF_LIFE_DAYS` | `14` | Importance half-life |
| `LB_IMPORTANCE_FLOOR` | `0.05` | Below this, a memory is forgotten |

## Project layout

```
living-brain/
├── Makefile                  # db / migrate / seed / night / test targets
├── pyproject.toml            # uv project (stdlib-only runtime)
├── .env.example
├── migrations/               # forward-only *.sql migrations
├── scripts/run_night.sh      # nightly entry point
├── src/living_brain/
│   ├── config.py             # .env loading
│   ├── db.py                 # sqlite + migration runner
│   ├── embeddings.py         # ollama nomic-embed-text + fallback
│   ├── llm.py                # ollama qwen2.5:14b + extractive fallback
│   ├── ollama_client.py      # tiny urllib client
│   ├── memory.py             # ingest + semantic search
│   ├── consolidate.py        # the "sleep" engine
│   ├── seed.py               # sample data
│   └── cli.py                # `brain` command
└── tests/                    # hermetic end-to-end tests (offline backend)
```

## Development

```bash
make test        # run the test suite (no Ollama required)
make status      # what backend am I actually using right now?
make reset       # delete the local database
```

## License

MIT.
