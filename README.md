# TCG Restock Watcher

Polls Shopify TCG stores every ~5 minutes for **Pokémon / One Piece / Dragon Ball**
inventory and price changes, and posts alerts to **Discord**. Runs entirely on free
GitHub Actions; state lives in this repo.

## How it works

```
per store: adapter (products.json) → franchise filter → diff vs last snapshot
        → classify events → Discord (loud/quiet) → commit new snapshot
```

- A GitHub Actions workflow (`.github/workflows/watch.yml`) runs `python -m tcg_watcher`
  every ~5 min and commits updated `state/*.json` snapshots back to `main` (free history +
  git-diff debugging).
- One adapter per store platform normalizes each catalog into a common product shape; the
  diff engine and notifier are store-agnostic.

## Stores (Phase 1 — 9 Shopify stores)

collectorsrow.cards · collectorstore.com · thepokehive.com · hobbiesville.com ·
deckoutgaming.ca · allpoketcg.com · skyboxct.com · matrixtcg.com · **store.401games.ca**

> Note: 401games' real storefront is `store.401games.ca` (the apex redirects there).
> `tcgsorted` (shop.app) could not be resolved to a working `/products.json` and is deferred
> to Phase 2, alongside the 3 non-Shopify sites (pokelegendstcg + bulbacards on Wix,
> rarecandy on Next.js).

## Setup

1. **Create two Discord channels** (e.g. `#deals` and `#tracker`) and add an **Incoming
   Webhook** to each: Channel → Edit → Integrations → Webhooks → New Webhook → Copy URL.
2. **Store the webhook URLs as repo secrets** (they are never committed):
   ```bash
   gh secret set DISCORD_DEALS_WEBHOOK      # paste the #deals webhook URL
   gh secret set DISCORD_TRACKER_WEBHOOK    # paste the #tracker webhook URL
   ```
3. The repo is **public** so Actions minutes are unlimited. No secrets live in the code.
4. The **first run seeds silently** (writes snapshots, sends nothing). Alerts begin on run 2.

## Notifications

- **#deals** (loud, `@here` ping): **restocks** and **preorder openings** — the act-now events.
- **#tracker** (quiet, no ping): **new listings** and **price changes**.
- Until Phase 3 (TCGplayer market-price deal-flagging) lands, set the **#tracker** channel to
  **All Messages** in Discord notification settings if you want a phone buzz on every change.

Each alert embed shows the product title, event type (color + emoji), store, price
(previous → current with ▲/▼ on price changes), franchise, image, and a tap-through Buy link.

## Event types

- **restock** — a watched variant went out-of-stock → in-stock.
- **new listing** — a variant never seen before (→ **preorder** if tagged/ titled as one).
- **price change** — price moved beyond `price_epsilon` **and the variant is currently in
  stock** (price changes on out-of-stock items are suppressed as noise).
- A restock takes precedence over a simultaneous price change (one alert, not two).

## Configuration

All in `config.toml`:

- **Add/remove a store** — edit a `[[stores]]` block. Phase 1 supports `platform = "shopify"`
  only. Disable a store with `enabled = false` (e.g. if it starts blocking GitHub's IPs).
- **Tune franchise matching** — edit `[franchise_synonyms]`. Matching checks tags →
  product_type → title (each tag individually). Some large general stores match big sets;
  tighten synonyms if a store is noisy.
- **Thresholds** — `max_events_per_store` (flood cap → one summary embed if exceeded),
  `price_epsilon`.

## Local use

```bash
# one real run (seeds on first run; needs webhook envs, even if unused on a seed run)
export DISCORD_DEALS_WEBHOOK=... DISCORD_TRACKER_WEBHOOK=...
uv run python -m tcg_watcher            # honors TCG_CONFIG (default config.toml), TCG_STATE_DIR (default state)

# check every feed is reachable (the landmine-#1 spike)
python scripts/spike_feeds.py

# tests
uv run pytest -v
```

## Known limitations (Phase 1)

- Shopify reports **in/out of stock only**, not quantity ("3 left").
- **GitHub cron is best-effort (~5–15 min)** — not for sub-minute drop sniping.
- **Transient 503s** from some stores are handled two ways: the HTTP layer retries transient
  503/429/timeouts, and if a store still fails, the run isolates it (logs + skips) and retries
  next cycle. A store failing one cycle is picked up the next.
- A **Discord post failure is fatal for that run** (fail-loud, non-idempotent): the failing
  store's snapshot isn't saved, so those events re-alert next run rather than being lost.
- Snapshot commits every ~5 min **grow repo history** over time (acceptable for Phase 1).
- **Phase 2** = the 3 non-Shopify sites. **Phase 3** = TCGplayer "below market" deal-flagging
  (loud `#deals` becomes below-market-only) via tcgcsv.com.

## Design docs

- Spec: `docs/superpowers/specs/2026-06-30-tcg-restock-watcher-design.md`
- Phase-1 plan: `docs/superpowers/plans/2026-06-30-tcg-restock-watcher-phase1.md`
