# TCG Restock Watcher — Design Spec

**Status:** Approved (design) — ready for implementation planning
**Date:** 2026-06-30
**Owner:** James Madison
**Type:** Personal project (NOT bound by Agent Smith production standards)

---

## 1. Problem & Goal

James buys sealed Pokémon, One Piece, and Dragon Ball trading-card products from a set of
online hobby shops. The hottest items sell out fast and preorders open without warning. He
wants to be notified the moment a watched product **restocks, newly appears, opens for
preorder, or changes price** — fast enough to buy before it sells out — and he wants to know
whether a listed price is a **good deal relative to TCGplayer market price**.

**Success looks like:** a Discord ping with a tappable buy-link within ~5 minutes of a relevant
change, with deals (priced below market) called out loudly and overpriced items flagged.

**Non-goals:** auto-checkout/buying, a web dashboard, multi-user, "low stock / N-left"
tracking, real-time (sub-minute) drop sniping.

---

## 2. Users & Context

Single user (James). Runs unattended 24/7. Personal-scale; reliability and low maintenance
matter more than throughput. No PII, no auth, no accounts.

---

## 3. Scope

### In scope (Phase 1 — the working MVP)
- 10 Shopify stores via public `/products.json`.
- Franchise filter: Pokémon, One Piece, Dragon Ball (configurable watchlist).
- Four event types: **restock**, **new product**, **preorder opens**, **price change**.
- Discord notifications with product image, price, franchise, and buy-link.
- Snapshot-diff engine; state committed to a public GitHub repo.
- GitHub Actions scheduler (~5-min cron); seed-first run (no false-alarm storm).

### In scope (later phases)
- **Phase 2:** Tier-2 sites — Wix ×2 + Next.js ×1 — best-effort adapters, isolated.
- **Phase 3:** TCGplayer market-price oracle (via tcgcsv.com) → deal-flagging (loud/quiet
  split, USD-normalized, sealed-products-first).

### Out of scope (for now)
Web UI/dashboard, quantity ("3 left"), auto-purchase, accounts, non-Shopify big-box retailers
(Target/Walmart/etc.), singles deal-matching, mobile app.

---

## 4. Architecture

### 4.1 Core idea
Every store is reduced to one normalized shape by a per-store **adapter**. A generic
**diff engine** compares this run's normalized list to the previous **snapshot** and emits
classified **events**. Everything downstream of the adapter is shared and store-agnostic.

```
[adapters] -> [franchise filter] -> [diff vs snapshot] -> [classify events]
   -> [price verdict (Phase 3)] -> [notifier: Discord] -> [write+commit snapshot]
```

### 4.2 Components
| Component | Responsibility | Notes |
|---|---|---|
| `adapters/` | One module per store platform → returns normalized products | Tier 1: Shopify (shared). Tier 2: Wix, Next.js (per-site). |
| `filter` | Keep only products matching the franchise watchlist | Matches on tags + product_type first, title second. |
| `diff` | Compare current vs previous snapshot, classify changes | Pure function; the heart of the system. |
| `price_oracle` (P3) | Look up TCGplayer market price for a product | Source: tcgcsv.com static JSON. Sealed-first. |
| `notifier` | Format + send Discord embeds (loud vs quiet) | Two webhooks: deals (loud) + tracker (quiet). |
| `state` | Load/save per-store snapshots; commit to repo | JSON files in `state/`. |
| `runner` | Orchestrate one run across all stores; isolate failures | A broken adapter logs + skips, never crashes the run. |

### 4.3 Tech stack
Python 3.13, `uv` for deps. `httpx` for fetching. No DB, no web framework, no frontend.
Standard-library-first; minimal dependencies (add nothing without James's approval).

---

## 5. Data Model

### Normalized product (adapter output)
```
{
  "store": "hobbiesville",
  "product_id": "shopify-gid-or-handle",
  "variant_id": "…",
  "title": "Prismatic Evolutions Elite Trainer Box",
  "franchise": "pokemon",            # resolved by filter
  "price": 59.99,
  "currency": "USD",                 # per-store, see roster
  "in_stock": true,                  # Shopify variant.available
  "url": "https://…/products/…",
  "image": "https://…",
  "is_preorder": false,              # heuristic (tag/title)
  "is_sealed": true                  # heuristic, used by price oracle
}
```

### Event (diff output)
```
{
  "type": "restock" | "new_product" | "preorder_open" | "price_change",
  "product": { …normalized… },
  "previous": { "price": 64.99, "in_stock": false } | null,
  "verdict": { "market_price": 58.40, "delta_pct": -14.7,
               "status": "below|above|unknown", "matched_name": "…" }  # Phase 3
}
```

### Snapshot (per store, in `state/<store>.json`)
Map of `variant_id -> { price, in_stock, title, is_preorder }` for all watched products as of
the last successful run. Plus a top-level `last_run` timestamp and `seeded: true` flag.

---

## 6. Store Roster (Phase 1)

| Store | Platform | Region | Currency | Tier |
|---|---|---|---|---|
| collectorsrow.cards | Shopify | US | USD | 1 |
| collectorstore.com | Shopify | US | USD | 1 |
| thepokehive.com | Shopify | US | USD | 1 |
| hobbiesville.com | Shopify | CA | CAD | 1 |
| deckoutgaming.ca | Shopify | CA | CAD | 1 |
| tcgsorted (shop.app) | Shopify | US (TBD) | USD (TBD) | 1 — **domain spike** |
| allpoketcg.com | Shopify | US | USD | 1 |
| skyboxct.com | Shopify | US | USD | 1 |
| matrixtcg.com | Shopify | US | USD | 1 — best DBZ/One Piece |
| 401games.ca | Shopify | CA | CAD | 1 |

**Phase 2 (Tier 2):** pokelegendstcg.com (Wix), bulbacards.com (Wix), rarecandy.com (Next.js).

Each store entry in config carries: `key`, `base_url`, `platform`, `currency`, `enabled`.
Currency drives USD-normalization for deal-flagging (Phase 3).

---

## 7. Franchise Watchlist & Matching

Watchlist is an editable config list. Initial: `pokemon`, `one piece`, `dragon ball`.

**Matching order (per product):**
1. Shopify `tags` (most reliable — shops categorize by franchise).
2. `product_type`.
3. `title` substring (last resort; tune to avoid false hits like a "Pikachu" sleeve).

Synonyms map per franchise (e.g. dragon ball → "dragon ball", "dbs", "dragon ball super",
"fusion world"). Unmatched products are dropped (not alerted). The watchlist is meant to be
tuned over time as false matches surface.

---

## 8. Event Detection Logic

Computed by diffing current normalized products against the previous snapshot, keyed by
`variant_id`:

- **restock:** variant existed, was `in_stock=false`, now `in_stock=true`.
- **new_product:** `variant_id` not present in previous snapshot at all.
- **preorder_open:** product flips into a preorder state (tag/title heuristic) and is buyable.
  On Shopify this often coincides with new_product or restock — dedupe so one change = one
  alert (preorder takes precedence in the label).
- **price_change:** variant present in both, `price` differs beyond a small epsilon. Direction
  (↑/↓) included.

**Seed-first rule:** if a store's snapshot is missing or `seeded != true`, write the snapshot
and send **no** alerts for that store on that run. Alerts begin the next run. Prevents the
first-run "everything is new" flood.

**Flood control:** if a single store produces more than `MAX_EVENTS_PER_STORE` (e.g. 25) in
one run (mass re-tag / bulk import), send **one summary embed** instead of N pings.

---

## 9. Deal-Flagging (Phase 3)

For each event, attach a **price verdict** by matching the product to a TCGplayer market price.

**Data source:** [tcgcsv.com](https://tcgcsv.com) — republishes TCGplayer category → group →
product → price data as static daily JSON. We **never call TCGplayer directly** (avoids ToS
violation, anti-bot, and datacenter-IP blocks). Confirmed coverage: Pokemon (EN + JP), One
Piece Card Game, Dragon Ball Z TCG / Super CCG / Fusion World. `marketPrice` present per
product (verified: Prismatic Evolutions = 399 products, 397 priced).

**Matching:** sealed products first (booster boxes, ETBs, bundles, collections — names match
reliably). Build an index of TCGplayer product names → marketPrice per franchise; fuzzy-match
the Shopify title with a **high confidence threshold**.

**Verdict → routing:**
- **below market** → `#deals` webhook, **loud** (with @-mention), shows `% under`.
- **above market** → `#tracker` webhook, quiet, flagged "above market."
- **no confident match** → quiet, `market: n/a`. **Never suppress an alert on lookup failure.**

**Currency normalization:** convert store price to USD via a daily FX rate before the
below/above decision; display both (`C$120 ≈ US$88`).

---

## 10. Notifications (Discord)

Two incoming webhooks (URLs stored as encrypted GitHub Actions secrets):
- **DEALS webhook** — loud channel, gets @-mention on below-market events.
- **TRACKER webhook** — quiet channel, all other events.

Embed contents: store name, product title, franchise tag, event type (restock/new/preorder/
price), current price (+ previous if price_change), market verdict (Phase 3), product image,
and a **"Buy now" link** straight to the product page.

---

## 11. State, Persistence & Scheduling

- **State:** `state/<store>.json` snapshots committed back to the repo each run → free history,
  git-diff debugging, survives between stateless Action runs.
- **Repo:** **public** so Actions minutes are unlimited. Nothing sensitive is public (only the
  watchlist and stock states); webhooks live in encrypted secrets.
- **Scheduler:** GitHub Actions `schedule` cron at `*/5` (best-effort; real cadence ~5–15 min
  under load). Committing state each run keeps the scheduled workflow from auto-disabling after
  60 days idle.
- **Concurrency:** Actions `concurrency` group cancels overlapping runs; commit with pull/rebase
  to avoid state races.

---

## 12. Error Handling Philosophy

- **Adapter isolation:** any single store/adapter failure is logged and skipped; the run
  continues for all other stores. One broken site never blocks alerts for the rest.
- **Never suppress an alert** because an enrichment step (price lookup, image, FX) failed —
  degrade gracefully and mark the missing field.
- Crash only on programmer error / corrupted state, not on expected network flakiness.

---

## 13. Landmines & Mitigations

| # | Landmine | Sev | Mitigation |
|---|---|---|---|
| 1 | Cloudflare blocks GitHub datacenter IPs (seen live on dacardworld/vaultofcards). | 🔴 | **Spike first:** a one-off Action hitting all 10 feeds before building. If blocked, free proxy or always-on box. |
| 2 | GitHub cron is best-effort, min 5 min; hot drops sell out faster. | 🟡 | Accept for preorders/most restocks; documented. Always-on box is the upgrade path. |
| 3 | Shopify gives in/out only, not quantity. | 🟢 | Out of scope by design. |
| 4 | First-run "everything is new" flood. | 🟡 | Seed-first: write snapshot, send nothing on first run per store. |
| 5 | Franchise match miss/over-match. | 🟡 | tags/product_type first, title last; tunable watchlist. |
| 6 | Overlapping runs corrupt state. | 🟡 | Actions `concurrency` group + commit with rebase. |
| 7 | Wix/Next adapters break on redesign. | 🟡 | Isolated per-adapter; broken adapter logs + skips. Best-effort tier. |
| 8 | Notification floods (bulk re-tag). | 🟡 | Per-store event cap → single summary embed. |
| 9 | ToS / rate-limiting on stores. | 🟢 | 5-min cadence, realistic UA, light pagination. |
| 10 | Scheduled workflow auto-disables after 60 days idle. | 🟢 | State commit each run = activity, stays alive. |
| 11 | Fuzzy price match → wrong "deal." | 🟡 | Sealed-first, high match threshold, show matched name; low-confidence → "n/a" quiet. |
| 12 | tcgcsv is daily; market price lags hot drops. | 🟢 | "Below market" is approximate; documented. |
| 13 | Currency mismatch (CAD store vs USD market). | 🟡 | Normalize to USD via daily FX before verdict; show both. |

---

## 14. Open Questions / Spikes (resolve during implementation)

1. **tcgsorted real domain** — resolve `shop.app/m/tcgsorted` → canonical `*.com` / `*.myshopify.com`.
2. **Cloudflare-from-Actions spike** (Landmine #1) — verify all 10 feeds return 200 from a
   GitHub runner before building the engine. This is the first build task.
3. **FX source** (Phase 3) — pick a free daily USD FX feed for CAD normalization.
4. **401games feed validation** — first batch threw a transient JSON error; confirm clean
   paginated parse.

---

## 15. Phasing

1. **Phase 1 — Core engine:** 10 Shopify stores, filter, diff, 4 events, Discord, GH Actions,
   seed-first. *Ships a fully working watcher with zero TCGplayer dependency.*
2. **Phase 2 — Tier-2 sites:** Wix ×2 + rarecandy, best-effort, isolated.
3. **Phase 3 — Deal-flagging:** tcgcsv oracle, sealed-first matching, loud/quiet split, USD
   normalization.

---

## 16. Phase-1 implementation deltas (as-built, 2026-07-01)

The shipped Phase 1 diverged from the original design based on empirical findings during
implementation (see the Cloudflare-from-Actions spike, Landmine #1):

- **Sealed-only scope.** Landmine #1 was worse than anticipated: GitHub datacenter IPs get
  Cloudflare **429**'d when crawling full catalogs (the stores are tens-of-thousands of
  *singles*). Rather than a proxy/always-on box, the fix was to **fetch only sealed product**
  (booster boxes, ETBs, bundles, tins, blisters) — which is the actual use case and cuts each
  run to ~40 requests. Individual singles are out of scope. *(User-approved scope change.)*
- **Fetch modes.** Big stores use **curated sealed collections** (`collections =
  ["franchise:handle", …]` in config; trusted as sealed + franchise-tagged, no heuristic
  filtering). Small stores (thepokehive, allpoketcg, matrixtcg) **full-crawl + `keep_sealed`
  filter**. New `Store.collections` field + runner branch.
- **Polite HTTP layer.** Added min-interval throttle (2.5s), `Retry-After` honoring, and
  exponential-backoff retries to `make_httpx_get` to stay under Cloudflare's limit.
- **Roster = 8 stores** (not 10): `store.401games.ca` (apex redirects there; DBZ sealed only —
  its Pokémon/OP sealed aren't cleanly targetable); **collectorstore dropped** (Funko-heavy, no
  clean sealed TCG); **tcgsorted deferred** (no resolvable storefront).
- **Phase-1 loud routing** = restock/preorder → `#deals` (loud), new/price-change → `#tracker`
  (quiet). (Spec's below-market loud is Phase 3.)
- **Price-change refinement:** only emitted for in-stock variants (out-of-stock price changes
  suppressed as noise).
- **Verified live** on GitHub Actions: 8/8 stores, 0 failures, 0 × 429, seed-first silent,
  steady-state 0 spurious events, state committed. 47 tests green.
- **Deferred follow-ups:** 401games Pokémon/OP sealed handles; drop bare `"bundle"` sealed
  marker + crash-on-missing-id in adapter (minor, full-crawl only); tcgsorted + collectorstore.
