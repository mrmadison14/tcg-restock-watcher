# Local (residential-IP) runner — Option C

**Why:** GitHub's shared runner IPs get Cloudflare-429'd at evening peak (see
`docs/superpowers/EGRESS_IP_SCOPING.md`). Running the watcher from the Mac's residential IP on a
launchd 5-min cadence beats the 429s. GitHub Actions stays as the overnight/asleep backstop.

## Design

- **Primary:** launchd runs `scripts/run_local.sh` every 300s from a **dedicated clone** (never the
  dev checkout — the script `git reset --hard`s to `origin/main`, and refuses to run on a dirty tree).
- **Backstop:** GitHub Actions. cron-job.org's 5-min `workflow_dispatch` should be **paused or slowed**
  (below) so GitHub isn't 429-flailing every 5 min; the workflow's hourly `schedule:` cron remains the
  fallback for when the Mac is asleep.
- **State** is still committed to `origin/main` by `commit_state.sh` (concurrency-safe `--mixed`
  reconcile), so Mac runs and any GitHub runs never clobber each other.
- Fetches from a residential IP → all 31 stores succeed (verified: local dry-runs pulled every store).

## One-time setup

1. **Dedicated clone** (recommended `~/workspace/tcg-restock-watcher-runner`):
   ```sh
   git clone https://github.com/mrmadison14/tcg-restock-watcher.git ~/workspace/tcg-restock-watcher-runner
   cd ~/workspace/tcg-restock-watcher-runner && uv sync --frozen
   ```
2. **Webhooks** — create `.envrc` in the clone (gitignored, never committed):
   ```sh
   printf 'export DISCORD_DEALS_WEBHOOK="…"\nexport DISCORD_TRACKER_WEBHOOK="…"\n' \
     > ~/workspace/tcg-restock-watcher-runner/.envrc
   ```
   Paste the two webhook URLs (from Discord → channel → Integrations → Webhooks, or your saved
   GitHub secrets). **Do not paste them into chat.**
3. **Install the launchd agent** — copy the template, substituting the clone path:
   ```sh
   sed 's#__RUNNER_CLONE__#'"$HOME"'/workspace/tcg-restock-watcher-runner#' \
     ~/workspace/tcg-restock-watcher-runner/ops/com.mrmadison.tcg-restock-watcher.plist \
     > ~/Library/LaunchAgents/com.mrmadison.tcg-restock-watcher.plist
   launchctl load ~/Library/LaunchAgents/com.mrmadison.tcg-restock-watcher.plist
   ```
4. **Slow the GitHub backstop** (cron-job.org): pause the 5-min job, or drop it to ~30 min, so GitHub
   stops 429-flailing at peak. The workflow's hourly `schedule:` cron covers Mac-asleep gaps.

## Verify

```sh
tail -f ~/Library/Logs/tcg-restock-watcher.log      # expect: [ts] OK every ~5 min
# newest run committed by the Mac should show ok=31 failed=0
git -C ~/workspace/tcg-restock-watcher-runner log -1 --format='%an %s'
```

## Notes / ops

- Logs: `~/Library/Logs/tcg-restock-watcher.log` (wrapper OK/FAIL) + `…launchd.log` (stdout/err).
- Mac asleep → launchd fires the missed run on wake; overnight gaps are covered by the GitHub backstop.
- Unload: `launchctl unload ~/Library/LaunchAgents/com.mrmadison.tcg-restock-watcher.plist`.
- The dedicated clone is intentionally separate from `~/workspace/tcg-restock-watcher` so the 5-min
  job never collides with active development in the dev checkout.
