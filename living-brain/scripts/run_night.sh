#!/usr/bin/env bash
# Run the Living Brain nightly consolidation loop.
#   usage: bash scripts/run_night.sh [MINUTES]
# MINUTES is the time budget (default: NIGHT_DEFAULT_MINUTES from .env, else 60).
# The run also stops early once the brain has nothing left to consolidate.
set -euo pipefail

MINUTES="${1:-}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# Make sure the schema is present before a night run.
if command -v uv >/dev/null 2>&1; then
    RUN=(uv run brain)
else
    RUN=(python -m living_brain.cli)
fi

"${RUN[@]}" db-init
"${RUN[@]}" migrate

# Auto-seed on first run so an empty brain still has something to reflect on.
PENDING="$("${RUN[@]}" stats --json | python -c 'import sys,json; print(json.load(sys.stdin)["total"])')"
if [ "${PENDING}" = "0" ]; then
    echo "brain is empty — seeding starter observations"
    "${RUN[@]}" ingest --seed
fi

if [ -n "${MINUTES}" ]; then
    "${RUN[@]}" night --minutes "${MINUTES}" --json
else
    "${RUN[@]}" night --json
fi

echo "---"
"${RUN[@]}" stats
