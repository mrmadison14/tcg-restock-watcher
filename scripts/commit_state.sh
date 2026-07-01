#!/usr/bin/env bash
set -euo pipefail

git config user.name "tcg-watcher-bot"
git config user.email "actions@users.noreply.github.com"
git add state/
if git diff --staged --quiet; then
  echo "no state changes"
  exit 0
fi
reconcile_cmd="${RECONCILE_CMD:-uv run python -m tcg_watcher.reconcile state}"
for attempt in 1 2 3 4 5 6; do
  git fetch origin main
  $reconcile_cmd
  git reset --mixed origin/main
  git add state/
  if git diff --staged --quiet; then
    echo "converged: nothing to push"
    exit 0
  fi
  git commit -m "state: update snapshots [skip ci]"
  if git push origin HEAD:main; then
    echo "pushed on attempt $attempt"
    exit 0
  fi
  echo "push rejected on attempt $attempt; retrying"
  sleep 3
done
echo "commit-state failed after retries" >&2
exit 1
