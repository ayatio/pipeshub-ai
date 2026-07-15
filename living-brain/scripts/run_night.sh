#!/usr/bin/env bash
# Run a nightly consolidation pass for the living-brain.
#
#   bash scripts/run_night.sh [DURATION_SECONDS]
#
# The brain replays recent memories: embeds new ones, links associations,
# clusters them into themes, and applies the forgetting curve — until the time
# budget expires (or it runs out of work to do).
set -euo pipefail

DURATION="${1:-60}"
cd "$(dirname "$0")/.."

mkdir -p logs
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="logs/night-${STAMP}.log"

# Prefer uv if available; fall back to plain python if the venv is active.
if command -v uv >/dev/null 2>&1; then
  RUNNER=(uv run python)
else
  RUNNER=(python3)
fi

echo "run_night: consolidating for ${DURATION}s (log: ${LOG})"
"${RUNNER[@]}" -m living_brain.night --duration "${DURATION}" 2>&1 | tee "${LOG}"
echo "run_night: done -> ${LOG}"
