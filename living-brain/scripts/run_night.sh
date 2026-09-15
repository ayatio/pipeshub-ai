#!/usr/bin/env bash
# run_night.sh — overnight autonomous build loop for the Living Brain.
#
# Loops Claude Code, one phase at a time, committing AND PUSHING on green. Uses
# --dangerously-skip-permissions so it runs unattended — which is why you only
# run it inside this sandboxed repo. It pauses only on a genuine decision, which
# it logs to PROGRESS.md under NEEDS-DECISION and works around with a reversible
# default. When every phase is done it writes "ALL PHASES COMPLETE" at the top of
# PROGRESS.md and this loop exits.
#
# Usage:  bash scripts/run_night.sh [MAX_ITERS]
#   MAX_ITERS  hard cap on loop iterations (default 40). Each iteration asks
#              Claude Code to advance the build by one green checkpoint.
set -euo pipefail

cd "$(dirname "$0")/.."
MAX_ITERS="${1:-40}"
PROGRESS="PROGRESS.md"

if ! command -v claude >/dev/null 2>&1; then
  echo "error: 'claude' CLI not found on PATH. Install Claude Code first:"
  echo "       https://docs.claude.com/en/docs/claude-code"
  exit 127
fi

PROMPT=$(cat <<'EOF'
You are building the Living Brain. Read BUILD-BRIEF.md and CLAUDE.md, then read
PROGRESS.md to see where you are. Advance the build by exactly ONE green
checkpoint (see BUILD-BRIEF §7):
  - work the lowest phase whose Definition of Done is not yet green;
  - implement the smallest unit that moves it forward;
  - run `uv run pytest -q` (and `-m db` if the DB is up) until green;
  - update PROGRESS.md (done / current phase / next action / NEEDS-DECISION);
  - `git add -A && git commit` with a clear message, then `git push`.
Never weaken the constitution (BUILD-BRIEF §1) to pass a test. Do not stall on
ambiguity: log it under NEEDS-DECISION, pick the most reversible default, note
it, and continue. When ALL phases' DoD are green, write "ALL PHASES COMPLETE" as
the first line of PROGRESS.md and stop.
EOF
)

for i in $(seq 1 "$MAX_ITERS"); do
  echo "=== run_night iteration $i/$MAX_ITERS ==="
  if [ -f "$PROGRESS" ] && head -1 "$PROGRESS" | grep -q "ALL PHASES COMPLETE"; then
    echo "All phases complete. Stopping."
    exit 0
  fi
  claude --dangerously-skip-permissions -p "$PROMPT" || {
    echo "claude exited non-zero on iteration $i; retrying after backoff"
    sleep $(( i < 5 ? i * 2 : 10 ))
  }
done

echo "Reached MAX_ITERS=$MAX_ITERS without ALL PHASES COMPLETE. See PROGRESS.md."
