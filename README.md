# TCG Restock Watcher

Polls TCG stores every ~5 minutes for **sealed** Pokémon / One Piece / Dragon Ball product
(booster boxes, ETBs, bundles, tins, blisters, cases) and posts **restock / new-listing /
preorder / price-change** alerts to **Discord**. Runs on free GitHub Actions; state lives in
this repo. **Live** at https://github.com/mrmadison14/tcg-restock-watcher.

## How it works

```
per store: fetch sealed products → diff vs last snapshot → classify events
        → Discord (loud/quiet) → reconcile + commit snapshot
```

- `.github/workflows/watch.yml` runs `python -m tcg_watcher` every ~5 min and commits updated
  `state/*.json` snapshots back to `main`. The commit step is **concurrency-safe**: when runs
  overlap, it reconciles each snapshot by newest `last_run` (`tcg_watcher.reconcile`) and retries
  the push, so parallel runs never conflict or clobber one another's state.
- **Sealed-only, by design.** Individual singles are intentionally out of scope — they're not
  what you preorder/restock, and their catalogs (tens of thousands of cards) trip Cloudflare
  rate-limits. Fetching only sealed keeps each run to ~40 requests.

## Stores (28)

| Store | Fetch mode | Franchises |
|---|---|---|
| collectorsrow.cards | curated sealed collections | Pokémon |
| collectorstore.com | curated sealed collections | Pokémon, One Piece |
| hobbiesville.com | curated sealed collections | Pokémon, One Piece, Dragon Ball |
| deckoutgaming.ca | curated sealed collections | Pokémon, One Piece |
| skyboxct.com | curated sealed collections | Pokémon |
| store.401games.ca | curated sealed collections | Dragon Ball |
| thepokehive.com | full-crawl + sealed filter | all (small catalog) |
| allpoketcg.com | full-crawl + sealed filter | all (small catalog) |
| matrixtcg.com | full-crawl + sealed filter | all (small catalog) |
| rarecandy.com | Apollo GraphQL `RareFindCatalog` (full sealed catalog, paginated) | Pokémon, One Piece, Dragon Ball |
| 3kcollectables.com | full-crawl + sealed filter | all (small catalog) |
| paladincards20.com | full-crawl + sealed filter | all (small catalog) |
| shopchieffpokeman.com | full-crawl + sealed filter | all (small catalog) |
| spoilsandloot.com | full-crawl + sealed filter | all |
| shinypax.us | full-crawl + sealed filter | all (minimal sealed) |
| tygerstcgden.com | full-crawl + sealed filter | all (minimal sealed) |
| realgoodeal.com | curated sealed collections | Pokémon, One Piece |
| zulusgames.com | curated sealed collections | Pokémon |
| shop.tcgsorted.com | full-crawl + sealed filter | Pokémon (small) |
| doubleinfinitygaming.com | curated "new and hot" collections | Pokémon, One Piece, Dragon Ball |
| safari-zone.com | full-crawl + sealed filter | all (small catalog) |
| tcg-stadium.com | full-crawl + sealed filter | all (small catalog) |
| royalsakuratcg.com | full-crawl + sealed filter | all (small, JP-focused) |
| 763collectibles.com | full-crawl + sealed filter | all (sealed-focused, ~920 watched) |
| www.smokeandmirrorshobby.com | curated sealed collections | Pokémon (EN+JP), Dragon Ball |
| pkmncolosseum.com | curated sealed collections | Pokémon |
| pokelegendstcg.com | Wix storefront GraphQL (full catalog) | Pokémon |
| bulbacards.com | Wix storefront GraphQL (full catalog) | Pokémon |

Notes: **401games** exposes a clean Dragon Ball sealed collection; its Pokémon/One Piece sealed
aren't cleanly targetable (add handles to its config if found). **collectorstore.com** uses its
`games-pokemon` / `games-one-piece` collections (all sealed). **tcgsorted** (shop.app) is deferred (no resolvable
storefront). **rarecandy** (Next.js marketplace) shipped as the first non-Shopify adapter; the remaining Wix ×2 are Phase 2 (see `docs/superpowers/PHASE2_SCOPING.md`). Session-4 added **10 stores** from the store-list image: 7 full-crawl + 3 curated (**realgoodeal**, **zulusgames**, **doubleinfinitygaming** — big/singles-heavy, so curated to clean sealed collections; doubleinfinitygaming uses its sealed-only "new and hot" staging collections since its full catalog is graded-singles). **shop.tcgsorted.com** is the real storefront behind the `shop.app/m/tcgsorted` link (apex 404s). A second store-list image added 5 more (session 4): `safarizone`, `tcgstadium`, `royalsakuratcg`, `763collectibles` full-crawl + `smokeandmirrorshobby` curated (big graded/singles catalog; its `one-piece` collection was rejected for accessory contamination). Not added: **blowoutcards** (Magento behind an Imperva JS-challenge WAF — would need a headless browser), **missionreadycollectibles** (merchant password-locked storefront), **smokemon07** (live-rips/PSA-slab store, nothing trackable). A third store-list image (session 5) added **pkmncolosseum.com** (Dead Draw Gaming's Pokémon-only Shopify store — a large singles catalog, so curated to its clean `all-pokemon-sealed` + type-specific sealed collections); every other domain in that image was already tracked or previously ruled out. **Phase 2 completed (session 6):** `pokelegendstcg.com` + `bulbacards.com` via a shared **Wix Stores adapter** — mints a visitor token from `/_api/v1/access-tokens`, then pages the **full catalog** through the storefront GraphQL (`getFilteredProducts`, 100/page, page-capped; the SSR'd gallery only exposes ~16 items, so scraping HTML was rejected). Both are Pokémon-only stores whose titles rarely name the franchise (~80% would be missed by title matching), so a per-store `franchise` config field blanket-tags the catalog for the franchise filter. Deliberately **no accessory guard**: every accessory-flagged name on bulbacards (Binder Collection, Sleeved Boosters, Premium Playmat Collection) is an official sealed product line that a guard would wrongly drop. **rarecandy widened (session 7):** replaced the ~85-listing `/shop`+`/discover` `__NEXT_DATA__` scrape with the real Apollo endpoint `api.rarecandy.com/graphql` (`RareFindCatalog(page, filters)`), paginating `filters={categories:["sealed"], sortBy:"newest"}` — the full **~450 sealed listings** across all sellers (page-capped at 40; franchise filtered client-side to ~237 Pokémon/One Piece/Dragon Ball). The raw endpoint needs the exact `operationName` + non-null `$page: Int!`; multi-category filters OR rather than AND, so franchise scoping stays client-side.

## The Cloudflare 429 story (why it's built this way)

GitHub's datacenter IPs get rate-limited (HTTP 429) by Cloudflare when crawling large catalogs.
Two things keep us under the limit: **(1) sealed-only** fetching (~40 requests/run, not ~300+),
and **(2) a polite HTTP layer** — a minimum interval between requests (2.5s), honoring
`Retry-After`, and exponential-backoff retries. A full run takes ~2–3 min (mostly the throttle),
well under the 5-min cron.

## Setup (already done, for reference)

1. Two Discord channels with Incoming Webhooks (`#deals`, `#tracker`).
2. Repo secrets `DISCORD_DEALS_WEBHOOK` and `DISCORD_TRACKER_WEBHOOK` (`gh secret set ...`).
3. Public repo (free unlimited Actions minutes). First run seeds silently; alerts begin run 2.

## Notifications

- **#deals** (loud, `@here`): **restocks** and **preorder openings** — act-now events.
- **#tracker** (quiet): **new listings** and **price changes**.
- Set **#tracker** to *All Messages* in Discord if you want phone buzzes there too.

Each embed: product title, event type (color + emoji), store, price (previous → current with
▲/▼), franchise, image, and a tap-through Buy link.

## Event types

- **restock** — a sealed variant went out-of-stock → in-stock.
- **new listing** — a sealed variant never seen before (→ **preorder** if tagged/titled as one).
- **price change** — price moved beyond `price_epsilon` **and the variant is in stock**.
- A restock takes precedence over a simultaneous price change (one alert).

## Configuration (`config.toml`)

- **Curated store** — set `collections = ["<franchise>:<collection-handle>", ...]` (e.g.
  `"pokemon:pokemon-booster-boxes"`). Only those collections are fetched; products are trusted
  as sealed and tagged with the given franchise.
- **Full-crawl store** — omit `collections`; the whole catalog is fetched, then filtered to the
  franchise watchlist and to sealed products (`is_sealed` heuristic). Use only for small stores.
- **Add a store**: add a `[[stores]]` block (`platform = "shopify"`). Find sealed collection
  handles via `https://<store>/collections.json`. Disable with `enabled = false`.
- **Wix store** — `platform = "wix"` plus `franchise = "<franchise>"`. Wix products carry no
  usable tags, so the adapter blanket-tags the whole catalog with the declared franchise (use
  only for single-franchise stores); the sealed-title filter still applies. The full catalog is
  fetched via the Wix storefront GraphQL — no `collections` needed.
- **Franchises / thresholds**: `[franchise_synonyms]`, `max_events_per_store` (flood cap →
  one summary embed), `price_epsilon` (absolute floor), `price_change_pct` (minimum *relative*
  move to fire a price-change alert; default `0.05` = 5% — suppresses algorithmic $1–2 repricing
  drift on high-value boxes that would otherwise spam `#tracker`), `post_delay_seconds` (proactive
  pause between Discord posts to stay under webhook rate limits; default `1.0`, set `0` to disable).

## Local use

```bash
export DISCORD_DEALS_WEBHOOK=... DISCORD_TRACKER_WEBHOOK=...
uv run python -m tcg_watcher          # TCG_CONFIG (default config.toml), TCG_STATE_DIR (default state)
python scripts/spike_feeds.py         # reachability spike
uv run pytest -v                      # 161 tests
```

## Known limitations (Phase 1)

- Shopify reports **in/out of stock only**, not quantity.
- **GitHub cron is best-effort (~5–15 min)** — not for sub-minute drop sniping.
- Transient failures: the HTTP layer retries; a store still failing is isolated (logged, skipped)
  and retried next cycle.
- A **Discord post failure is fatal for that run** (fail-loud, non-idempotent): the failing
  store's snapshot isn't saved, so those events re-alert next run rather than being lost.
- Snapshot commits every ~5 min **grow repo history** over time (acceptable for Phase 1).
- **Phase 2** ✅ = non-Shopify sites (**rarecandy** Next.js; **Wix ×2** pokelegendstcg + bulbacards
  via storefront GraphQL). **Phase 3** = TCGplayer "below market" deal-flagging
  (via tcgcsv.com), which makes `#deals` below-market-only.

## Design docs

- Spec: `docs/superpowers/specs/2026-06-30-tcg-restock-watcher-design.md`
- Phase-1 plan: `docs/superpowers/plans/2026-06-30-tcg-restock-watcher-phase1.md`
