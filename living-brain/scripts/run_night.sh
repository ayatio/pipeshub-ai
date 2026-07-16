#!/usr/bin/env bash
#
# run_night.sh — the nightly consolidation loop.
#
# Usage:  bash scripts/run_night.sh [SECONDS]
#
# For up to SECONDS (default 60), repeatedly ingest new/changed notes (cheap and
# idempotent — only changed files are re-embedded), then run one final
# consolidation digest. Works offline: if Ollama isn't reachable it uses the
# built-in fallback embedder + summarizer.

set -euo pipefail

DURATION="${1:-60}"

# Resolve project root (this script lives in <root>/scripts).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

export UV_PYTHON_DOWNLOADS="${UV_PYTHON_DOWNLOADS:-never}"
export PYTHONPATH="src"

# Prefer uv; fall back to a bare python3 if uv is unavailable.
if command -v uv >/dev/null 2>&1; then
  RUN=(uv run --no-project python -m living_brain)
else
  RUN=(python3 -m living_brain)
fi

echo "[night] starting nightly loop for ${DURATION}s (root=${ROOT_DIR})"

# Make sure schema exists before we start.
"${RUN[@]}" migrate

start=${SECONDS}
iteration=0
while (( SECONDS - start < DURATION )); do
  iteration=$((iteration + 1))
  echo "[night] --- pass ${iteration} (elapsed $((SECONDS - start))s) ---"
  "${RUN[@]}" ingest
  # Sleep a beat between passes, but never overshoot the deadline.
  remaining=$(( DURATION - (SECONDS - start) ))
  (( remaining <= 0 )) && break
  sleep_for=$(( remaining < 5 ? remaining : 5 ))
  sleep "${sleep_for}"
done

echo "[night] consolidating..."
"${RUN[@]}" consolidate

echo "[night] done after ${iteration} pass(es)."
