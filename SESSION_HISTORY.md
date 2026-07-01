# TCG Restock Watcher — Session History

Chronological log of meaningful work, decisions, and state. Newest session on top.

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
