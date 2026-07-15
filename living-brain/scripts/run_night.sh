#!/usr/bin/env bash
#
# run_night.sh — run one nightly consolidation pass ("sleep") for the brain.
#
# Usage:
#   bash scripts/run_night.sh [DURATION_SECONDS]
#
# DURATION_SECONDS is the wall-clock budget for consolidation (default 60).
# The pass stops early once a steady state is reached.
#
set -euo pipefail

DURATION="${1:-60}"

# Resolve project root (parent of this script's directory) and run from there
# so relative paths in .env (e.g. ./data/brain.db) behave predictably.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Make sure the database exists and is migrated before consolidating.
run() {
  if command -v uv >/dev/null 2>&1; then
    uv run python -m living_brain.cli "$@"
  else
    PYTHONPATH="src:${PYTHONPATH:-}" python3 -m living_brain.cli "$@"
  fi
}

echo ">> Living Brain nightly run (budget: ${DURATION}s)"
run createdb
run migrate >/dev/null
run night --duration "${DURATION}"
