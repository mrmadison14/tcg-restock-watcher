# Resume Prompt — tcg-restock-watcher

Paste-and-go prompt for a fresh Claude session. Self-contained — no prior conversation context required. Single repo (no siblings).

=== START PROMPT ===

I'm resuming work on `tcg-restock-watcher` at `/Users/jmadison/workspace/tcg-restock-watcher`. It's a personal (non-Agent-Smith) tool that polls TCG stores every ~5 min for sealed Pokémon / One Piece / Dragon Ball product (booster boxes, ETBs, bundles, tins, blisters) and posts restock / new-listing / preorder / price-change alerts to Discord — with TCGplayer below-market **deal-flagging**. Stack: Python 3.13 + uv + httpx, no DB/framework/UI. Runs free on GitHub Actions (personal GitHub `mrmadison14`); state committed back to the repo.

## Where things stand (2026-07-01, session 4)

🟢 LIVE + autonomous + concurrency-safe — and now **clobber-safe for concurrent non-`state/` pushes**. `main` HEAD advances via the Actions bot's `state:`/`data:` commits (expected, not drift); this session's fix commits are `73f62b9` (fix) + `ad25dea` (restore), now under later bot commits. This session: found & fixed a **live doc-clobber data-loss bug** (off the decision-tree), then triaged the user's store-list image for easy Shopify adds.
- **commit-state clobber fix (the big one):** `watch.yml` did `git reset --soft origin/main`, keeping the runner's stale index; since `reconcile` only re-materializes `state/`, a concurrent human push's non-`state/` files (the session-3 handoff docs) got committed as deletions. Fix: **`git reset --mixed`** re-bases the index onto the fetched tip → only `state/` diffs are ever staged. Extracted to **`scripts/commit_state.sh`** (+ `RECONCILE_CMD` seam); `watch.yml` calls it; new **`tests/test_commit_state.py`** (RED on `--soft`, GREEN on `--mixed`). Restored the 4 clobbered files. Prod-verified (2 fixed runs + 2 bot state commits, docs intact).
- **store triage:** of 14 domains in the store-list image, 2 already tracked (rarecandy, collectorstore); **9 are Shopify = easy config-only adds** (3kcollectables, doubleinfinitygaming, paladincards20, realgoodeal, shinypax, shopchieffpokeman, spoilsandloot, tygerstcgden, zulusgames). Not-easy: blowoutcards (non-Shopify, big), missionreadycollectibles (401), tcgsorted (shop.app, domain TBD). **10 added + seeded live** (`ok=20 failed=0`): 7 full-crawl + realgoodeal / zulusgames / doubleinfinitygaming curated. tcgsorted → `shop.tcgsorted.com` (apex 404s); doubleinfinitygaming via its sealed-only "new and hot" collections. Ruled out: blowoutcards (Imperva JS-WAF), missionreadycollectibles (merchant password-lock). **20 stores** total.
- **rarecandy** (session 3): parses `__NEXT_DATA__` Apollo cache from `/shop`+`/discover`; ~51 sealed variants. **PAT rotated**; **Discord inter-post delay** live (`post_delay_seconds`, default 1.0s).

## Uncommitted / in-flight state
- Staged: nothing
- Unstaged / modified: nothing (working tree clean, up to date with origin/main)
- Failing or skipped tests: none (107 passed)
- Background jobs / open processes: none
- **Exact next command:** `cd /Users/jmadison/workspace/tcg-restock-watcher && git pull --rebase && uv run pytest -q`

## Read these first (in order)
1. `SESSION_HISTORY.md` — session-4 entry (top) = full arc + next steps.
2. `docs/superpowers/PHASE2_SCOPING.md` — Phase 2 (Wix ×2) feasibility + effort (the main open work).
3. `README.md` — as-built overview (10 stores, sealed-only, 429 story).
4. `config.toml` — 20 stores + curated collections + `[pricing]` + `[thresholds]`.

## Verification commands (run first to confirm no drift)
```bash
cd /Users/jmadison/workspace/tcg-restock-watcher
git pull --rebase                                   # bot commits state/data ~every 5 min; sync first
git status -sb                                      # expect: clean, up to date with origin/main
uv run pytest -q                                    # expect: 107 passed
gh run list --workflow=watch --limit 5              # expect: recent runs = success (was ~38% failing pre-`2c8be31`)
gh run list --workflow=build-index --limit 2        # expect: daily run success
```
If `watch` runs show `failure`, run `gh run view <id> --log-failed`. The rebase-conflict and doc-clobber failures are fixed; a new failure is more likely a transient fetch or the PAT expiring. If tests < 107 or stores ≠ 20, STOP and reconcile against the docs above before changing anything.

## Key reference values (no credentials)
| Thing | Value |
|---|---|
| HEAD (indicative) | session-4 fix `73f62b9` + restore `ad25dea` (advances via bot commits) |
| Repo | github.com/mrmadison14/tcg-restock-watcher (public) |
| Tests | 107 passing |
| Stores | 20 (19 Shopify + rarecandy Next.js) |
| Workflows | `watch.yml` (cron+dispatch; **concurrency-safe commit-state retry loop**, `timeout-minutes: 10`; commits `state/`), `build-index.yml` (daily 20:30 UTC; commits `data/`), `spike.yml` (manual) |
| Autonomous trigger | cron-job.org job → POST `…/actions/workflows/watch.yml/dispatches` body `{"ref":"main"}` every 5 min |
| cron-job.org PAT | ✅ **rotated 2026-07-01** (fine-grained, Actions r+w, this repo). Rotate again before its expiry. Runbook: `docs/PAT_ROTATION.md` |
| Phase-3 index | `data/price_index.json` (pokemon 2595 / one piece 255 / dragon ball 588 sealed) + `data/fx.json` (CAD 1.42) |
| tcgcsv categories | pokemon 3 & 85, one piece 68, dragon ball 23 / 27 / 80 |
| Discord webhooks | `DISCORD_DEALS_WEBHOOK` (loud @here) · `DISCORD_TRACKER_WEBHOOK` (quiet) — GH repo secrets |
| Deal threshold | 10% under market (`[pricing].deal_threshold`) |
| Post delay | `[thresholds].post_delay_seconds = 1.0` (proactive anti-429) |

## Hard rules & conventions
- Python 3.13, uv only (not pip/poetry). httpx for HTTP. **No comments in production code. No new deps without asking.**
- **Sealed-only scope** — singles are out of scope (they trigger the Cloudflare 429).
- Curated store (has `collections`): products trusted (no filter), tagged with the config franchise. Full-crawl store (no `collections`, incl. rarecandy): `keep_sealed(filter_franchises(...))`. **Never full-crawl a big store / whole marketplace.**
- Keep the polite throttle in `http.py` (min_interval + Retry-After + backoff) for BOTH the fetch (`make_httpx_get`) and the Discord poster (`make_discord_poster`).
- The Actions bot commits `state/` + `data/` to `main` every few min → **always `git pull --rebase` before pushing.**
- TDD (RED→GREEN); review for non-trivial changes; present diffs before pushing live changes. End commit messages with the `Co-Authored-By: Claude Opus 4.8` trailer.

## Gotchas
- **commit-state lives in `scripts/commit_state.sh` (called by `watch.yml`) — do NOT inline it back or revert to `git pull --rebase`.** It's a fetch→reconcile→`git reset --mixed origin/main`→`git add state/`→commit→push retry loop. Two overlapping runs rewrite `last_run` in every state file, so a naive rebase conflicts on all of them; `tcg_watcher.reconcile` = newest-`last_run`-per-file + materializes origin-only files. **Keep `--mixed` (never `--soft`):** soft keeps the runner's stale index, so a concurrent human push's non-`state/` files (e.g. docs) get committed as deletions — this is how the session-3 handoff docs got clobbered (session 4). `RECONCILE_CMD` env overrides the reconcile command for tests; `tests/test_commit_state.py` guards the clobber (RED on `--soft`, GREEN on `--mixed`).
- **rarecandy:** `__NEXT_DATA__` → `props.pageProps.__APOLLO_STATE__`; iterate `RareFind:` entities → their `Product` ref; url = base/`{rareFind.slug}` (store-prefixed & `/product/` both 404); franchise tags `onepiece`/`dbz` normalized to `one piece`/`dragon ball` so `filter_franchises` matches. GraphQL host `api.rarecandy.com/graphql` introspection is 400 → HTML route only; no pagination in HTML → ~85 browse-surface listings, not the full catalog.
- Discord `@here` needs `allowed_mentions:{parse:["everyone"]}`; poster retries 429 `Retry-After` + proactive `post_delay_seconds` between posts.
- Box-vs-`case` fuzzy trap: `match.best_match` rejects size-qualifier mismatches via `_SIZE_TOKENS` — don't remove that guard.
- tcgcsv 401s default-UA fetchers; the Chrome UA in `http.py` bypasses it. GitHub free-tier throttles frequent `schedule` crons (~2–3h) — that's why cron-job.org does the 5-min cadence (paying GitHub does NOT help).
- A launchd pinger was prepared but **NOT loaded** (`~/.claude/scripts/tcg-watch-ping.sh` + `~/Library/LaunchAgents/com.mrmadison.tcg-watch-ping.plist`) — superseded by cron-job.org.

## Decision tree — pick your next move
(A) ✅ **DONE (session 4): 10 stores added + seeded live, all follow-ups resolved.** Full-crawl: `3kcollectables`, `paladincards20`, `shopchieffpokeman`, `spoilsandloot`, `shinypax`, `tygerstcgden`, `tcgsorted` (=`shop.tcgsorted.com`). Curated: `realgoodeal` (+`dragon-ball-super`, `pokemon-sealed-cases`), `zulusgames` (+`pokemon-scarlet-violet`, `pokemon-imported-product`), `doubleinfinitygaming` (sealed-only "new and hot" collections). **Not addable:** `blowoutcards` (Magento + Imperva JS-challenge WAF → needs headless browser), `missionreadycollectibles` (merchant storefront password-lock). No open store follow-ups.
(B) **Phase 2 — Wix ×2** (`pokelegendstcg` + `bulbacards`): the harder non-Shopify work. Per `docs/superpowers/PHASE2_SCOPING.md`, both are Wix Stores whose SSR HTML only exposes page 1 (~16 items); the full catalog needs an access-token + storefront **GraphQL POST** → requires a POST-capable `http` helper (extend `make_httpx_get`). Decide **full-GraphQL** (real coverage, ~2–2.5d) vs **best-effort SSR** (~1d, low value). Make the gallery route config-driven (bulbacards `/shop` 404s) and verify Wix id-stability before enabling alerts. One shared `adapters/wix.py` serves both sites.
(C) **Widen rarecandy** beyond the ~85 browse-surface listings if the `rareFindCatalog(page)` GraphQL path can be made to work (introspection currently 400).
(D) Something else — describe.

=== END PROMPT ===

## Note for the next session

Session 3 opened by verifying the "done" system and immediately found it was **failing 38% of runs** — a commit-state rebase conflict under run overlap that dropped state and re-alerted — fixed with a reconcile+retry loop, proven by a real-git simulation and a 60-min 0/17 prod monitor. Then it cleared the security loose end (**rotated the exposed PAT**, revoked the old, verified continuity), added a **proactive Discord inter-post delay** (B), and began Phase 2 by shipping the **rarecandy** adapter (Next.js `__NEXT_DATA__` route; seeded 51 sealed live). The **Wix pair is the remaining Phase 2 work** and is genuinely harder (needs POST/token plumbing — see `PHASE2_SCOPING.md`). Standing user preferences observed: address him as **"James Madison"** (never a nickname); **verify before claiming done** (again vindicated — the "done" pipeline was silently failing); **prefer free/no-cost solutions**; TDD RED→GREEN + review for non-trivial work; `git pull --rebase` before pushing (the Actions bot writes to `main` continuously); and **present diffs for review before pushing** live changes.
