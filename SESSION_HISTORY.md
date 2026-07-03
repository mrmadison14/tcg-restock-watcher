# TCG Restock Watcher — Session History

Chronological log of meaningful work, decisions, and state. Newest session on top.

---

## 2026-07-01 (session 4) — commit-state doc-clobber fix (off-tree regression) + Shopify-candidate triage, 🟢 LIVE

Resumed from the session-3 handoff. Verification-first per the handoff — and the opening `git pull --rebase` immediately surfaced a **live data-loss bug not in the decision tree**: bot commit `4f94e04` (child of the human handoff commit `83d58da`) had **deleted `docs/superpowers/PHASE2_SCOPING.md` + `docs/PAT_ROTATION.md` and reverted `SESSION_HISTORY.md`/`RESUME_PROMPT.md`**. Root-caused, fixed (TDD), restored the files, verified in prod.

**Root cause (systematic-debugging).** `watch.yml`'s commit-state retry loop did `git reset --soft origin/main` after fetching, which keeps the runner's **stale index**. `reconcile` only re-materializes `state/`, so any *non-`state/`* file a concurrent human push added to origin mid-run (the docs) was committed as a **deletion**; concurrently-edited non-state files were reverted to the runner's stale base. Only bites when origin advances via a non-`state/` push during a run — exactly what the session-3 handoff push did. As a bonus, `--soft` also defeated the `git diff --staged --quiet` convergence early-exit.

**Fix.** `git reset --soft` → **`git reset --mixed origin/main`**: re-bases the index onto the fetched tip so only `state/` diffs can ever be staged; non-state files are inherited from origin and preserved. Extracted the whole sequence into **`scripts/commit_state.sh`** (with a `RECONCILE_CMD` test seam) and pointed `watch.yml` at it. New integration test **`tests/test_commit_state.py`** replays a bot-run-races-human-push in a real git triad: RED on `--soft`, GREEN on `--mixed`, + a happy-path guard. TDD (+2 → **107 tests**). Commits `73f62b9` (fix) + `ad25dea` (restore).

**`build-index.yml` checked, left as-is** — its `commit → pull --rebase → push` replays only the `data/` diff onto the fetched tip, so it never clobbers non-`data/` files (theoretical daily-only conflict-failure risk, no data loss).

**Second finding (informational).** The last straggler on the OLD inline logic (run `28541683947`) failed *harmlessly*: its clobber commit also reverted `watch.yml`, and GitHub rejected the push — `refusing to allow a GitHub App to create or update workflow .github/workflows/watch.yml without workflows permission` (the job has only `contents: write`). That guard is why the docs survived that straggler. Fixed runs only ever touch `state/`, so they never need `workflows: write`.

**Prod verification.** 2 consecutive fixed runs succeeded (`28541865676`, `28541970794`); 2 subsequent bot `state:` commits then landed with all docs intact (the very act that broke things last session — pushing docs to `main` — is now clobber-safe).

**Store triage (against the user's store/promo list image).** Of 14 store domains in the image, 2 already tracked (rarecandy, collectorstore). Probed the rest via `/products.json`: **9 are Shopify = easy adds through the existing adapter, config-only** — `3kcollectables`, `doubleinfinitygaming`, `paladincards20`, `realgoodeal`, `shinypax`, `shopchieffpokeman`, `spoilsandloot`, `tygerstcgden`, `zulusgames`. Not-easy: `blowoutcards` (custom/non-Shopify HTML, and a big store — no full-crawl), `missionreadycollectibles` (`/products.json` → 401), `tcgsorted` (shop.app link — likely Shopify, real domain TBD). **8 added + seeded live** (`ok=18 failed=0`): 6 full-crawl + `realgoodeal` (590) / `zulusgames` (95) curated. **Follow-up (5 parallel read-only agents chasing the leftovers):** `tcgsorted` → real domain `shop.tcgsorted.com` (apex 404s; full-crawl, 21 sealed); `doubleinfinitygaming` → added via its sealed-only "new and hot" collections (pokemon/one piece/dragon ball) — the full catalog is graded-singles-heavy and uncurable, but those staging lists are clean (31); `realgoodeal` += `dragon ball:dragon-ball-super` (15) + `pokemon:pokemon-sealed-cases` (11) → 605; `zulusgames` += `pokemon:pokemon-scarlet-violet` + `pokemon:pokemon-imported-product` (Japanese displays) → 127 (no clean OP/DBZ collections exist there). realgoodeal/zulus state dropped to force a silent re-seed (verified: `ok=20 failed=0`, all 4 "seeded … no alerts", zero burst). **Ruled out:** `blowoutcards` (Magento behind an Imperva JS-challenge WAF → needs a headless browser, out of scope), `missionreadycollectibles` (Shopify storefront password-locked by the merchant). → **20 stores** total.

**rarecandy singles fix (`ce92967`).** rarecandy tags some graded slabs / named single cards with a catch-all tag dump that *includes* `sealed`, so `is_sealed = "sealed" in tags` let them pass `keep_sealed` into the watched set and alerts. Fixed to also require `"singles" not in tags` (`adapters/rarecandy.py`); TDD +2 → **109 tests**. Live watched dropped from ~53 (incl. CGC/PSA singles) to sealed-only; re-seeded clean and verified **0** `singles`/graded markers in the watched set. `detect_events` only iterates the current watched set, so the dropped singles fired nothing. (Adjacent, not fixed: a few `accessories`/`merch` items — e.g. playmats — tagged `sealed` without `singles` still pass; not "single cards" so left in scope pending a call.) Several of these also carry Smokemon/$5-off **promo codes** in the image, which the watcher does not model (orthogonal to restock/deal alerts).

**Current state (close of session 4):**
- 🟢 LIVE + autonomous + concurrency-safe, now also **clobber-safe for concurrent non-`state/` pushes**. **131 tests** green, tree clean. **25 stores**.

**Second store-list image → +5 stores (2026-07-03).** Probed 6 new domains (same Shopify/dry-run pipeline): added **full-crawl** `safarizone` (7), `tcgstadium` (27), `royalsakuratcg` (18), `763collectibles` (920, sealed-focused); **curated** `smokeandmirrorshobby` (1,123 via `pokemon` sealed + `pokemon-japanese-booster-boxes` + `shop-all-dragon-ball-super-tcg`; its `one-piece` collection rejected — 7 accessory card-cases; `one-piece-card-game-in-stock` is pure singles). **Skipped** `smokemon07` (live-rips/PSA-slab store, 0 watchable). Seeded live: `RUN: ok=25 failed=0 events_sent=0`, all 5 silent.

**rarecandy link fix (`ffdbd7f`).** User reported alert links opening an empty page. Root cause: URLs were `base/{slug}`, which Next.js matches to the `/[storeSlug]` route — rarecandy treats the product slug as a store name and renders an empty store page (200 soft-404; the session-3 "verified 200" check was fooled). The real route (from `/_next/static/{buildId}/_buildManifest.js`) is **`/[storeSlug]/shop/[rareFindSlug]`**. Adapter now resolves the seller from the RareFind's `store` field — a normalized Apollo ref on some SSR variants, an inline `{slug}` object on others — and skips listings with no resolvable seller (mirrors the unresolvable-product guard; only ever observed on already-skipped listings). Live-verified 4/4 URLs match the detail route. TDD +3 → **131 tests**.

**Duplicate-post fix — carry-over snapshots (`d0cb9cc`).** User reported repeat Discord posts. 24h state-history reconstruction (every run commits state → full forensic record): **2,405 events, 2,061 repeats — 2,048 of them rarecandy re-entries** (same item up to 27×/day, e.g. "Pitch Black Booster Box"). Root cause: rarecandy's `/shop`+`/discover` are rotating browse surfaces; `build_snapshot` kept only currently-visible variants, so every rotation off-and-back-on made `detect_events` see `old is None` → NEW_PRODUCT/PREORDER_OPEN re-posted. Fix: `state.merge_snapshot` — carry departed variants forward with `last_seen` (14-day TTL prune, tolerant of unparseable stamps), wired into both runner save paths (all stores); rarecandy state backfilled with the 24h union (251 variants) so the fix started warm. TDD +7 → **128 tests**. Live-verified: ~22 events/run → **1 then 0** across heavy watched-set churn (80→58). Minor residual noted, not fixed: skyboxct price ping-pong (~13 quiet posts/day).
- HEAD advances via bot `state:` commits; the session's fix commits are `73f62b9` / `ad25dea` (now under later bot commits).

**Next steps:** (a) ✅ Added 8/9 easy Shopify stores (`doubleinfinitygaming` skipped); optionally add One Piece/Dragon Ball collections where the full-crawl stores carry them + resolve `tcgsorted`/`missionreadycollectibles`. (b) Phase 2 Wix ×2 (still the harder non-Shopify work). (c) Widen rarecandy. (d) Rotate the cron-job.org PAT before expiry.

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
