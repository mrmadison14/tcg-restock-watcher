# Phase 2 Handoff — Wix ×2 adapter (for a fresh session)

**Written:** 2026-07-06 (end of session 5) · **For:** whoever picks up Phase 2 (Fable model)
**Companion:** `PHASE2_SCOPING.md` (the deep feasibility study — read it second, this brief first).

You are picking up a **live, healthy** personal project. This brief is the zero-context entry
point: what's true now, the one decision to make, the single prerequisite, and exactly where to cut.

---

## 1. What this project is (30-second version)

`tcg-restock-watcher` polls TCG stores every ~5 min for **sealed** Pokémon / One Piece / Dragon Ball
product and posts restock / new-listing / preorder / price-change alerts to Discord, with TCGplayer
below-market **deal-flagging**. Python 3.13 + uv + httpx. No DB, no framework, no frontend. Runs free
on GitHub Actions (personal GitHub `mrmadison14`); state is committed back to the repo every run.

**Hard rules:** Python 3.13, **uv only**. **No comments in production code. No new deps without asking.**
**Sealed-only scope** (singles trip Cloudflare 429). TDD (RED→GREEN). Commit as
`mrmadison14 <mr.madison@gmail.com>`; end commit messages with the `Co-Authored-By: Claude Opus 4.8`
trailer. The Actions bot commits `state/`+`data/` to `main` every few min → **always
`git pull --rebase` before pushing.**

## 2. Current verified state (start-of-your-session baseline)

- 🟢 LIVE + autonomous. **26 stores, 139 tests green**, working tree clean, synced to `origin/main`.
- **Verify before touching anything:**
  ```bash
  cd /Users/jmadison/workspace/tcg-restock-watcher
  git pull --rebase && uv run pytest -q          # expect: 139 passed
  gh run list --workflow=watch --limit 5         # expect: recent = success
  ```
  If tests < 139 or stores ≠ 26, reconcile against `SESSION_HISTORY.md` (top entry) before changing code.

## 3. The Phase 2 goal

Add the **two remaining non-Shopify stores** named in the design spec:

| Site | Platform | Currency |
|---|---|---|
| `pokelegendstcg.com` | **Wix Stores** | USD |
| `bulbacards.com` | **Wix Stores** | USD |

One shared adapter — **`src/tcg_watcher/adapters/wix.py`** — serves both (same platform/data shape).
rarecandy (the third non-Shopify site) already shipped in an earlier session; do not re-do it.

## 4. THE decision to make first (owner sign-off needed)

`PHASE2_SCOPING.md §2 + §6` establishes that Wix SSRs **only the first page** (~16 items) of a gallery.
Two paths — pick one **before** building:

- **(A) Full-catalog** via the Wix Stores storefront **GraphQL POST** (`/_api/wix-ecommerce-storefront-web/api`)
  with a bearer minted from `/_api/v1/access-tokens`. Real coverage. **~2–2.5 days.** Recommended if the
  point is catching *new* sealed drops (many never appear in the SSR'd first page).
- **(B) Best-effort SSR scrape** — parse the ~16 SSR'd products from the gallery HTML. **~1 day.**
  Cheap but **low value** (misses most of the catalog). Ship only as a deliberately-labeled v1.

**My recommendation: (A)** — a restock watcher that only sees page 1 is nearly pointless here.
But confirm with the owner; it's the difference between a 1-day and a 2.5-day task.

## 5. THE prerequisite (blocks both adapters)

The shared HTTP client `src/tcg_watcher/http.py::make_httpx_get` is **GET-only and always returns
`.json()`**. Phase 2 needs (depending on path chosen):
- a **raw-text GET** (to pull HTML / Wix warmup JSON), and/or
- a **POST-capable JSON caller** (for the Wix storefront GraphQL + the token mint).

Add a small sibling in `http.py` that **reuses the same throttle / Retry-After / backoff / Chrome-UA
machinery** (see how `make_httpx_get` and `make_discord_poster` already do it). Keep `httpx`-only.
**This is a cross-cutting change to the adapter contract — get owner sign-off first** (it's plumbing,
not a new dep). Precedent: the rarecandy adapter already added an `as_text=True` option to `http.get`
for HTML — look at that first; you may just extend it plus add `post_json`.

## 6. The adapter contract (what `wix.py` must satisfy)

Reference: `src/tcg_watcher/adapters/shopify.py` and `adapters/rarecandy.py`; wired in `runner.py`.

- **Register** the platform: `runner._ADAPTERS = {"shopify": ..., "rarecandy": ..., "wix": wix.fetch_products}`.
- **Signature:** `fetch_products(store: Store, http_get) -> list[models.Product]`.
- **Populate** (frozen `Product`): `store`(=`store.key`), `product_id`, `variant_id`, `title`, `price: float`,
  `currency`, `in_stock: bool`, `url`; plus `image`, `tags`, `is_preorder`, `is_sealed`, `franchise`.
- **Stable `variant_id`/`product_id` across runs is MANDATORY** — a changing id = phantom restock/new-product
  spam. Wix ids in the warmup blob look stable but **verify across two fetches before enabling alerts** (§6.3).
- **Filtering:** the runner applies `keep_sealed(filter_franchises(...))` **only when `store.collections`
  is empty**. Wix objects carry no franchise tag, so franchise/sealed detection falls to title/product_type
  (least-reliable tier — same marker approach as Shopify's `_SEALED_MARKERS`). `pokelegends /shop` is
  **preorder-heavy** (10/16 SSR'd items) so preorder detection matters.
- **`bulbacards /shop` 404s** — its gallery route differs. Make the gallery/listing path **config-driven**
  (add an optional `shop_path` field to `Store` in `config.py`; do NOT hardcode `/shop`). Resolve
  bulbacards' real route live before building.

## 7. Test approach (mirror `tests/test_shopify_adapter.py` + `test_rarecandy_adapter.py`)

- Construct a `Store`, inject a fake `http_get` (or fake text/POST caller), assert mapped `Product` fields.
- **Fixtures = trimmed real captures** under `tests/fixtures/` (a Wix warmup-JSON snippet; if path A, a
  GraphQL response snippet). **No network in tests.**
- Cover: preorder detection (Wix slug/title-based), `in_stock` mapping, and a **stable-id assertion**.
- Keep `uv run pytest -q` green; don't reformat out-of-scope files (`ruff` scope discipline).

## 8. Gotchas carried from scoping / this codebase

- Wix storefront GraphQL is **undocumented** — treat the adapter as best-effort; the runner already
  catches per-store adapter exceptions and continues, so a Wix failure won't take down the run.
- **Never full-crawl a huge catalog** (Cloudflare 429 from GitHub IPs). Page-cap like Shopify's `_MAX_PAGES`;
  scope to sealed + watched franchises.
- Curated store (has `collections`) → products trusted, no filter. Full-crawl (no `collections`) →
  `keep_sealed(filter_franchises(...))`. Decide which model Wix uses (likely full-crawl-with-filter given
  no clean franchise tags, but keep it small).
- The polite throttle in `http.py` (min_interval + Retry-After + backoff) **must** be inherited by any new caller.

## 9. Suggested first moves

1. Run the §2 verification; confirm 139 green.
2. **Get the (A)-vs-(B) decision** and the `http.py` sign-off from the owner (§4, §5).
3. Live-probe both sites with the project Chrome UA: confirm Wix warmup-JSON shape on `pokelegends /shop`,
   and **resolve bulbacards' real gallery route** (§6). Save trimmed fixtures.
4. TDD the `http.py` helper → `wix.py` → config `shop_path` field → register in `runner` → `config.toml`
   blocks (`enabled = false` until id-stability is verified) → README + `SESSION_HISTORY.md`.
5. Enable alerts only after a silent seed + a two-fetch id-stability check.

---

*State/data commits by the Actions bot advance `main` constantly — that's expected, not drift. The last
human commit at handoff was `74a07bee` (session-5 log).* 
