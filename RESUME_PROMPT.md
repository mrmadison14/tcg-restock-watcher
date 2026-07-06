# Resume Prompt — tcg-restock-watcher

Paste-and-go prompt for a fresh Claude session. Self-contained — no prior conversation context required. Single repo (no siblings).

=== START PROMPT ===

I'm resuming work on `tcg-restock-watcher` at `/Users/jmadison/workspace/tcg-restock-watcher`. It's a personal (non-Agent-Smith) tool that polls TCG stores every ~5 min for sealed Pokémon / One Piece / Dragon Ball product (booster boxes, ETBs, bundles, tins, blisters) and posts restock / new-listing / preorder / price-change alerts to Discord — with TCGplayer below-market **deal-flagging**. Stack: Python 3.13 + uv + httpx, no DB/framework/UI. Runs free on GitHub Actions (personal GitHub `mrmadison14`); state committed back to the repo.

## Where things stand (2026-07-06)

🟢 LIVE + autonomous + concurrency-safe + clobber-safe. **25 stores, 131 tests**, working tree clean; `main` HEAD advances via the Actions bot's `state:` commits every ~5 min (expected, not drift — the last *human* commits are the 07-03 store adds, now buried under bot commits). Long session-4 arc across 07-01→07-03; newest-first:
- **rarecandy links fixed (`ffdbd7f`, 07-02):** alert URLs were `base/{slug}`, which Next.js matched to the `/[storeSlug]` route → **empty store page (200 soft-404)**. Real route (from the Next build manifest) is `/[storeSlug]/shop/[rareFindSlug]`; adapter now resolves the seller (Apollo ref OR inline `{slug}` object per SSR variant) and builds `base/{store.slug}/shop/{rareFind.slug}`. Live-verified 4/4 URLs hit the detail route.
- **duplicate posts fixed (`d0cb9cc`, 07-02):** rarecandy's rotating `/shop`+`/discover` surfaces made departed variants re-fire NEW/PREORDER (~2,048 repeats/day, same item up to 27×). New `state.merge_snapshot` carries variants forward with a `last_seen` stamp (14-day TTL) — applies to ALL stores; rarecandy state backfilled with the 24h union. Live: ~22 events/run → 0–1.
- **+15 stores → 25 total** (10 on 07-01 from store-list image #1, 5 on 07-03 from image #2). Full-crawl small/clean stores + curated big/singles-heavy ones (`realgoodeal`, `zulusgames`, `doubleinfinitygaming`, `smokeandmirrorshobby`). Ruled out: `blowoutcards` (Imperva JS-WAF), `missionreadycollectibles` (merchant password-lock), `smokemon07` (live-rips/PSA store, 0 watchable). All seeded silently (carry-over fix → no burst).
- **earlier this arc (07-01):** commit-state clobber fix (`git reset --mixed`, see gotchas), rarecandy `singles`-tag exclusion, and the WS1 30-day-review hardening merged to `main` (6 fixes: per-store post isolation, O(1) price index, fuzzy pre-filter, reconcile transient-vs-missing, poster wait caps, rarecandy warning).

## Uncommitted / in-flight state
- Staged: nothing
- Unstaged / modified: nothing (working tree clean, up to date with origin/main)
- Failing or skipped tests: none (131 passed)
- Background jobs / open processes: none
- **Exact next command:** `cd /Users/jmadison/workspace/tcg-restock-watcher && git pull --rebase && uv run pytest -q`

## Read these first (in order)
1. `SESSION_HISTORY.md` — session-4 entry (top) = full arc + next steps.
2. `docs/superpowers/PHASE2_SCOPING.md` — Phase 2 (Wix ×2) feasibility + effort (the main open work).
3. `README.md` — as-built overview (25-store table, sealed-only, 429 story).
4. `config.toml` — 25 stores + curated collections + `[pricing]` + `[thresholds]`.

## Verification commands (run first to confirm no drift)
```bash
cd /Users/jmadison/workspace/tcg-restock-watcher
git pull --rebase                                   # bot commits state/data ~every 5 min; sync first
git status -sb                                      # expect: clean, up to date with origin/main
uv run pytest -q                                    # expect: 131 passed
gh run list --workflow=watch --limit 5              # expect: recent runs = success (was ~38% failing pre-`2c8be31`)
gh run list --workflow=build-index --limit 2        # expect: daily run success
```
If `watch` runs show `failure`, run `gh run view <id> --log-failed`. The rebase-conflict and doc-clobber failures are fixed; a new failure is more likely a transient fetch or the PAT expiring. If tests < 131 or stores ≠ 25, STOP and reconcile against the docs above before changing anything.

## Key reference values (no credentials)
| Thing | Value |
|---|---|
| HEAD (indicative) | last human commit `861fc32` (docs: sync to 25 stores); advances via bot `state:` commits |
| Repo | github.com/mrmadison14/tcg-restock-watcher (public) |
| Tests | 131 passing |
| Stores | 25 (24 Shopify + rarecandy Next.js) |
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
- **rarecandy:** `__NEXT_DATA__` → `props.pageProps.__APOLLO_STATE__`; iterate `RareFind:` entities → their `Product` ref; **url = base/`{store.slug}/shop/{rareFind.slug}`** (per the Next build-manifest route `/[storeSlug]/shop/[rareFindSlug]`; bare `/{slug}` matches the `/[storeSlug]` route → renders an EMPTY store page as a 200 soft-404, so title/name-in-HTML checks lie — verify by matching `__NEXT_DATA__`'s `page` field to the detail route). The RareFind's `store` field is a normalized Apollo ref on some SSR variants and an inline `{slug}` object on others — resolve both; skip listings with no resolvable seller; franchise tags `onepiece`/`dbz` normalized to `one piece`/`dragon ball` so `filter_franchises` matches. GraphQL host `api.rarecandy.com/graphql` introspection is 400 → HTML route only; no pagination in HTML → ~85 browse-surface listings, not the full catalog. **`is_sealed` = `sealed` tag AND NOT `singles` tag** — rarecandy tags graded slabs / named single cards with a catch-all dump that *includes* `sealed`, so the `singles` exclusion is load-bearing (removing it re-admits CGC/PSA singles into the sealed feed).
- Discord `@here` needs `allowed_mentions:{parse:["everyone"]}`; poster retries 429 `Retry-After` + proactive `post_delay_seconds` between posts.
- Box-vs-`case` fuzzy trap: `match.best_match` rejects size-qualifier mismatches via `_SIZE_TOKENS` — don't remove that guard.
- **Snapshots are carry-over, not replace** (`state.merge_snapshot`, both runner save paths): variants that leave the fetch surface stay in state with a `last_seen` stamp (pruned after 14 days) so rotation re-entry doesn't re-fire NEW/PREORDER. This killed rarecandy's ~2,000 repeat posts/day (its `/shop`+`/discover` browse surfaces rotate the catalog every run). Don't revert to `build_snapshot` in the runner; unparseable `last_seen`/`now_iso` stamps are tolerated (kept, no prune).
- tcgcsv 401s default-UA fetchers; the Chrome UA in `http.py` bypasses it. GitHub free-tier throttles frequent `schedule` crons (~2–3h) — that's why cron-job.org does the 5-min cadence (paying GitHub does NOT help).
- A launchd pinger was prepared but **NOT loaded** (`~/.claude/scripts/tcg-watch-ping.sh` + `~/Library/LaunchAgents/com.mrmadison.tcg-watch-ping.plist`) — superseded by cron-job.org.

## Decision tree — pick your next move
(A) **Phase 2 — Wix ×2** (`pokelegendstcg` + `bulbacards`): the main remaining feature work. Per `docs/superpowers/PHASE2_SCOPING.md`, both are Wix Stores whose SSR HTML only exposes page 1 (~16 items); the full catalog needs an access-token + storefront **GraphQL POST** → requires a POST-capable `http` helper (extend `make_httpx_get`). Decide **full-GraphQL** (real coverage, ~2–2.5d) vs **best-effort SSR** (~1d, low value). Make the gallery route config-driven (bulbacards `/shop` 404s) and verify Wix id-stability before enabling alerts. One shared `adapters/wix.py` serves both sites.
(B) **Add more stores** (recurring — the user has sent 2 store-list images so far). Pipeline that worked twice: probe each domain for Shopify (`/products.json` 200) + currency + catalog size, dry-run through the REAL adapter+filters (`keep_sealed(filter_franchises())`), then **full-crawl small/clean stores, curate big/singles-heavy ones** (find sealed-only `collections`; reject any with singles/accessory contamination). Reuse the scratchpad probe scripts pattern (`probe_new6.py`, `dryrun_stores.py`, `verify_curated.py`). Expanding a *seeded* store's collections → drop its `state/*.json` first for a silent re-seed.
(C) **Widen rarecandy** beyond the ~85 browse-surface listings if the `rareFindCatalog(page)` GraphQL path can be made to work (introspection currently 400).
(D) **Monitor run health / duration.** 25 stores now watch ~2,100 more variants than at 10 stores, so `watch` runs are longer (throttled fetches, 2.5s min-interval). Still inside the `timeout-minutes: 10` job cap, but if runs start failing on timeout, bump `timeout-minutes` in `.github/workflows/watch.yml`. Also: cron-job.org PAT will eventually expire (rotate per `docs/PAT_ROTATION.md`).
(E) Something else — describe.

=== END PROMPT ===

## Note for the next session

Session 3 opened by verifying the "done" system and immediately found it was **failing 38% of runs** — a commit-state rebase conflict under run overlap that dropped state and re-alerted — fixed with a reconcile+retry loop, proven by a real-git simulation and a 60-min 0/17 prod monitor. Then it cleared the security loose end (**rotated the exposed PAT**, revoked the old, verified continuity), added a **proactive Discord inter-post delay** (B), and began Phase 2 by shipping the **rarecandy** adapter (Next.js `__NEXT_DATA__` route; seeded 51 sealed live). The **Wix pair is the remaining Phase 2 work** and is genuinely harder (needs POST/token plumbing — see `PHASE2_SCOPING.md`). Standing user preferences observed: address him as **"James Madison"** (never a nickname); **verify before claiming done** (again vindicated — the "done" pipeline was silently failing); **prefer free/no-cost solutions**; TDD RED→GREEN + review for non-trivial work; `git pull --rebase` before pushing (the Actions bot writes to `main` continuously); and **present diffs for review before pushing** live changes.
