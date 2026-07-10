#!/bin/sh
# Local (residential-IP) runner for the watcher — Option C.
# Runs on a launchd 5-min cadence from a DEDICATED clone (never the dev checkout:
# it hard-resets to origin/main). Reads Discord webhooks from a gitignored .envrc.
set -eu

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UV="${TCG_UV:-/Users/jmadison/.local/bin/uv}"
LOG="${TCG_LOG:-$HOME/Library/Logs/tcg-restock-watcher.log}"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

cd "$REPO"
[ -f "$REPO/.envrc" ] && . "$REPO/.envrc" || true

{
  if ! git diff --quiet HEAD 2>/dev/null; then
    echo "[$(ts)] FAIL: working tree dirty — run only from the dedicated runner clone"; exit 1
  fi
  if ! (git fetch --quiet origin main && git reset --hard --quiet origin/main); then
    echo "[$(ts)] FAIL: git sync"; exit 1
  fi
  if "$UV" run python -m tcg_watcher; then
    if sh "$REPO/scripts/commit_state.sh"; then echo "[$(ts)] OK"; else echo "[$(ts)] FAIL: commit_state"; exit 1; fi
  else
    echo "[$(ts)] FAIL: watcher"; exit 1
  fi
} >> "$LOG" 2>&1
