# Resume Prompt — tcg-restock-watcher

Paste-and-go prompt for a fresh Claude session. Self-contained — no prior conversation context required. Single repo (no siblings).

=== START PROMPT ===
I'm resuming work on `tcg-restock-watcher` at `/Users/jmadison/workspace/tcg-restock-watcher`. It's a personal (non-Agent-Smith) tool that polls TCG stores every ~5 min for sealed Pokémon / One Piece / Dragon Ball product (booster boxes, ETBs, bundles, tins, blisters) and posts restock / new-listing / preorder / price-change alerts to Discord — with TCGplayer below-market **deal-flagging**. Stack: Python 3.13 + uv + httpx, no DB/framework/UI. Runs free on GitHub Actions (personal GitHub `mrmadison14`); state committed back to the repo.

## Where things stand (2026-07-06, close of session 5)

🟢 LIVE + autonomous + concurrency-safe + clobber-safe. **26 stores, 139 tests**, working tree clean, synced to `origin/main`. `main` HEAD advances via the Actions bot's `state:` commits every ~5 min (expected, not drift — the last *human* commit is `f96a6318`, buried under bot commits within minutes). Session-5 arc (newest-first):
- **Phase 2 handed to Fable (`f96a6318`, `74a07bee`):** wrote `docs/superpowers/PHASE2_HANDOFF.md` — a zero-context entry brief for a fresh session to build the Wix ×2 adapter. This is the main open feature. **← next-session intent (A).**
- **N2 — rarecandy accessory guard (`fd84f2aa`, TDD +3):** title-based guard so playmats/binders/toploaders can't leak into the sealed feed. Root-cause investigation *disproved* the obvious tag-based fix: rarecandy applies garbage catch-all tag dumps, so a real ETB + a Commander Deck carry `accessories`+`merch`+`sealed` together — a tag exclusion would drop legit sealed product. Chose title-based; **`Sleeved Booster Pack` deliberately kept** (it IS sealed). No accessory leaks today (genuine accessories carry empty tags → already filtered); this closes the gap if rarecandy ever tags a playmat `sealed`.
- **N1 — price-change drift noise (`b2eda04a`, TDD +5):** skyboxct fired ~13 `#tracker` price posts/day. Forensic git-history replay (every state commit = a snapshot) proved it was **not ping-pong** (values never revisit) but **algorithmic repricing drift** on high-value boxes — $1–2 nudges (`$374→$373`, `$1424→$1428`) each clearing the absolute `$0.01` epsilon. Fix: `detect_events` now also requires a **relative** move ≥ `price_change_pct` (new `[thresholds]` key, default **0.05 = 5%**); abs epsilon kept as a floor; div-by-zero guarded. Deals are event-gated but ride on restocks/≥10% drops (all ≥5%) so none hidden. Replay: skyboxct price-change **69→33 (~13→~6/day, −52%); restock/preorder/new_product unchanged.**
- **watch timeout 10→20 min (`16b3bc0c`):** run durations crept to ~7–8 min at 26 stores vs the 10-min cap; doubled headroom (concurrency cancels overlaps so longer jobs won't stack).
- **+1 store → 26 (`60cceda3`):** added `pkmncolosseum` (Dead Draw Gaming, Pokémon-only Shopify, USD) — the ONLY new domain across two store-list images (07-03 + 07-06); every other domain already tracked or ruled out. Big singles catalog → **curated** to `all-pokemon-sealed` + type collections (adapter dedups). Live-verified: `[pkmncolosseum] seeded 9 watched variants (no alerts)`, `RUN: ok=26 failed=0 seeded=['pkmncolosseum']`.

## Uncommitted / in-flight state
- Staged: nothing. Unstaged / modified: nothing (working tree clean, up to date with `origin/main`).
- Failing or skipped tests: none (139 passed). Background jobs / open processes: none.
- **Exact next command:** `cd /Users/jmadison/workspace/tcg-restock-watcher && git pull --rebase && uv run pytest -q`

## Read these first (in order)
1. `SESSION_HISTORY.md` — session-5 entry (top) = full arc + next steps.
2. `docs/superpowers/PHASE2_HANDOFF.md` — the Phase 2 (Wix ×2) zero-context brief (the main open work).
3. `docs/superpowers/PHASE2_SCOPING.md` — the deep Wix feasibility study behind the brief.
4. `README.md` — as-built overview (26-store table, sealed-only, 429 story, `price_change_pct`).
5. `config.toml` — 26 stores + curated collections + `[thresholds]` (incl. `price_change_pct = 0.05`) + `[pricing]`.

## Verification commands (run first to confirm no drift)
```bash
cd /Users/jmadison/workspace/tcg-restock-watcher
git pull --rebase                                   # bot commits state/data ~every 5 min; sync first
git status -sb                                      # expect: clean, up to date with origin/main
uv run pytest -q                                    # expect: 139 passed
gh run list --workflow=watch --limit 5              # expect: recent runs = success
gh run list --workflow=build-index --limit 2        # expect: daily run success
```
If tests < 139 or stores ≠ 26, STOP and reconcile against the docs above before changing anything. If `watch` runs show `failure`, `gh run view <id> --log-failed` — the rebase-conflict/doc-clobber failures are fixed; a new failure is more likely a transient fetch, a run exceeding the (now 20-min) cap, or the PAT expiring.

## Key reference values (no credentials)
| Thing | Value |
|---|---|
| Last human commit | `f96a6318` (docs: Phase 2 handoff brief); HEAD advances via bot `state:` commits |
| Repo | github.com/mrmadison14/tcg-restock-watcher (public) |
| Tests | 139 passing |
| Stores | 26 (25 Shopify + rarecandy Next.js) |
| Commit identity | `mrmadison14 <mr.madison@gmail.com>` (personal) |
| Workflows | `watch.yml` (cron+dispatch; concurrency-safe commit-state retry loop, **`timeout-minutes: 20`**; commits `state/`), `build-index.yml` (daily 20:30 UTC; commits `data/`), `spike.yml` (manual) |
| Autonomous trigger | cron-job.org job → POST `…/actions/workflows/watch.yml/dispatches` body `{"ref":"main"}` every 5 min |
| cron-job.org PAT | fine-grained, Actions r+w, this repo; rotated 2026-07-01. **Rotate before expiry** — runbook `docs/PAT_ROTATION.md` |
| Phase-3 index | `data/price_index.json` (pokemon 2595 / one piece 255 / dragon ball 588 sealed) + `data/fx.json` (CAD 1.42) |
| tcgcsv categories | pokemon 3 & 85, one piece 68, dragon ball 23 / 27 / 80 |
| Discord webhooks | `DISCORD_DEALS_WEBHOOK` (loud @here) · `DISCORD_TRACKER_WEBHOOK` (quiet) — GH repo secrets |
| Deal threshold | 10% under market (`[pricing].deal_threshold`) |
| Price-change floor | `price_change_pct = 0.05` (5% relative) + `price_epsilon = 0.01` (abs) — both must clear |
| Post delay | `[thresholds].post_delay_seconds = 1.0` (proactive anti-429) |

## Hard rules & conventions
- Python 3.13, uv only (not pip/poetry). httpx for HTTP. **No comments in production code. No new deps without asking.**
- **Sealed-only scope** — singles are out of scope (they trip the Cloudflare 429).
- Curated store (has `collections`): products trusted (no filter), tagged with the config franchise. Full-crawl store (no `collections`, incl. rarecandy): `keep_sealed(filter_franchises(...))`. **Never full-crawl a big store / whole marketplace.**
- Keep the polite throttle in `http.py` (min_interval + Retry-After + backoff) for BOTH the fetch (`make_httpx_get`) and the Discord poster (`make_discord_poster`).
- The Actions bot commits `state/` + `data/` to `main` every few min → **always `git pull --rebase` before pushing.**
- Commit as `mrmadison14`; end commit messages with the `Co-Authored-By: Claude Opus 4.8` trailer. TDD (RED→GREEN); present diffs before pushing live changes.

## Gotchas
- **commit-state lives in `scripts/commit_state.sh` (called by `watch.yml`) — do NOT inline it back or revert to `git pull --rebase`.** fetch→reconcile→`git reset --mixed origin/main`→`git add state/`→commit→push retry loop. **Keep `--mixed` (never `--soft`):** soft keeps the runner's stale index, so a concurrent human push's non-`state/` files get committed as deletions (this clobbered the session-3 handoff docs). `tests/test_commit_state.py` guards it (RED on `--soft`).
- **Price-change floor (N1):** `detect_events(current, prev, epsilon, min_pct)` fires PRICE_CHANGE only if `abs(move) > epsilon` AND `abs(move)/old_price >= min_pct` (config `price_change_pct`, default 0.05). Root cause of skyboxct spam was repricing *drift* (monotonic), NOT ping-pong — so flap-suppression/last-price-memory would NOT have helped. Deals are **event-gated** (`runner.py` attaches verdicts only to detected events); safe because real deals ride on restocks/≥10% moves. To make #tracker quieter/louder, tune `price_change_pct`.
- **rarecandy is tag-garbage:** `__NEXT_DATA__` → `props.pageProps.__APOLLO_STATE__`; iterate `RareFind:` → its `Product` ref; **url = base/`{store.slug}/shop/{rareFind.slug}`** (bare `/{slug}` = empty-store 200 soft-404). `store` field is Apollo ref OR inline `{slug}` — resolve both, skip no-seller listings. **`is_sealed` = `sealed` tag AND NOT `singles` tag AND NOT title-accessory** (`_ACCESSORY_MARKERS`: playmat/binder/toploader/deck box/portfolio/…). Do NOT switch to a tag-based accessory/merch exclusion — rarecandy puts `accessories`+`merch` on real ETBs/Commander Decks in catch-all dumps (N2 root cause). `Sleeved Booster Pack` must stay sealed. `singles` exclusion is also load-bearing (re-admits CGC/PSA singles if removed). GraphQL introspection is 400 → HTML route only; ~85 browse-surface listings, catalog rotates each run.
- **Snapshots are carry-over, not replace** (`state.merge_snapshot`, both runner save paths): departed variants stay with a `last_seen` stamp (14-day TTL) so rotation re-entry doesn't re-fire NEW/PREORDER (killed rarecandy's ~2,000 dupes/day). Don't revert to `build_snapshot`.
- Discord `@here` needs `allowed_mentions:{parse:["everyone"]}`; poster retries 429 `Retry-After` + proactive `post_delay_seconds`.
- Box-vs-`case` fuzzy trap: `match.best_match` rejects size-qualifier mismatches via `_SIZE_TOKENS` — don't remove.
- tcgcsv 401s default-UA fetchers; the Chrome UA in `http.py` bypasses it. GitHub free-tier throttles frequent `schedule` crons (~2–3h) — that's why cron-job.org drives the 5-min cadence (paying GitHub does NOT help).
- Expanding a *seeded* store's collections → drop its `state/*.json` first for a silent re-seed (avoids a NEW-listing burst). Not needed for a brand-new store (seeds silently on first run).

## Decision tree — pick your next move
(A) **Phase 2 — Wix ×2 via the Fable model** (`pokelegendstcg` + `bulbacards`): the main remaining feature. **Start a fresh session (Fable) and point it at `docs/superpowers/PHASE2_HANDOFF.md`.** Two things it needs from the owner early: the **decision** — full-GraphQL (real coverage, ~2–2.5d, recommended) vs best-effort SSR (~1d, low value); and **sign-off on a `http.py` change** — add a POST/text-capable helper (current `make_httpx_get` is GET+JSON-only; rarecandy already added `as_text=True` — extend that + add `post_json`). One shared `adapters/wix.py`; make the gallery route config-driven (`bulbacards /shop` 404s; add optional `shop_path` to `Store`); verify Wix id-stability before enabling alerts.
(B) **Add more stores** (recurring — the user sends store-list images). Pipeline that's worked: probe domain for Shopify (`/products.json` 200) + currency + catalog size, dry-run through the REAL adapter+filters, then **full-crawl small/clean stores, curate big/singles-heavy ones** (find sealed-only `collections`; reject singles/accessory contamination). Scratchpad probe scripts are the template.
(C) **Widen rarecandy** beyond the ~85 browse-surface listings if `rareFindCatalog(page)` GraphQL can be made to work (introspection currently 400).
(D) **Monitor / ops.** Watch runs are longer at 26 stores (throttle × more variants) but under the new 20-min cap. Rotate the cron-job.org PAT before expiry (`docs/PAT_ROTATION.md`).
(E) **Tune the price-change floor** if #tracker is still too noisy/quiet: adjust `price_change_pct` in `config.toml` (currently 0.05). A ~2–5% band of mid-value moves still posts by design.
(F) Something else — describe.
=== END PROMPT ===
