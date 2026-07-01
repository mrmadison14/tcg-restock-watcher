# Phase 3 — Deal-Flagging: Design Spec

**Date:** 2026-07-01
**Status:** Approved in brainstorming — pending written-spec review
**Extends:** `2026-06-30-tcg-restock-watcher-design.md` §9 (this supersedes that stub with an implementable design)

## 1. Goal

Attach a **TCGplayer market-price verdict** to every event. Fire a **loud `#deals`** alert (with `@here`) when a listing is a real deal (≥10% below market) **or** is a time-sensitive restock/preorder. Everything else goes **quiet to `#tracker`**, enriched with the verdict. We **never call TCGplayer directly** — we read tcgcsv.com's daily mirror.

## 2. Decisions (locked in brainstorming)

- **Index refresh:** a **separate daily GitHub Action** builds and commits the price index + FX rate; the 5-min `watch` only *reads* them (zero tcgcsv calls in the hot path).
- **Deal threshold:** **≥10%** below market (USD-normalized) fires loud. Below-but-under-10% is logged quiet.
- **Loud mention:** `@here`, via `content:"@here"` + `allowed_mentions:{parse:["everyone"]}`. (There is no `"here"` parse type — the known gotcha.)
- **Matcher:** Python **stdlib `difflib`** — no new dependency.
- **Routing:** **union** — loud iff `(≥10% below market) OR (event is RESTOCK or PREORDER_OPEN)`; everything else quiet. Preserves Phase-1 "act now" behavior *and* adds price deals.

## 3. tcgcsv access (spike-verified 2026-07-01)

- **Free, no API key.** Cloudflare returns **401** to datacenter fetchers using a default UA → the client **must send a realistic browser User-Agent** (same lesson as the stores). Polite throttle (~1 req/s; reuse the `http.py` throttle/backoff).
- **Endpoints** (`{success, errors, results:[…]}` JSON):
  - `GET /tcgplayer/categories`
  - `GET /tcgplayer/{cat}/groups`
  - `GET /tcgplayer/{cat}/{grp}/products`
  - `GET /tcgplayer/{cat}/{grp}/prices`
- **Sealed products carry `marketPrice`** (verified on Pokémon set 3170 "Silver Tempest": 28/34 sealed-named products priced — Booster Box $544.53, Elite Trainer Box $170.20, Booster Bundle $118.22, Booster Pack $13.20, …). Sealed price rows use a single `subTypeName:"Normal"`. Unpriced oddballs (e.g. "Collector Chest Case") → `market: n/a`.
- **Join:** products ↔ prices by `productId` (one-to-many; for sealed, take the `"Normal"` row's `marketPrice`). Prices are **USD**.
- **Cadence:** tcgcsv updates once daily ~20:00 UTC.

## 4. Category → franchise map (config; confirm exact IDs at build time)

| Franchise | tcgcsv category IDs |
|---|---|
| pokemon | 3 (English), 85 (Japanese) |
| one piece | 68 |
| dragon ball | 23, 27, 80 (DBZ TCG / Super CCG / Fusion World) |

A per-category fetch failure is **isolated and logged**; a missing/renamed category never aborts the whole build. IDs live in config so a TCGplayer re-categorization is a config edit, not a code change.

## 5. Components (new, small, independently testable)

- **`pricing/tcgcsv.py`** — thin client: `groups(cat)`, `products(cat, grp)`, `prices(cat, grp)`. Realistic UA + throttle + retry (reuse the existing HTTP layer).
- **`pricing/match.py`** — pure functions:
  - `normalize(title) -> str`: lowercase; strip franchise words ("pokemon"/"one piece"/"dragon ball"), edition words ("english"/"japanese"), punctuation; canonicalize `etb ↔ "elite trainer box"`.
  - `best_match(norm_title, franchise_index, threshold) -> (display_name, market_usd) | None`: `difflib.SequenceMatcher` (+ token-overlap guard), threshold ~0.86. Returns `None` below threshold.
- **`pricing/build_index.py`** — daily builder (CLI entrypoint). For each franchise's categories, walk every group, fetch products + prices, keep **sealed-named** products, join the `"Normal"` `marketPrice`, accumulate `{franchise: {normalized_name: {market_usd, display_name}}}`. Write `data/price_index.json`. Then fetch FX → `data/fx.json`.
- **`pricing/oracle.py`** — runtime: `load(index_path, fx_path)` once per run; `verdict(product) -> Verdict`. Normalize the store title → `best_match` scoped to `product.franchise` → convert store price to USD (USD passthrough; CAD via FX) → `pct_under = (market_usd - store_usd) / market_usd` → assign status.

## 6. Data model

`Verdict` dataclass:

- `status: Literal["deal", "market", "na"]`
  - `deal` — matched **and** `pct_under >= deal_threshold`
  - `market` — matched but not a deal (below-threshold, at, or above market)
  - `na` — no confident match, or FX/index unavailable
- `market_usd: float | None`
- `store_usd: float | None`
- `pct_under: float | None`
- `matched_name: str | None`
- `currency: str` (store's native currency)

`Event` gains `verdict: Verdict | None = None`, set after diff, before notify.

## 7. Data flow

- **Daily** (`build-index.yml`, cron `30 20 * * *` + manual dispatch): run `build_index` → commit `data/price_index.json` + `data/fx.json` (pull --rebase before push; own concurrency group). Does **not** trigger `watch` (`watch` is schedule/dispatch only, not on push).
- **Every 5 min** (`watch`): `oracle.load()` once → after `detect_events`, set `event.verdict = oracle.verdict(event.product)` per event → `send_events` routes on verdict. Separate runners/filesystems → `watch` always reads the last-committed index; no runner-local race.

## 8. Routing (notify.py)

For each event:

- **Loud** (`post_loud`, `@here`) iff `verdict.status == "deal"` **OR** `event.type in {RESTOCK, PREORDER_OPEN}`.
- **Quiet** (`post_quiet`) otherwise.
- **Embed always** includes a verdict line and, for CAD stores, both currencies:
  - `deal` → `🔥 14% under market (C$120 ≈ US$88 vs US$102 market)`
  - `market` → shows the **actual signed delta**, e.g. `3% under market`, `at market`, or `6% above market (US$88 vs US$85 market)` — never a blanket label, since this band spans 0–10% under through above
  - `na` → `market: n/a`
- Existing `max_events_per_store` cap and loud/quiet split are preserved.

## 9. Error handling (§12 — never suppress an alert on enrichment failure)

- Oracle load fails (missing/corrupt index or FX) → every verdict is `na`; events **still post** (quiet unless restock/preorder). Log a warning.
- No confident match → `na`.
- FX missing for a store's currency → `na` (can't compare); event still posts showing native price.
- Daily build failure → the last committed index/FX **stay in use**; the workflow exits non-zero (visibly red) without overwriting good files. Per-category failures are isolated.

## 10. Config (`config.toml`)

```toml
[pricing]
enabled = true
deal_threshold = 0.10
match_threshold = 0.86
index_path = "data/price_index.json"
fx_path = "data/fx.json"
fx_url = "https://open.er-api.com/v6/latest/USD"   # free, no key; USD base, invert for CAD->USD

[pricing.categories]
pokemon = [3, 85]
"one piece" = [68]
"dragon ball" = [23, 27, 80]
```

## 11. Files & workflow

- **New:** `src/tcg_watcher/pricing/{__init__,tcgcsv,match,build_index,oracle}.py`
- **New:** `data/price_index.json`, `data/fx.json` (committed; regenerated daily)
- **New:** `.github/workflows/build-index.yml` (daily cron + dispatch; commits `data/`)
- **Modified:** `models.py` (`Verdict`, `Event.verdict`), `runner.py` (load oracle, enrich events), `notify.py` (verdict routing + `@here` + verdict/dual-currency embed line), `config.py` (`[pricing]`)

## 12. Testing (TDD, RED→GREEN)

- **`match`**: normalization cases; exact + fuzzy match above threshold; below-threshold → `None`; franchise scoping.
- **`oracle`**: `deal` (≥10% under), `market` (matched, not a deal), `na` (no match); CAD→USD conversion; oracle-load-failure → all `na`, no exception raised.
- **`build_index`**: sealed filter drops singles; price join picks the `"Normal"` `marketPrice`; franchise partitioning; per-category failure isolated (mocked HTTP).
- **`notify`**: `deal` → loud with correct `@here` `allowed_mentions`; restock → loud; new-listing-at-market → quiet; `na` → quiet; embed shows verdict + dual currency.
- **Regression**: existing 50 tests stay green.

## 13. Landmines & mitigations

| # | Landmine | Mitigation |
|---|---|---|
| 11 | Fuzzy match → wrong "deal" | High threshold (0.86); show matched name in embed; low-confidence → `na` quiet |
| 12 | tcgcsv is daily → market lags hot drops | Verdicts approximate; documented; show `fetched_at` |
| 13 | Currency mismatch (CAD store vs USD market) | Normalize to USD via daily FX; show both |
| new | tcgcsv Cloudflare 401 on datacenter IPs | Realistic UA (spike-confirmed) + polite throttle |

## 14. Out of scope / future

- Pricing for singles (non-sealed) — out of scope by design.
- Historical price trends.
- Build-time optimization: restrict the daily walk to recent groups (last N sets) if build time grows. v1 walks all groups (daily job is unconstrained on time).
