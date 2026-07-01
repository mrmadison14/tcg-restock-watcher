# Phase 2 Scoping — Non-Shopify Adapters (2 Wix + rarecandy)

**Date:** 2026-07-01
**Author:** exploration pass (no code implemented)
**Status:** Scoping / feasibility only — do NOT treat as an implementation plan.

## 0. Scope

Phase 1 = Shopify stores (shared `adapters/shopify.py`). Phase 2 adds **three** Tier-2, non-Shopify sites named in the design spec (`docs/superpowers/specs/2026-06-30-tcg-restock-watcher-design.md` §6, line 135):

| Site | Spec platform | Confirmed platform | Region/currency (assumed) |
|---|---|---|---|
| `pokelegendstcg.com` | Wix | **Wix Stores** ✅ | US / USD |
| `bulbacards.com` | Wix | **Wix Stores** ✅ | US / USD |
| `rarecandy.com` | Next.js | **Next.js + Apollo GraphQL** ✅ | US / USD |

**NOT in scope:** `tcgsorted` (shop.app) is a *separate* deferred Shopify-domain spike, tracked in the Phase 1 plan — it is not one of these three.

All findings below are from live, unauthenticated probes on 2026-07-01 using the project's Chrome UA. No Cloudflare / anti-bot challenge was hit on any of the three with a plain `httpx`-style GET (realistic UA sufficed). No headless browser was needed to *read* data on any site — see per-site notes for the catalog-completeness caveat on Wix.

---

## 1. The adapter contract (what any new adapter must satisfy)

Reference: `src/tcg_watcher/adapters/shopify.py`, wired in `src/tcg_watcher/runner.py`.

- **Registry:** `runner._ADAPTERS = {"shopify": shopify.fetch_products}`. A new platform = a new key here mapping `store.platform` → a `fetch_products` callable.
- **Signature:** `fetch_products(store: Store, http_get) -> list[Product]`.
  - `store` is the frozen `config.Store` dataclass: `key, base_url, platform, currency, enabled=True, collections=()`.
  - `http_get(url, params=None) -> parsed-JSON` is the shared client from `http.py` (Chrome UA, 2.5s min-interval throttle, `Retry-After`, exponential backoff, `raise_for_status`). **It calls `.json()` on every response** — so it only works for endpoints that return JSON. HTML pages and GraphQL-POST cannot go through the current `http_get` unchanged (see §6, biggest risk).
- **Output:** a list of `models.Product` (frozen dataclass). Required fields an adapter must populate:
  `store` (=`store.key`), `product_id`, `variant_id`, `title`, `price: float`, `currency` (=`store.currency`), `in_stock: bool`, `url`. Optional but expected: `image`, `product_type`, `tags: tuple`, `is_preorder`, `is_sealed`, `franchise`.
- **Sealed/franchise filtering:** the runner applies `keep_sealed(filter_franchises(products, synonyms))` **only when `store.collections` is empty**. If `store.collections` is set, the runner trusts the adapter's output verbatim (no post-filter). So an adapter can either (a) return everything and let the runner filter, or (b) pre-scope via curated collections/categories and set `store.collections` so the runner skips filtering. `filter_franchises` matches synonyms against `tags` → `product_type` → `title` (in that tier order). `keep_sealed` keeps `p.is_sealed`. `is_sealed`/`is_preorder` are set by the adapter (Shopify uses title/product_type/tag marker lists).
- **Seeding & events:** handled entirely by the runner/`diff.py` keyed on `variant_id` — the adapter does not touch state. So **stable `variant_id` and `product_id` across runs are mandatory** (a changing id = phantom restock/new-product spam).

**Implication:** each Phase 2 adapter's whole job is: fetch → normalize into `Product` with a *stable* id, correct `price`/`in_stock`, a real `url`, and enough signal (`tags`/`title`) for sealed+franchise filtering.

---

## 2. Wix Stores — `pokelegendstcg.com` and `bulbacards.com`

### Platform confirmation
Both are **Wix Stores**, confirmed via:
- Response header `server: Pepyaka` + `x-seen-by: …` (Wix edge).
- Homepage HTML contains `metaSiteId` (e.g. pokelegends = `a7928bf4-f432-4867-8515-da846dee484c`), the **Wix Stores appDefId `1380b703-ce81-ff05-f115-39571d94dfcd`** (×45), `wixstores` (×147), `static.wixstatic.com` (×539), `"Add to Cart"` (×25).
- `/products.json` → HTTP 400 (not Shopify). `/_api/stores-reader/v1/products/query` and `/api/v1/products` → **403** (token-gated).

### Machine-readable data & its shape
Wix **server-renders product objects into the page HTML** as JSON inside the Wix "warmup data" blob. Example object (from `/shop`):
```
"productType":"physical","ribbon":"","price":45,"comparePrice":0,
"sku":"","isInStock":true,"urlPart":"chaos-rising-booster-bundle",
"formattedPrice":"$45.00","name":"…"
```
Field mapping to `Product`:
- `product_id`/`variant_id` → the product `id` (a `dd011e…`-style Wix id is present in the same object; **must confirm it is stable** — see risk). Wix Stores products can have variants; sealed products are typically single-variant, so `variant_id = product_id` is a safe default.
- `title` → `name`. `price` → `price` (numeric) or parse `formattedPrice`. `in_stock` → `isInStock`. `currency` → from `formattedPrice` symbol or store config.
- `url` → `{base_url}/product-page/{urlPart}` (confirmed URL model).
- `is_preorder` → detectable from `urlPart`/`name` ("preorder", "pre-order", "ships-12-3", etc.). On pokelegends `/shop`, **10 of 16** SSR'd slugs were preorders — this store is preorder-heavy, so preorder handling matters.
- `is_sealed`/`franchise` → title-based (same marker approach as Shopify); Wix objects here carry no franchise tag, so filtering falls to `title`/`product_type` tier (least reliable tier).

### The catalog-completeness problem (the crux for Wix)
The gallery page SSRs **only the first page** of products, not the whole catalog:
- `pokelegendstcg.com/shop` → HTTP 200, **16 product objects (8 unique, duplicated in mobile+desktop markup)** embedded. Wix galleries lazy-load the remainder over the storefront GraphQL as the user scrolls.
- `bulbacards.com/shop` → **HTTP 404**. Its gallery lives at a different route (the two sites do NOT share the same page paths). Common Wix paths tried (`/store`, `/all-products`, `/category/all-products`, `/collections/all`, `/shop-all`) all 404 on pokelegends too.

To get the **full sealed catalog** you have two options:
1. **HTML-scrape the gallery page(s)** and accept only what Wix SSRs (first ~12–16 items). Cheap, no auth, `httpx`-only — but *incomplete* (misses everything past page 1). Marginal for a restock watcher whose value is catching *new* sealed drops, many of which may never be in the SSR'd first page.
2. **Call the Wix Stores storefront GraphQL** (`/_api/wix-ecommerce-storefront-web/api`, POST) with an `Authorization: <instance>` bearer minted from `/_api/v1/access-tokens` (that endpoint IS present in the HTML). This yields the full paginated catalog with stock/price. But it requires: a token-fetch step, a POST GraphQL call (JSON body + custom header), and per-site query/collection knowledge. This does **not** fit the current `http_get` (which is GET-only and assumes JSON responses — a GraphQL POST with a bearer header cannot go through it unchanged).

### Difficulty: **HARD** (both Wix sites)
Reason: no clean public JSON feed. Either scrape partial SSR HTML (incomplete catalog — low value) **or** implement a two-step token + GraphQL-POST client that the current shared `http_get` does not support (new HTTP plumbing, still `httpx`-only but a real lift). Per-site route/structure differences (bulbacards `/shop` 404) mean the page path must be config-driven, not hardcoded. Not *blocked* (no anti-bot, no headless browser needed), but the highest-effort of the three.

---

## 3. rarecandy.com — Next.js + Apollo GraphQL

### Platform confirmation
**Next.js** confirmed: `__NEXT_DATA__` script present, `buildId` (`k4Pou7VpTQ8rdHjGAFHFL`), `/_next/static/<buildId>/…`. No Cloudflare challenge. Note it is a **multi-seller marketplace of "drops"** (consignment/auction-flavored: stores like `ninetalestradingcompany`, "Recent sales", "Top Bid"), not a single-storefront shop.

### Machine-readable data & its shape — best of the three
`__NEXT_DATA__ → props.pageProps.__APOLLO_STATE__` is a normalized Apollo cache embedded in every page. On the homepage it held **65 `Product` entities**; `/shop` = 65, `/discover` = 66, `/deals` = 51. Each `Product`:
```
keys: id, thumbnail, name, price, shippingHandling*, limitPerPerson,
      tags, categories, quantity, showScarcity, thresholdExceeded
```
Field mapping to `Product` (near 1:1, no title-guessing needed):
- `product_id`/`variant_id` → `Product.id` (integer, e.g. `298699` — stable per listing).
- `title` → `name`. `price` → `price` (numeric). `image` → `thumbnail`.
- `in_stock` → `quantity > 0` (**actual stock count available** — better than Shopify's boolean).
- **`tags`/`categories` carry `pokemon` / `onepiece` / `dbz` AND `sealed`** directly — e.g. `['pokemon','english','sealed']`, `['onepiece','sealed','japanese']`, `['dbz','sealed','japanese']`. All three watched franchises confirmed present. This means franchise + sealed filtering is a clean tag lookup — the highest-fidelity filtering of any site in the whole project.
- `is_preorder` → not an explicit field seen; infer from `name` or `tags` if present.
- `url` → constructed from the `RareFind` entity (`RareFind{ id, slug, store, product }`) + its `Store.slug` → likely `/{store.slug}/{rareFind.slug}` (marketplace product page). Must confirm exact path when building.

### Two viable data routes
1. **Scrape `__NEXT_DATA__` Apollo state from HTML pages** (`/shop`, `/discover`, `/deals`) — no auth, works today, 50–66 products per page.
2. **Hit the GraphQL API directly:** `https://api.rarecandy.com/graphql` is a **live Apollo endpoint** (returned structured `{"errors":[…]}` JSON to a probe, i.e. it parses queries — needs a valid `operationName`/query). The `Query` root exposes `shopView`, **`rareFindCatalog({"page":1})` (built-in pagination)**, `store({"slug":…})`, `discoverView`. This is the clean path to the *full* catalog. (Note: same-origin `/api/graphql`, `/gql`, `/v1/graphql` are 404/SPA — the real host is `api.rarecandy.com`.)

### Difficulty: **EASY–MEDIUM**
Reason: a real JSON/GraphQL feed exists with stock, price, and franchise+sealed tags — minimal normalization, no anti-bot, `httpx`-only. Two independent extraction paths (embedded Apollo JSON, or the public GraphQL host) de-risk it. Bumped from "easy" to "easy–medium" only because: (a) the GraphQL POST + `api.` host doesn't fit the current GET-only `http_get`, so it needs the same small POST-capable plumbing as Wix (or you scrape `__NEXT_DATA__` HTML instead, which *also* doesn't fit `http_get` since that's HTML not JSON); and (b) it's a marketplace, so URL construction spans `Product`→`RareFind`→`Store` and "one listing" semantics need a quick sanity check against restock/new-product diffing.

---

## 4. Difficulty summary

| Site | Platform | Feed | Anti-bot | Headless needed? | Difficulty |
|---|---|---|---|---|---|
| rarecandy.com | Next.js + Apollo GraphQL | `api.rarecandy.com/graphql` (paginated) **or** `__NEXT_DATA__` Apollo JSON | none | No | **Easy–Medium** |
| pokelegendstcg.com | Wix Stores | partial SSR HTML (~16) or token+GraphQL for full catalog | none | No | **Hard** |
| bulbacards.com | Wix Stores | same as above; gallery route differs (`/shop` 404) | none | No | **Hard** |

No site is *blocked*, and **no site requires a headless browser** (which would be out of scope — `httpx`-only, no new deps). The hard rating on Wix is about catalog completeness + POST/token plumbing, not about being unreadable.

---

## 5. Effort to COMPLETE Phase 2

### Adapters needed: **2** (not 3)
- **`adapters/wix.py`** — one adapter serving *both* Wix sites (same platform/data shape). Site-specific differences (gallery route: pokelegends `/shop` works, bulbacards `/shop` 404) must be **config-driven**, so add an optional per-store field (e.g. reuse/extend `collections`, or add a `paths`/`shop_path` field to `Store`). Register `"wix": wix.fetch_products`.
- **`adapters/rarecandy.py`** — single-site adapter (marketplace-specific URL/paging), keyed `"rarecandy"` (per-site platform string is fine; the registry maps platform→adapter). Register `"rarecandy": rarecandy.fetch_products`.

### Shared plumbing (the real cost, shared by both)
The current `http.py::make_httpx_get` is **GET-only and always returns `.json()`**. Phase 2 needs at least one of:
- a **POST-capable JSON caller** (for rarecandy GraphQL and, if chosen, Wix storefront GraphQL), and/or
- a **raw-text GET** (to pull HTML and parse `__NEXT_DATA__` / Wix warmup JSON).

Recommendation: add a small sibling in `http.py` (e.g. `make_httpx_get_text` and/or a `post_json`) that reuses the same throttle/backoff/UA machinery. Keep `httpx`-only. This is the single biggest structural change and is a prerequisite for both adapters. **Confirm with the owner before adding it** (it's plumbing, not a new dep, so likely fine — but it changes the adapter contract's assumption that adapters only ever receive a JSON-returning `http_get`).

### config.toml additions
```
[[stores]]
key = "rarecandy"
base_url = "https://rarecandy.com"
platform = "rarecandy"
currency = "USD"
# franchise+sealed come from tags; likely no collections needed (runner will filter)

[[stores]]
key = "pokelegendstcg"
base_url = "https://pokelegendstcg.com"
platform = "wix"
currency = "USD"
# shop_path = "/shop"   (new per-store field, TBD)

[[stores]]
key = "bulbacards"
base_url = "https://bulbacards.com"
platform = "wix"
currency = "USD"
# shop_path = "<resolve real gallery route>"  (do NOT assume /shop)
```
`config.py::load_config` and the `Store` dataclass need the new optional field if the config-driven route approach is taken.

### Test approach (mirror `tests/test_shopify_adapter.py`)
- Same pattern: construct a `Store`, inject a fake `http_get` (or fake text/POST caller), assert the mapped `Product` fields (`variant_id`, `price`, `in_stock`, `url`, `is_preorder`, `is_sealed`, franchise/tags).
- **Fixtures = trimmed real captures** (a few product objects each): a Wix warmup-JSON snippet, and a rarecandy `__APOLLO_STATE__` snippet. Save under `tests/fixtures/`. Do not hit the network in tests.
- Add cases for: preorder detection (Wix slug-based, given 10/16 pokelegends items are preorders), stock boolean vs `quantity>0` (rarecandy), and stable-id assertion (guards against phantom-restock spam).
- Keep `make validate` / the existing pytest suite green; do not reformat out-of-scope files.

### Rough estimate
- Shared `http.py` POST/text helper + tests: **~0.5 day.**
- `rarecandy.py` + fixtures + tests: **~0.5–1 day** (easy mapping; the only fiddly bit is URL construction + confirming `rareFindCatalog` paging vs scraping `__NEXT_DATA__`).
- `wix.py` + fixtures + tests: **~1.5–2.5 days**, driven by which path is chosen:
  - *SSR-scrape-only* (accept partial catalog): ~1 day, but low value (misses catalog past page 1).
  - *token + storefront GraphQL* (full catalog): ~2–2.5 days (token fetch, per-site query, paging, id-stability verification).
- config + wiring + `README`/docs update: **~0.25 day.**
- **Total: ~1 week** for a solid rarecandy + a full-catalog Wix adapter; **~2–3 days** if Wix ships SSR-scrape-only as a deliberate best-effort v1.

---

## 6. Biggest risks & unknowns

1. **`http_get` contract mismatch (highest impact).** Both adapters need capabilities the shared client lacks (POST, and/or raw HTML). This is a cross-cutting change gated on owner sign-off. Everything else depends on it.
2. **Wix catalog completeness.** SSR gives only the first page. A restock watcher that only sees ~16 of N sealed products will miss most new drops → weak value. The token+GraphQL path fixes this but is the bulk of the effort. **Decision needed:** full-catalog Wix (worth it) vs best-effort SSR (cheap, low value).
3. **Wix id stability.** `variant_id`/`product_id` must be stable across runs or the diff engine emits phantom restock/new-product alerts. Wix product ids in the warmup blob look stable but this must be verified across two fetches before trusting.
4. **bulbacards route unknown.** Its gallery is not `/shop`. The real product-listing route must be resolved per-site (reinforces config-driven paths; do not hardcode).
5. **rarecandy is a marketplace, not a shop.** Multi-seller "drops" with auction/consignment semantics. "In stock" = `quantity>0` is clean, but confirm that a listing's `id` is stable and that drop open/close windows don't masquerade as restocks. URL spans `Product`→`RareFind`→`Store`.
6. **Rate-limit / never full-crawl a huge catalog.** rarecandy's `rareFindCatalog` is paginated across *all sellers* (14+ stores seen) — capping pages and franchise/sealed-filtering server-side (via tags) is essential. The existing 2.5s throttle in `http.py` must be inherited by any new caller. Do not crawl the entire marketplace; scope to sealed + watched franchises and a sane page cap (mirror Shopify's `_MAX_PAGES`).
7. **Wix storefront GraphQL is undocumented/unofficial.** Query shape and the token-mint flow can change without notice; treat the Wix adapter as best-effort and isolate failures (the runner already catches per-store adapter exceptions and continues).

---

## 7. Recommendation

- **Do rarecandy first** — highest value per unit effort (clean feed, real stock counts, franchise+sealed tags, all three franchises present).
- **Land the shared POST/text `http_get` helper** as a small, owner-approved prerequisite.
- **For Wix, decide explicitly**: ship the full-catalog token+GraphQL adapter (recommended for real coverage) or a labeled best-effort SSR-scrape v1. Either way, make the gallery/listing route config-driven and verify id stability before enabling alerts.
- Keep everything `httpx`-only, no comments in production code, sealed-only scope, and page-capped to avoid marketplace-wide crawls.
