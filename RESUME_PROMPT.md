# Resume Prompt — tcg-restock-watcher

Paste-and-go prompt for a fresh Claude session. Self-contained — no prior conversation context required. Single-project session (no sibling repos).

=== START PROMPT ===

I'm resuming work on `tcg-restock-watcher` at `/Users/jmadison/workspace/tcg-restock-watcher`. It's a personal (non-Agent-Smith) tool that polls TCG stores every ~5 min for sealed Pokémon / One Piece / Dragon Ball product and posts restock / new-listing / preorder / price-change alerts to Discord, with TCGplayer below-market deal-flagging. Python 3.13 + uv + httpx, no DB/framework/UI. Two run paths now: a **Mac launchd residential-IP runner** (primary, beats Cloudflare 429s) + **GitHub Actions** (backstop); state is committed back to the repo each run.

## Where things stand (2026-07-10, session 12)

🟢 LIVE + autonomous. Last **human** commit `main` = **`73c4d7f1`** (pushed); HEAD advances via `tcg-watcher-bot` `state:` commits every few min (expected, not drift). **31 stores, 169 tests** green, dev checkout clean. This session's arc (newest first):
- **Egress fix — Mac runner is now PRIMARY (session 12).** GitHub's shared runner IPs hit an evening Cloudflare 429 storm (`ok=3 failed=25` at peak; only non-Cloudflare stores got through). Chose Option C: a launchd job runs the watcher from the Mac's residential IP every 5 min (~6.5 min effective) → verified **`ok=31 failed=0`**. GitHub Actions stays as the asleep backstop. Agent: `com.mrmadison.tcg-restock-watcher`, runs from a **dedicated clone** `~/workspace/tcg-restock-watcher-runner`.
- **Caught+fixed a launchd-PATH bug (`8056e70d`):** first run's `commit_state.sh` failed (`uv: command not found` — launchd's minimal PATH) → state didn't push → would've re-fired alerts. Fixed by exporting PATH in `run_local.sh`; re-verified clean (`commit_state pushed on attempt 1`).
- **+3 stores → 31 (`6c4ec865`, `1fce5a9b`):** sakurascardshop (full-crawl), galactictoys + tradingcardmarket (both via new **`filter_collections`** mode — fetch named collections but still apply the sealed+franchise filter, for big multi-hobby Shopify stores).
- **429 fail-fast (`2a1a646e`) + hourly schedule backstop (`b0813958`) + rarecandy widened ~85→237 via `api.rarecandy.com/graphql` (`866d40c0`).**

## Uncommitted / in-flight state

- Staged: nothing.
- Unstaged / modified: nothing in the dev checkout (clean, synced to `origin/main`). The runner clone holds a gitignored `.envrc` (Discord webhooks, mode 0600 — intentional, never committed).
- Failing or skipped tests: none (169 passed).
- Background jobs / open processes: **the Mac launchd agent `com.mrmadison.tcg-restock-watcher` is LOADED and running** (~6.5-min cadence). Logs to `~/Library/Logs/tcg-restock-watcher.log`.
- **Exact next command:** `cd /Users/jmadison/workspace/tcg-restock-watcher && git pull --rebase && uv run pytest -q`

## Read these first (in order)
1. `/Users/jmadison/workspace/tcg-restock-watcher/SESSION_HISTORY.md` — session-12 entry (top) = full arc, the launchd-PATH gotcha, and the open cron-job.org item.
2. `/Users/jmadison/workspace/tcg-restock-watcher/docs/LOCAL_RUNNER.md` — how the Mac runner is wired (clone, .envrc, plist, cron-job.org coordination).
3. `/Users/jmadison/workspace/tcg-restock-watcher/docs/superpowers/EGRESS_IP_SCOPING.md` — why Option C (Mac) over proxy/VPS.
4. `/Users/jmadison/workspace/tcg-restock-watcher/README.md` — as-built (31-store table, filter_collections, 429 story).
5. `/Users/jmadison/workspace/tcg-restock-watcher/config.toml` — 31 stores incl. the 3 new + `filter_collections` blocks.

## Verification commands (run first to confirm no drift)

```bash
cd /Users/jmadison/workspace/tcg-restock-watcher
git pull --rebase                                   # bot commits state ~every few min; sync first
git status -sb                                      # expect: clean, up to date with origin/main
uv run pytest -q                                    # expect: 169 passed
launchctl list | grep tcg-restock-watcher           # expect: agent listed (Mac runner live)
tail -3 ~/Library/Logs/tcg-restock-watcher.log      # expect: a recent "[<ts>] OK"
gh run list --workflow=watch --limit 3              # backstop; may be 429-degraded at peak (expected)
```
If tests < 169 or stores ≠ 31, or the launchd agent is absent, STOP and reconcile against the docs above before changing anything. A 429-degraded GitHub `watch` run is expected at peak — the Mac runner is what keeps coverage green.

## Key reference values (no credentials)

| Thing | Value |
|---|---|
| Last human commit | **`73c4d7f1`** (docs: session-12 log); HEAD advances via bot `state:` commits |
| Repo | github.com/mrmadison14/tcg-restock-watcher (public); commit identity `mrmadison14 <mr.madison@gmail.com>` |
| Stores | 31 (27 Shopify inc. 3 `filter_collections`, rarecandy Next.js/GraphQL, 2 Wix) |
| Tests | 169 passing |
| Mac runner | launchd `com.mrmadison.tcg-restock-watcher`, StartInterval 300, from clone `~/workspace/tcg-restock-watcher-runner`; wrapper `scripts/run_local.sh`; log `~/Library/Logs/tcg-restock-watcher.log` |
| Discord | `#deals` (loud @here) + `#tracker` (quiet) — webhook URLs live ONLY in the runner clone's gitignored `.envrc` (validated 204) |
| GitHub backstop | `watch.yml` (hourly `schedule:` cron + cron-job.org `workflow_dispatch`); `timeout-minutes: 20` |
| cron-job.org | fine-grained PAT, Actions r+w; **rotate before expiry** (`docs/PAT_ROTATION.md`) |
| filter_collections stores | galactictoys (pokemon-tcg, one-piece-tcg, pre-orders), tradingcardmarket (pokemon, one-piece, presell) |

## Hard rules & conventions

- Python 3.13, uv only (not pip/poetry). httpx for HTTP. **No comments in production code. No new deps without asking.**
- **Sealed-only scope** — singles are out of scope (they trip Cloudflare 429).
- Commit code/docs as `mrmadison14`; end commit messages with the `Co-Authored-By: Claude Opus 4.8` trailer. TDD (RED→GREEN). **Present diffs before pushing live changes.** Verify before claiming done.
- The bot commits `state/` to `main` constantly → **always `git pull --rebase` before pushing.**
- **The Mac runner clone is separate from the dev checkout on purpose** — never run `run_local.sh` from the dev checkout (it `git reset --hard`s to origin).

## Gotchas

- **launchd has a minimal PATH** — `run_local.sh` must `export PATH` incl. `~/.local/bin` or `uv`-calling child scripts (`commit_state.sh` reconcile) fail with `uv: command not found`, state never pushes, and alerts re-fire. (Fixed in `8056e70d`.)
- **`filter_collections=true`**: fetch named collections but STILL apply `keep_sealed(filter_franchises(...))`; the `<franchise>:` prefix is advisory (filter re-derives). For big multi-hobby Shopify stores — avoids full-crawling a huge catalog while dropping non-sealed/non-franchise.
- **Sealed-marker matching is word-boundary** (`shopify._has_marker`) — bare substrings falsely matched (`tin`⊂`setting`, `case`⊂`showcase`); keep the `\b`.
- **429 fails fast** in the fetch path (`http._RETRY_STATUS` excludes 429); the Discord poster still honors Retry-After. Next dispatch is the retry.
- **Expanding a seeded store's collections → drop its `state/*.json` first** for a silent re-seed (else a NEW-listing burst; flood-capped at 25/store to a summary).
- **rarecandy** = `api.rarecandy.com/graphql` `RareFindCatalog(page, filters={categories:[sealed],sortBy:newest})`; needs exact `operationName` + non-null `$page: Int!`; multi-category filters OR not AND (franchise filtered client-side).
- `commit_state.sh` uses `git reset --mixed origin/main` (never `--soft`) — concurrency-safe against parallel Mac+GitHub pushes.

## Decision tree — pick your next move

(A) **Confirm the Mac runner is healthy at steady state + coordinate the GitHub backstop.** Run the verification block; `tail` the runner log for a rhythm of `[ts] OK`. Then the one open owner action: **slow/pause the cron-job.org 5-min dispatch** so GitHub stops 429-flailing at peak (concurrency-safe either way — it's just failure-email noise). The workflow's hourly `schedule:` cron stays as the Mac-asleep backstop.
(B) **Add more stores** (recurring — user sends a store-list image). Pipeline: probe `/products.json` + currency + catalog size, dry-run through the REAL adapter+filters, then full-crawl small/clean, curate big/singles-heavy, or `filter_collections` for multi-hobby.
(C) **Ops/maintenance** — rotate the cron-job.org PAT before expiry (`docs/PAT_ROTATION.md`); or reconsider egress (a residential proxy, `EGRESS_IP_SCOPING.md` Option A, if the Mac-uptime dependency proves annoying).
(D) Something else — describe.

=== END PROMPT ===

## Note for the next session

Session 12 solved the evening Cloudflare-429 storm by standing up a Mac launchd runner on the residential IP (Option C from the egress scoping doc) — it's LIVE and verified `ok=31 failed=0`, with GitHub Actions demoted to an asleep-backstop. The one thing left is the owner's action to slow/pause cron-job.org so the redundant GitHub 5-min dispatch stops 429-flailing (it's harmless, just noisy). A subtle but important gotcha bit us and is now fixed + documented: launchd's minimal PATH broke `commit_state.sh`'s `uv` call, which would have caused a re-alert loop — the fix (export PATH in `run_local.sh`) plus the "run only from the dedicated clone" rule are the load-bearing bits for the runner. Standing user preferences: TDD with RED→GREEN, present diffs before any live push, `git pull --rebase` before pushing (bot commits state constantly), commit as `mrmadison14` with the Co-Authored-By trailer, sealed-only scope, no comments in production code, and verify-before-claiming-done (spot-check live run output, don't trust a summary). Discord webhooks live only in the runner clone's gitignored `.envrc` — never put them in the repo or a resume prompt.
