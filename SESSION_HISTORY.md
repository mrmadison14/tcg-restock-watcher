# TCG Restock Watcher — Session History

Chronological log of meaningful work, decisions, and state. Newest session on top.

---

## 2026-07-09 (session 9) — diagnosed 4 "failures" (GitHub runner-acquisition, not us) + made the schedule cron an explicit backstop, 🟢 LIVE

Health-check on reported run failures. **Root cause: GitHub-side, not our code.** 4 `watch` runs failed 10:20–12:20Z, all with the annotation **"The job was not acquired by Runner of type hosted even after multiple attempts"** — GitHub couldn't provision a hosted runner; the job waited GitHub's fixed ~15-min acquisition window (every failure was exactly `15m1s`) then was marked `failure`. **The watcher code never executed** on those runs → no fetch, no state commit, no Discord posts, no data loss/corruption. All 4 were `workflow_dispatch` (cron-job.org). Intermittent (other runs in the window succeeded), self-healed by ~12:20Z; since then all green, ~3.7-min runs. This is the same self-healing logic as the 429 fix — a failed dispatch just means the next ~5-min dispatch is the retry.

**Dispatch-architecture finding.** Trigger breakdown of the last 200 runs: **194 `workflow_dispatch` (cron-job.org) vs 6 `schedule` (GitHub)** — the GitHub `schedule:` cron fires only ~every 2.7h (free-tier throttling, as long suspected), so it contributes ~3% of dispatches and is effectively a sparse backstop, not a co-driver. Considered removing it; **kept it** — near-zero cost, and it's the only fallback if cron-job.org dies (expired PAT / outage) → watcher would degrade to ~hourly instead of going dark. Removing it would not have prevented the runner-acquisition failures anyway.

**Change (CI only, no code):** set the `watch.yml` `schedule:` cron from every-5-min (`2,7,12,…`) to **hourly (`0 * * * *`)** with a comment documenting intent — it's a backstop; cron-job.org drives the real cadence. GitHub throttles it to ~2.7h either way, so behavior is unchanged, but it stops the occasional superseded/cancelled `schedule` run and makes the architecture explicit. README dispatch description + limitations updated. 165 tests still green (no Python touched). Commit `<pending>`.

**Close of session 9:** 🟢 LIVE, **28 stores, 165 tests**. No code defect found; the "failures" were transient GitHub runner capacity. Standing watch-list unchanged (rotate cron-job.org PAT before expiry; evening Cloudflare 429s on some stores now fail-fast and isolate cleanly).

---

## 2026-07-07 (session 8) — health review + fail-fast on 429 (Cloudflare runner-IP rate-limiting), 🟢 LIVE

Post-deploy health review of sessions 6–7 (Wix ×2 + rarecandy widening). **The feature work is healthy:** Wix stores quiet (10–13 / ~213 watched, 0 phantom events all day), rarecandy stable at ~237 watched, alert volume 0–2 events/run, and **13 straight hours of `ok=28 failed=0`** (04:06→17:00Z) after the session-7 push.

**Found a separate, pre-existing problem flaring up (NOT caused by our changes).** From ~17:30Z, a growing set of Shopify stores (5→7→8: allpoketcg, pkmncolosseum, doubleinfinitygaming, realgoodeal, zulusgames, deckoutgaming, spoilsandloot, paladincards20) started returning **429** to the GitHub runner — the original Cloudflare-rate-limits-shared-runner-IPs landmine, worse at evening peak. Confirmed it's environmental, not ours: all those stores return **200 from a local IP** right now, the code didn't change at 17:30Z, and the 13h clean streak preceded it.

**Impact was indirect but real:** each 429'd store burned up to ~90s of `Retry-After` retry sleeps, stretching runs from ~9 min to 14–20 min. Long runs collided with the 5-min dispatch cadence, so the concurrency guard cancelled most of them — hourly successes fell 10/hr → **3–4/hr** (median run duration 8.6m → 20.1m by 21:00Z). No data loss, no bad alerts (blocked stores just skip a cycle; the runner isolates per-store failures).

**Fix (decision A, TDD +2 → 165 tests): 429 is now fail-fast in the fetch path.** Removed `429` from `http.py::_RETRY_STATUS` (now `{500,502,503,504}`); a 429 raises immediately instead of sleeping through `Retry-After`. Rationale: the watcher **redispatches every ~5 min, so the next run *is* the retry** — a far longer, more polite backoff than any in-run retry, and it keeps run duration down so the cadence stops collapsing. The **Discord poster's** 429 handling is deliberately **untouched** (it's not redispatched — it must honor `Retry-After` in-run). Tests: flipped the three Retry-After/retry tests from 429→503 (5xx still retries + honors `Retry-After`), added `test_429_fails_fast_in_get` / `_in_post_json` (1 call, no sleep, raises). Docs: README Cloudflare section + limitations bullet updated. Commit `<pending>`.

**Close of session 8:** 🟢 LIVE, **28 stores, 165 tests**. Watched the fix restore run duration/cadence. Note: fail-fast means during a Cloudflare rate-limit window, affected stores update on whatever cadence gets a clean run rather than every 5 min — acceptable; the alternative (long in-run sleeps) starved *all* stores. If evening 429s persist/worsen, next levers: drop cron-job.org cadence to ~10 min (less IP pressure) or shard stores across runs.

---

## 2026-07-06 (session 7) — rarecandy widened ~85 → ~237 watched via the real Apollo GraphQL API, 🟢 LIVE

Same session, decision-tree **C** on the Opus model. Goal: widen rarecandy past the ~85 browse-surface listings the `/shop`+`/discover` `__NEXT_DATA__` scrape sees. The handoff flagged `rareFindCatalog(page)` GraphQL as the path "if it can be made to work (introspection 400)."

**Spike cracked the API (introspection stays closed; didn't need it).** The Apollo cache's `ROOT_QUERY` records the site's own query signatures — `rareFindCatalog({"page":1})` is real. The exact query **document** (field selections + `RareFindFilters` arg) lives in JS chunk `9311-*.js`: `query RareFindCatalog($page: Int!, $filters: RareFindFilters)`. The endpoint is **`api.rarecandy.com/graphql`** (from `_app` bundle; same-origin `/graphql` and `/api/graphql` are SPA/404). My first POST failed ("unknown error") only because it was **anonymous with a nullable `$page`** — sending `operationName: "RareFindCatalog"` + `$page: Int!` works bare (no auth/headers). Response carries `totalCount`/`pageSize` → clean server-side pagination.

**Filter model (probed live):** the filter field is **`categories`** (values `pokemon`/`onepiece`/`dbz`/`sealed`/`singles`/`accessories`/`mtg`/`lorcana`/`ws`/…); `sortBy:"newest"`. **Multi-category ORs, not ANDs** (`pokemon+sealed`=575 > `sealed`=453), so I can't get "pokemon AND sealed" server-side. Tightest scope = single `categories:["sealed"]` (**453 items, 23 pages @20/pg**); franchise filtering stays **client-side** in the runner (`filter_franchises` already does it — drops the MTG/Lorcana/GA sealed that share the marketplace). Confirmed clean pagination bounds: page 23 returns the 13-item tail, page 24 returns 0 (stop).

**Build (TDD, rewrite, +2 → 163 tests).** Replaced the HTML/`__NEXT_DATA__` scrape entirely (removed `extract_apollo`/`products_from_apollo`/`_SURFACES`). New `fetch_products` paginates `api.rarecandy.com/graphql` via the session-6 **`http_get.post_json`** (inherits the 2.5s throttle/Retry-After/Chrome-UA), `filters={categories:["sealed"], sortBy:"newest"}`, stopping on empty page / `len(seen) >= totalCount` / `_MAX_PAGES=40` cap, dedup by rareFind id. New `products_from_catalog` maps the inline GraphQL shape (no `__ref` resolution) → `Product`. **All the sealed-heuristic logic carried over unchanged**: `is_sealed = "sealed" in tags AND "singles" not in tags AND not title-accessory`; franchise-tag normalization (`onepiece`→`one piece`, `dbz`→`dragon ball`); URL `base/{store.slug}/shop/{rareFind.slug}`; `in_stock = quantity>0`. Tests rewritten against a trimmed real GraphQL capture (Pokémon-sealed, One Piece+singles→excluded, MTG-sealed→adapter-keeps-runner-drops, preorder+q=0).

**Live dry-run.** Real API through the throttled client: **453 sealed fetched → 237 watched after franchise filter** (pokemon 215, one piece 21, dragon ball 1), all in stock, 8 preorders, 0 duplicate ids, URLs/images verified. **~62s** for the 23-page fetch (adds ~55s to the run vs. the old 2 GETs; new run ~6 min, under the 20-min cap).

**Re-seed (seeded-store expansion).** rarecandy was already seeded (~79 variants); dropped `state/rarecandy.json` so the ~158 newly-visible variants seed **silently** rather than firing a NEW/PREORDER burst (the established drop-state pattern; even without it the `max_events_per_store=25` flood cap collapses to one quiet #tracker line). Commit `<pending>`.

**Close of session 7:** 🟢 LIVE, **28 stores, 163 tests** green. rarecandy coverage ~3× (79→237 watched). Remaining rarecandy headroom: the marketplace holds ~1497 total listings; we scope to sealed (~450) by design. Next ideas unchanged: more store-list images; rotate the cron-job.org PAT before expiry.

---

## 2026-07-06 (session 6) — Phase 2 ✅: Wix ×2 (pokelegendstcg + bulbacards) via full-catalog storefront GraphQL, 🟢 LIVE

Resumed via `/resume-session` on the **Fable model** (verification green: 139 tests, 26 stores, runs healthy) and executed decision-tree **A** — the `docs/superpowers/PHASE2_HANDOFF.md` brief. Owner sign-offs obtained up front: **(A) full-catalog GraphQL** over best-effort SSR, the **`http.py` POST helper**, and push-enabled (silent-seed flow, matching every prior store add).

**Probes flipped two scoping assumptions.** (1) **No gallery route needed at all** — the all-products category (`00000000-000000-000000-000000000001`) via storefront GraphQL serves the full catalog, so bulbacards' `/shop` 404 is moot and the planned `shop_path` config field was dropped unbuilt. (2) **pokelegends' catalog is genuinely 13 products** (`numOfProducts=344` is a stale counter; `onlyVisible=false` also returns 13) — all sealed Pokémon; bulbacards = 349 real products. Token mint (`/_api/v1/access-tokens` → `apps[<wix-stores appDefId>].instance`) + `POST /_api/wix-ecommerce-storefront-web/api?o=getFilteredProducts&s=WixStoresWebClient` work unauthenticated with the project Chrome UA on both sites; ids identical across fetches ~1h apart on fresh tokens.

**Franchise gap → config-declared blanket tag.** Both stores are 100% Pokémon (0 OP/DBZ titles in 362 products) but titles rarely name the franchise — title-tier matching keeps only 43/225 sealed items (~80% miss, e.g. 'Mega Greninja ex Premium Collection'). New optional **`Store.franchise`** field; the adapter tags every product with it so `filter_franchises` matches on tier-1 tags (mirrors rarecandy's tag normalization). Runner and `filtering.py` untouched. Use only for single-franchise stores.

**No accessory guard (N2 re-checked against this catalog):** all 8 accessory-flagged sealed-pass names on bulbacards (Binder Collections ×4, Sleeved Boosters ×3, Premium Playmat Collection) are **official sealed product lines** a guard would false-drop; zero graded/singles noise passes the markers. Added a `"trainer box"` marker to catch the store-typo'd 'Pitch Black EliteTrainer Box'.

**Build (TDD, +22 → 161 tests, commit `54408028`).** `http.py`: retry/throttle loop factored into a shared `request()`; the returned `get` now carries **`get.post_json(url, body, params, headers)`** on the same client/throttle/Retry-After/UA machinery (+5) — runner and existing adapters untouched. `config.py`: `franchise` field (+2). **`adapters/wix.py`**: token mint → paginated `getFilteredProducts` (100/page, `_MAX_PAGES` 20) → `Product` (Wix id → both ids; `/product-page/{urlPart}` url; `static.wixstatic.com/media/` image; ribbon+name preorder markers; title sealed markers; blanket franchise tag); GraphQL errors raise (+15 incl. pagination, page-cap, empty-page, error-raise, stable-ids, and a runner-filter integration case). Registered `"wix"` in `runner._ADAPTERS`. Fixtures = trimmed real bulbacards captures.

**Live verification.** Dry-run through the real adapter+filters: pokelegends 13→13 watched, bulbacards 349→**213 watched** (33 in stock), 0 duplicate ids, URLs/images verified. Prod: run `28834896655` seeded both silently (`[pokelegendstcg] seeded 13` / `[bulbacards] seeded 213`, `ok=28 failed=0`); run+1 re-seeded silently (raced the seed's state push — harmless); one hour on, steady state **`13 watched, 0 events` / `213 watched, 0 events`** — no phantom-id events. → **28 stores.**

**Close of session 6:** 🟢 LIVE, **28 stores, 161 tests** green, **Phase 2 complete** — every non-Shopify store named in the design spec has shipped. Remaining ideas: widen rarecandy past its ~85 browse-surface listings if `rareFindCatalog` GraphQL opens up; more store-list images as they arrive; rotate the cron-job.org PAT before expiry (`docs/PAT_ROTATION.md`).

---

## 2026-07-06 (session 5) — +1 store (pkmncolosseum) from a third store-list image, 🟢 LIVE

Resumed via `/resume-session` (verification green: 131 tests, `watch`/`build-index` runs success, tree clean after `git pull --rebase`). Noted `watch` run durations creeping up (6m44s→8m12s vs the `timeout-minutes: 10` cap) — flagged, not yet acted on.

Chose decision-tree **B (add stores)** against **two new store-list images** (Smokemon07 YouTube descriptions, 07-03 + 07-06). Cross-referenced every domain in both against the tracked 25: all were already tracked or previously ruled out (`missionreadycollectibles` = password-lock, `smokemon07` = live-rips) **except one new domain — `pkmncolosseum.com`**.

**Probe → dry-run → curate (the standard pipeline).** `pkmncolosseum.com` = Shopify (`dead-draw-gaming.myshopify.com`), **USD**, Dead Draw Gaming's **Pokémon-only** store. Page 1 of `/products.json` is all singles (`Best Selling`=10,304, `All Sets`=5,984) → a **curate** store, not full-crawl. Found clean sealed collections (`products_count`: `all-pokemon-sealed` 268, `sealed-booster-packs`/"Sealed Product" 441, `booster-boxes` 49, `elite-trainer-boxes` 40, `collection-boxes` 110, `booster-packs` 106). **Note:** the collection `/products.json` endpoint returns only currently-*available* items, so the live watched set is far smaller than `products_count` — most of the catalog is presently sold out. Dry-run through the **real** `shopify.fetch_products` (which dedups overlapping collections by `variant_id`, adapter L96–105): **9 deduped watched variants, 0 singles contamination, all Pokémon, all in stock** (real UPCs/ETBs/bundles/booster boxes/battle decks). 9 is just current availability; the broad collection set future-proofs coverage as types restock. The "dragon" collections are Pokémon sets (Dragon Majesty, Dragons Exalted), not Dragon Ball TCG; no One Piece.

**Store add (`pkmncolosseum`).** `config.toml` (+curated block, 6 collections) + `README.md` (25→26). **→ 26 stores.** Committed + pushed as `mrmadison14`; **live-verified** on run `28828161655`: `[pkmncolosseum] seeded 9 watched variants (no alerts)`, `RUN: ok=26 failed=0 seeded=['pkmncolosseum']`, state committed — silent seed, no burst.

**Watch timeout 10→20 min (`16b3bc0c`).** Run durations had crept to ~7–8 min at 26 stores (2.5s throttle × more variants) vs the 10-min cap. Doubled the headroom; concurrency cancels overlaps so longer jobs won't stack.

**N1 — price-change drift noise (`b2eda04a`, TDD +5).** skyboxct fired ~13 `#tracker` price-change posts/day. **Forensic git-history replay** (every state commit = a snapshot) proved it was **not ping-pong** (values never revisit) but **algorithmic repricing drift** on high-value boxes — $1–2 nudges (`$374→$373`, `$1424→$1428`) each clearing the absolute `$0.01` epsilon. Fix: `detect_events` now also requires a **relative** move ≥ `price_change_pct` (new `[thresholds]` key, default **0.05 = 5%**); absolute epsilon kept as a floor; div-by-zero guarded for free items. Deals are **event-gated** (`runner.py` attaches verdicts only to detected events) but genuine ≥10%-below-market deals ride on restocks/new-listings or large drops, all ≥5%, so none are hidden. Real-history replay (skyboxct, 5.4d): **price-change 69→33 (~13→~6/day, −52%); restock/preorder/new_product unchanged.**

**N2 — rarecandy accessory guard (`fd84f2aa`, TDD +3).** Guard against playmats/binders/toploaders leaking into the sealed feed. **Root-cause investigation flipped the obvious fix:** a tag-based `accessories`/`merch` exclusion is **unsafe** — rarecandy applies garbage catch-all tag dumps, so a real ETB (16 tags incl. `accessories`+`merch`+`sealed`) and a Commander Deck would be wrongly dropped. Also: no accessory currently leaks (genuine accessories carry **empty tags** → no `sealed` → already filtered). Chose a **title-based** guard (owner-approved): `is_sealed` also requires the title not to name an accessory (`playmat`/`binder`/`toploader`/`deck box`/`portfolio`/…). **`Sleeved Booster Pack` deliberately NOT matched** (it's sealed). Tests lock in sleeved-booster-stays-sealed + catch-all-ETB-stays-sealed. Closes the gap if rarecandy ever tags a playmat `sealed`.

**Close of session 5:** 🟢 LIVE, **26 stores, 139 tests** green, tree clean, all pushed as `mrmadison14`. **Next: Phase 2 (Wix ×2) handed to the Fable model** — see `docs/superpowers/PHASE2_SCOPING.md` (decision still open: full-GraphQL vs best-effort SSR; needs a POST/text `http` helper). Adjacent unfixed: a couple mid-value price moves in the 2–5% band still post (by design of the 5% floor — tune `price_change_pct` if desired).

---

## 2026-07-01 → 07-06 (session 4) — clobber fix + WS1 hardening merge + 15 stores added + rarecandy dedup & link fixes, 🟢 LIVE

Resumed from the session-3 handoff. Verification-first per the handoff — and the opening `git pull --rebase` immediately surfaced a **live data-loss bug not in the decision tree**: bot commit `4f94e04` (child of the human handoff commit `83d58da`) had **deleted `docs/superpowers/PHASE2_SCOPING.md` + `docs/PAT_ROTATION.md` and reverted `SESSION_HISTORY.md`/`RESUME_PROMPT.md`**. Root-caused, fixed (TDD), restored the files, verified in prod.

**Root cause (systematic-debugging).** `watch.yml`'s commit-state retry loop did `git reset --soft origin/main` after fetching, which keeps the runner's **stale index**. `reconcile` only re-materializes `state/`, so any *non-`state/`* file a concurrent human push added to origin mid-run (the docs) was committed as a **deletion**; concurrently-edited non-state files were reverted to the runner's stale base. Only bites when origin advances via a non-`state/` push during a run — exactly what the session-3 handoff push did. As a bonus, `--soft` also defeated the `git diff --staged --quiet` convergence early-exit.

**Fix.** `git reset --soft` → **`git reset --mixed origin/main`**: re-bases the index onto the fetched tip so only `state/` diffs can ever be staged; non-state files are inherited from origin and preserved. Extracted the whole sequence into **`scripts/commit_state.sh`** (with a `RECONCILE_CMD` test seam) and pointed `watch.yml` at it. New integration test **`tests/test_commit_state.py`** replays a bot-run-races-human-push in a real git triad: RED on `--soft`, GREEN on `--mixed`, + a happy-path guard. TDD (+2 → **107 tests**). Commits `73f62b9` (fix) + `ad25dea` (restore).

**`build-index.yml` checked, left as-is** — its `commit → pull --rebase → push` replays only the `data/` diff onto the fetched tip, so it never clobbers non-`data/` files (theoretical daily-only conflict-failure risk, no data loss).

**Second finding (informational).** The last straggler on the OLD inline logic (run `28541683947`) failed *harmlessly*: its clobber commit also reverted `watch.yml`, and GitHub rejected the push — `refusing to allow a GitHub App to create or update workflow .github/workflows/watch.yml without workflows permission` (the job has only `contents: write`). That guard is why the docs survived that straggler. Fixed runs only ever touch `state/`, so they never need `workflows: write`.

**Prod verification.** 2 consecutive fixed runs succeeded (`28541865676`, `28541970794`); 2 subsequent bot `state:` commits then landed with all docs intact (the very act that broke things last session — pushing docs to `main` — is now clobber-safe).

**Store triage (against the user's store/promo list image).** Of 14 store domains in the image, 2 already tracked (rarecandy, collectorstore). Probed the rest via `/products.json`: **9 are Shopify = easy adds through the existing adapter, config-only** — `3kcollectables`, `doubleinfinitygaming`, `paladincards20`, `realgoodeal`, `shinypax`, `shopchieffpokeman`, `spoilsandloot`, `tygerstcgden`, `zulusgames`. Not-easy: `blowoutcards` (custom/non-Shopify HTML, and a big store — no full-crawl), `missionreadycollectibles` (`/products.json` → 401), `tcgsorted` (shop.app link — likely Shopify, real domain TBD). **8 added + seeded live** (`ok=18 failed=0`): 6 full-crawl + `realgoodeal` (590) / `zulusgames` (95) curated. **Follow-up (5 parallel read-only agents chasing the leftovers):** `tcgsorted` → real domain `shop.tcgsorted.com` (apex 404s; full-crawl, 21 sealed); `doubleinfinitygaming` → added via its sealed-only "new and hot" collections (pokemon/one piece/dragon ball) — the full catalog is graded-singles-heavy and uncurable, but those staging lists are clean (31); `realgoodeal` += `dragon ball:dragon-ball-super` (15) + `pokemon:pokemon-sealed-cases` (11) → 605; `zulusgames` += `pokemon:pokemon-scarlet-violet` + `pokemon:pokemon-imported-product` (Japanese displays) → 127 (no clean OP/DBZ collections exist there). realgoodeal/zulus state dropped to force a silent re-seed (verified: `ok=20 failed=0`, all 4 "seeded … no alerts", zero burst). **Ruled out:** `blowoutcards` (Magento behind an Imperva JS-challenge WAF → needs a headless browser, out of scope), `missionreadycollectibles` (Shopify storefront password-locked by the merchant). → **20 stores** total.

**rarecandy singles fix (`ce92967`).** rarecandy tags some graded slabs / named single cards with a catch-all tag dump that *includes* `sealed`, so `is_sealed = "sealed" in tags` let them pass `keep_sealed` into the watched set and alerts. Fixed to also require `"singles" not in tags` (`adapters/rarecandy.py`); TDD +2 → **109 tests**. Live watched dropped from ~53 (incl. CGC/PSA singles) to sealed-only; re-seeded clean and verified **0** `singles`/graded markers in the watched set. `detect_events` only iterates the current watched set, so the dropped singles fired nothing. (Adjacent, not fixed: a few `accessories`/`merch` items — e.g. playmats — tagged `sealed` without `singles` still pass; not "single cards" so left in scope pending a call.) Several of these also carry Smokemon/$5-off **promo codes** in the image, which the watcher does not model (orthogonal to restock/deal alerts).

**Second store-list image → +5 stores (2026-07-03).** Probed 6 new domains (same Shopify/dry-run pipeline): added **full-crawl** `safarizone` (7), `tcgstadium` (27), `royalsakuratcg` (18), `763collectibles` (920, sealed-focused); **curated** `smokeandmirrorshobby` (1,123 via `pokemon` sealed + `pokemon-japanese-booster-boxes` + `shop-all-dragon-ball-super-tcg`; its `one-piece` collection rejected — 7 accessory card-cases; `one-piece-card-game-in-stock` is pure singles). **Skipped** `smokemon07` (live-rips/PSA-slab store, 0 watchable). Seeded live: `RUN: ok=25 failed=0 events_sent=0`, all 5 silent.

**rarecandy link fix (`ffdbd7f`).** User reported alert links opening an empty page. Root cause: URLs were `base/{slug}`, which Next.js matches to the `/[storeSlug]` route — rarecandy treats the product slug as a store name and renders an empty store page (200 soft-404; the session-3 "verified 200" check was fooled). The real route (from `/_next/static/{buildId}/_buildManifest.js`) is **`/[storeSlug]/shop/[rareFindSlug]`**. Adapter now resolves the seller from the RareFind's `store` field — a normalized Apollo ref on some SSR variants, an inline `{slug}` object on others — and skips listings with no resolvable seller (mirrors the unresolvable-product guard; only ever observed on already-skipped listings). Live-verified 4/4 URLs match the detail route. TDD +3 → **131 tests**.

**Duplicate-post fix — carry-over snapshots (`d0cb9cc`).** User reported repeat Discord posts. 24h state-history reconstruction (every run commits state → full forensic record): **2,405 events, 2,061 repeats — 2,048 of them rarecandy re-entries** (same item up to 27×/day, e.g. "Pitch Black Booster Box"). Root cause: rarecandy's `/shop`+`/discover` are rotating browse surfaces; `build_snapshot` kept only currently-visible variants, so every rotation off-and-back-on made `detect_events` see `old is None` → NEW_PRODUCT/PREORDER_OPEN re-posted. Fix: `state.merge_snapshot` — carry departed variants forward with `last_seen` (14-day TTL prune, tolerant of unparseable stamps), wired into both runner save paths (all stores); rarecandy state backfilled with the 24h union (251 variants) so the fix started warm. TDD +7 → **128 tests**. Live-verified: ~22 events/run → **1 then 0** across heavy watched-set churn (80→58). Minor residual noted, not fixed: skyboxct price ping-pong (~13 quiet posts/day).
**Current state (2026-07-06):** 🟢 LIVE + autonomous + concurrency-safe + clobber-safe. **25 stores, 131 tests** green, working tree clean. Every duplicate-post and broken-link report resolved and prod-verified. HEAD advances via bot `state:` commits (last human commit `861fc32`, docs: sync to 25 stores).

**Next steps:** (a) **Phase 2 — Wix ×2** (`pokelegendstcg` + `bulbacards`) — the main remaining feature work; needs a POST/token-capable `http` helper (see `docs/superpowers/PHASE2_SCOPING.md`). (b) Add more stores when the next store-list image arrives (probe → dry-run → full-crawl-or-curate pipeline; scratchpad probe scripts are the template). (c) Widen rarecandy past the ~85 browse-surface listings. (d) Monitor run duration (25 stores → longer runs; bump `timeout-minutes` in `watch.yml` if runs approach the 10-min cap) + rotate the cron-job.org PAT before expiry. Adjacent unfixed: skyboxct price ping-pong (~13 quiet posts/day) + a few rarecandy `accessories`/`merch` items (playmats) that pass the sealed filter.

---

## 2026-07-01 (session 3) — CI concurrency fix (found off-tree) + PAT rotation + Discord inter-post delay + rarecandy adapter (Phase 2 begun), 🟢 LIVE

Resumed from HEAD `755744d`; ended at HEAD **`bc42af3`** (`main`; bot appends `state:`/`data:` commits). Verification-first: found a **live, ongoing failure not in the handoff's decision tree** — `watch` was failing ~38% of runs — fixed it, then did A, B, and began C. All TDD'd + reviewed + prod-verified.

**Off-tree find — commit-state concurrency bug (top priority).** `git status`/`gh run list` showed 38% of recent watch runs failing. Root cause (systematic-debugging + a real-git simulation): overlapping runs (cron-job.org 5-min + GitHub's own schedule + occasional >5-min runs) each rewrite `last_run` in every `state/*.json`, so the old `git pull --rebase origin main` conflicted on all 9 files → run failed, its state was dropped, next run re-alerted (a hidden flood source). Fix: commit step is now a **fetch → reconcile → `reset --soft origin/main` → commit → push retry loop** (`watch.yml`) + job `timeout-minutes: 10`. New `tcg_watcher.reconcile` keeps the **newest `last_run` per file** and **materializes origin-only files** (guards a real data-loss hole — `git add state/` stages deletions on git 2.x, silently dropping a store another run just seeded). TDD (+10) + two real-git end-to-end sims (stale-file + origin-only). Commit `2c8be31`. **60-min prod monitor: 0 failures / 17 runs (was 38%); 3 execution overlaps all handled.**

**A — cron-job.org PAT rotated.** Exposed/expiring fine-grained PAT replaced (Actions r+w, this repo only), swapped into cron-job.org `Authorization` (tested 204), old token **revoked**; verified by a post-revoke scheduled dispatch landing (`28536694410`). Runbook `docs/PAT_ROTATION.md`.

**B — proactive Discord inter-post delay.** `send_events` sleeps `post_delay_seconds` (config `[thresholds]`, default 1.0s, injected sleep) between posts so bursts don't hit the webhook 429 in the first place (on top of the existing Retry-After retry). TDD (+5). Commit `953ce06`.

**C — Phase 2 scoping + rarecandy adapter (first non-Shopify).** A research subagent probed the 3 non-Shopify sites → `docs/superpowers/PHASE2_SCOPING.md` (rarecandy easy; both Wix hard — full catalog needs token + GraphQL POST; ~1 week, 2 adapters not 3). Built **rarecandy** (Next.js marketplace): parses `__NEXT_DATA__` Apollo cache from `/shop`+`/discover` (GraphQL introspection is 400/closed), per `RareFind` → `Product` (real stock count, explicit `isPreorder`, franchise+sealed tags with `onepiece`→`one piece` / `dbz`→`dragon ball` normalization so `filter_franchises` matches; url `/{rareFind.slug}`, verified 200). `http.get` gained an `as_text` option for HTML. TDD vs a real trimmed fixture (+9). Commit `bc42af3`. **Prod-verified: `[rarecandy] seeded 51 watched variants (no alerts)`.**

**Current state (close of session 3):**
- 🟢 LIVE + autonomous + concurrency-safe. HEAD **`bc42af3`** on `main` (advances via bot commits). **105 tests** green.
- Watch pipeline now 0% failures. PAT rotated. Discord inter-post delay live. **10 stores** (rarecandy = first non-Shopify).

**Next steps:** (a) **Phase 2 Wix ×2** (`pokelegendstcg` + `bulbacards`) — remaining non-Shopify work; needs a POST/token-capable `http` path for full catalog (see `PHASE2_SCOPING.md`; decide full-GraphQL vs best-effort SSR; make gallery route config-driven — bulbacards `/shop` 404s; verify id-stability). (b) Optionally widen rarecandy past ~85 browse-surface listings if `rareFindCatalog(page)` GraphQL opens up. (c) Rotate the new PAT before its expiry.

---

## 2026-07-01 (session 2) — 401games coverage + Task-15 polish + Phase 3 deal-flagging (shipped) + made autonomous, 🟢 LIVE

Resumed from HEAD `182e42a`; ended at HEAD **`755744d`** (`main`; the Actions bot appends `state:`/`data:` commits, so HEAD keeps advancing). Verified session-1 state, then executed decision-tree items A + D + B, made the watcher run autonomously at 5-min cadence, and fixed a live crash surfaced during this handoff.

**Stage A — 401games full sealed coverage.** 401games was DBZ-only (195 variants). It organizes Pokémon/OP by *set* (mixes singles) but also exposes product-type sealed collections. Added Pokémon (booster-boxes / ETBs / packs / box-sets-tins / japanese-sealed-product) + One Piece (booster-boxes / packs / box-sets) to `config.toml`; dropped its stale seed state to force a silent re-seed. Verified via a live run: `[401games] seeded 1131 watched variants (no alerts)`, ok=9, 0×429. Commit `e64af93`.

**Stage D — Task-15 polish.** `adapters/shopify.py`: dropped over-matching bare `"bundle"` marker (kept `"booster bundle"`); made product/variant ids crash-on-missing (`it["id"]`/`v["id"]`). TDD, +3 tests. Commit `2c33154`.

**Stage B — Phase 3 deal-flagging (the big one).** Spike-verified tcgcsv (sealed products DO carry `marketPrice`; a realistic Chrome UA bypasses its Cloudflare 401). Brainstorm → spec (`docs/superpowers/specs/2026-07-01-phase3-deal-flagging-design.md`) → plan (`docs/superpowers/plans/2026-07-01-phase3-deal-flagging.md`) → subagent-driven TDD build (10 tasks, fresh implementer + reviewers). New `pricing/{tcgcsv,match,build_index,oracle}.py`, `Verdict` model, `[pricing]` config, deal-aware `notify` routing, daily `build-index.yml`. Final review found a **Critical**: a single "Booster Box" fuzzy-matched a "Booster Box Case" (0.91) → bogus 91%-under loud deal — fixed with a size-qualifier guard in `match.best_match` (`_SIZE_TOKENS`) + dropped bare `"case"` marker (commit `848ba9d`). Merged via PR #1 (`745083a`). Real index built on Actions + verified: **pokemon 2595 / one piece 255 / dragon ball 588** sealed entries + CAD FX 1.42.

**Stage — autonomous + Discord proof.** GitHub's own `watch` schedule self-started but sparse (~2–3h — free-tier throttles frequent crons; moved cron off top-of-hour anyway). Verified the Discord path end-to-end (forced a preorder event → loud `#deals` @here; self-healed). Stood up a **cron-job.org** cloud cron POSTing `workflow_dispatch` every 5 min (verified 204 + a real dispatch firing) — 5-min cadence with no local Mac. (Decided against paying GitHub — schedule throttle is plan-independent. A launchd pinger was prepared but NOT loaded, superseded by cron-job.org.)

**Stage — live Discord-429 crash fixed (surfaced during handoff).** The 5-min cadence + a backlog of real events exposed a gap: `make_discord_poster` had no 429 handling → a rate-limited webhook crashed the whole run, and since state saves *after* posting, the same events re-fired every run = crash loop (and it was emailing failure notices). Fixed: the poster now retries on 429 honoring `Retry-After` (mirrors `make_httpx_get`), fail-loud only after exhausting retries. TDD, +2 tests. Commit `cea9b29`. Verified: the next run posted the **19-event backlog** and saved state — `RUN: ok=9 failed=0 events_sent=19`.

**Current state (close of session 2):**
- 🟢 LIVE + autonomous. HEAD **`755744d`** on `main` (advances via bot commits). **81 tests** green, tree clean.
- Phase 3 deal-flagging merged + price index built (2595/255/588 + FX). Market verdict on every event; ≥10%-under → loud `#deals`.
- Runs every 5 min via cron-job.org (verified) + GitHub's sparse own schedule as backstop. 401games full sealed (1131). Discord proven; 19-event backlog cleared.

**Next steps:** (a) **Rotate the cron-job.org PAT** — pasted in chat (exposed) + expires 2026-07-31 → new fine-grained PAT (Actions r+w, this repo), update the cron-job.org `Authorization` header, re-test 204, revoke old. (b) If Discord 429s recur under load, add a small inter-post delay in `send_events` (proactive, on top of the retry). (c) Phase 2 (non-Shopify: Wix ×2 + rarecandy) still deferred.

---

## 2026-07-01 (session 1) — Brainstorm → ship (sealed-only watcher, LIVE), 🟢 LIVE

Started from a bare idea; ended with a **live, verified** watcher on GitHub Actions. Built via the
superpowers workflow: brainstorming → spec → writing-plans → subagent-driven-development (fresh
implementer + spec/quality reviewers per task). Ended at HEAD **`182e42a`** on `main` (pushed; the
Actions bot also appends `state: update snapshots` commits every ~5 min, so HEAD keeps advancing).

**Stage 1 — Brainstorm + spec.** Probed the user's sites: most are Shopify (public `/products.json`).
Decided: franchises = Pokémon/One Piece/Dragon Ball; Discord alerts (loud/quiet); GitHub Actions
(later account-corrected to personal GitHub `mrmadison14`, not GitLab); snapshot-diff engine.
Spec: `docs/superpowers/specs/2026-06-30-tcg-restock-watcher-design.md`.

**Stage 2 — Plan.** 13-task TDD plan: `docs/superpowers/plans/2026-06-30-tcg-restock-watcher-phase1.md`.

**Stage 3 — Build (Tasks 1,3–11).** Python 3.13 + uv + httpx. Modules under `src/tcg_watcher/`:
models, config (tomllib), adapters/shopify, filtering, state, diff, notify, http, runner, __main__.
Each task: TDD, spec review, code review. Fixes landed via review: per-tag franchise matching
(no cross-boundary false match); in-stock-only price changes; preorder-restock test; @here
`allowed_mentions:{parse:["everyone"]}` (verified — Discord has no "here" parse type).

**Stage 4 — Spike (Landmine #1, the pivot).** Created the repo, ran the feed spike on a real runner.
Single-request spike passed, but the **full-catalog crawl got Cloudflare 429'd** from GitHub's
datacenter IP. Also caught: 401games' real storefront is `store.401games.ca` (apex redirects);
transient 503s (→ added HTTP retry + polite throttle).

**Stage 5 — Sealed-only re-architecture (user-approved).** Recon showed the stores are tens of
thousands of *singles* (429 cause) and the user only wants **sealed** (restocks/preorders). Rebuilt
the fetch layer: curated **sealed collections** per big store (config `collections=["fr:handle"]`,
trusted) + full-crawl + `keep_sealed` for 3 small stores. Cuts a run to ~40 requests.

**Stage 6 — Live verify + collectorstore.** GitHub run: **9/9 stores seed, 0 failures, 0 × 429**,
seed-first silent, steady-state 0 spurious events, state committed. User flagged collectorstore has
sealed under `games-pokemon`/`games-one-piece` → re-added (my keyword filter had missed the "games-"
naming). Docs (README + spec §16) + memory updated to as-built. Final holistic review: **SHIP**.

**Current state (close of session 1):**
- 🟢 LIVE. `main` clean + synced. HEAD `182e42a` (bot state commits ongoing). 47 tests green.
- `watch.yml` 5-min cron active; last runs success. Discord webhooks set + tested (204).
- 9 stores seeded. Real sealed restock/preorder/price-change alerts now flow to Discord.

**Next steps:** (a) confirm real-world alerts fire + add 401games Pokémon/OP sealed handles;
(b) Phase 3 — TCGplayer below-market deal-flagging via tcgcsv.com; (c) Phase 2 — the 3 non-Shopify
sites (Wix ×2 + rarecandy); (d) minor adapter polish (Task 15: drop bare "bundle" marker,
crash-on-missing-id — full-crawl only).

---
