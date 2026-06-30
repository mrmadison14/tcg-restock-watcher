# TCG Restock Watcher — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 24/7 GitHub Actions watcher that polls 10 Shopify TCG stores for Pokémon/One Piece/Dragon Ball inventory and price changes, diffs against committed snapshots, and alerts to Discord.

**Architecture:** Per-store adapters normalize each catalog into a common `Product` shape; a pure diff engine compares the current list to the previous JSON snapshot and emits classified `Event`s; a notifier posts Discord embeds (loud vs quiet). State lives as JSON committed back to a public repo each run. A scheduled GitHub Actions workflow drives it every ~5 minutes.

**Tech Stack:** Python 3.13, `uv` (deps + runner), `httpx` (fetching), `tomllib` (stdlib config), `pytest` (tests). No DB, no web framework, no UI.

**Scope:** Phase 1 only (10 Shopify stores). Phase 2 (Wix/Next adapters) and Phase 3 (tcgcsv deal-flagging) are separate plans.

**Reference spec:** `docs/superpowers/specs/2026-06-30-tcg-restock-watcher-design.md`

---

## File Structure

```
tcg-restock-watcher/
├── pyproject.toml                      # uv project, py3.13, httpx + pytest
├── config.toml                         # store roster + franchise synonyms + thresholds
├── src/tcg_watcher/
│   ├── __init__.py
│   ├── models.py                       # Product, Event, EventType
│   ├── config.py                       # Store, Config, load_config()
│   ├── filtering.py                    # filter_franchises()
│   ├── state.py                        # load/build/save snapshot
│   ├── diff.py                         # detect_events()  (the heart)
│   ├── notify.py                       # build_embed(), route_loud(), send_events()
│   ├── runner.py                       # run_once() orchestration + RunReport
│   ├── http.py                         # make_httpx_get(), make_discord_poster()
│   ├── adapters/
│   │   ├── __init__.py
│   │   └── shopify.py                  # fetch_products()
│   └── __main__.py                     # CLI entrypoint: python -m tcg_watcher
├── scripts/
│   └── spike_feeds.py                  # Landmine #1 spike: probe all feeds, exit nonzero on block
├── state/                              # snapshot JSON, committed each run (created at runtime)
├── tests/
│   ├── test_models.py
│   ├── test_config.py
│   ├── test_shopify_adapter.py
│   ├── test_filtering.py
│   ├── test_state.py
│   ├── test_diff.py
│   ├── test_notify.py
│   └── test_runner.py
└── .github/workflows/
    ├── spike.yml                       # manual: run the feed spike on a GH runner
    └── watch.yml                       # scheduled: run watcher every 5 min, commit state
```

## Shared Interfaces (defined once, used by all tasks)

These signatures are the contract. Every task below conforms to them.

```python
# models.py
class EventType(str, Enum): RESTOCK; NEW_PRODUCT; PREORDER_OPEN; PRICE_CHANGE
Product(store, product_id, variant_id, title, price, currency, in_stock, url,
        image=None, product_type="", tags=(), is_preorder=False, is_sealed=False, franchise=None)  # frozen
Event(type, product, previous_price=None, previous_in_stock=None)  # frozen

# config.py
Store(key, base_url, platform, currency, enabled=True)  # frozen
Config(stores, franchise_synonyms, max_events_per_store, price_epsilon)  # frozen
load_config(path) -> Config

# adapters/shopify.py
fetch_products(store: Store, http_get) -> list[Product]

# filtering.py
filter_franchises(products: list[Product], synonyms: dict[str, tuple[str,...]]) -> list[Product]

# state.py
snapshot_path(state_dir, store_key) -> Path
load_snapshot(path) -> dict          # {"seeded": bool, "last_run": str|None, "variants": {vid: {...}}}
build_snapshot(products, now_iso) -> dict
save_snapshot(path, snapshot) -> None

# diff.py
detect_events(current: list[Product], previous: dict, epsilon: float = 0.01) -> list[Event]

# notify.py
build_embed(event: Event) -> dict
route_loud(event: Event) -> bool
send_events(events, post_loud, post_quiet, max_events_per_store, route=route_loud) -> int

# http.py
make_httpx_get() -> callable          # (url, params=None) -> dict
make_discord_poster(webhook_url) -> callable  # (payload: dict) -> None

# runner.py
RunReport(stores_ok, stores_failed, events_sent, seeded)
run_once(config, http_get, post_loud, post_quiet, state_dir, now_iso) -> RunReport
```

`http_get(url, params=None) -> dict` and the Discord `post(payload) -> None` callables are **injected** everywhere so tests never touch the network.

> **Phase-1 loud/quiet note (deviation from spec, flagged for approval):** the spec defines "loud" as *below TCGplayer market price*, which is a Phase-3 capability. To give Phase 1 a useful loud path, `route_loud()` routes **RESTOCK** and **PREORDER_OPEN** events to the loud (#deals) webhook, and **NEW_PRODUCT** / **PRICE_CHANGE** to the quiet (#tracker) webhook. Phase 3 will refine loud to additionally require below-market. If you'd rather Phase 1 send everything quiet (and rely on Discord's per-channel "All Messages" notification), say so and `route_loud` becomes `return False`.

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/tcg_watcher/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing smoke test**

`tests/test_smoke.py`:
```python
def test_package_imports():
    import tcg_watcher
    assert tcg_watcher.__version__ == "0.1.0"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tcg_watcher'` (uv may also report no project yet).

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "tcg-watcher"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["httpx>=0.27"]

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/tcg_watcher"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 4: Create the package init**

`src/tcg_watcher/__init__.py`:
```python
__version__ = "0.1.0"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: PASS (uv resolves the env on first run).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/tcg_watcher/__init__.py tests/test_smoke.py uv.lock
git commit -m "chore: scaffold tcg_watcher package with uv + pytest"
```

---

## Task 2: Cloudflare-from-Actions spike (Landmine #1 — GATES EVERYTHING)

This must pass before building the engine. It proves GitHub's datacenter IPs can read all 10 Shopify feeds (some Cloudflare configs block datacenter IPs — confirmed live on other stores during design).

**Files:**
- Create: `scripts/spike_feeds.py`
- Create: `.github/workflows/spike.yml`

- [ ] **Step 1: Write the spike script**

`scripts/spike_feeds.py`:
```python
import sys, json, urllib.request, urllib.error

FEEDS = [
    "https://collectorsrow.cards",
    "https://collectorstore.com",
    "https://thepokehive.com",
    "https://hobbiesville.com",
    "https://deckoutgaming.ca",
    "https://allpoketcg.com",
    "https://skyboxct.com",
    "https://matrixtcg.com",
    "https://401games.ca",
    # tcgsorted: resolve real domain in Step 4 before adding here
]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

def probe(base):
    url = f"{base}/products.json?limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
            n = len(json.loads(body).get("products", []))
            return (base, r.getcode(), f"ok products_parsed={n}")
    except urllib.error.HTTPError as e:
        return (base, e.code, f"HTTPError {e.reason}")
    except Exception as e:
        return (base, "ERR", f"{type(e).__name__}: {e}")

def main():
    rows = [probe(b) for b in FEEDS]
    blocked = []
    for base, code, note in rows:
        ok = code == 200 and note.startswith("ok")
        print(f"{'PASS' if ok else 'FAIL'}  {code!s:>5}  {base:30}  {note}")
        if not ok:
            blocked.append(base)
    if blocked:
        print(f"\nBLOCKED/UNREADABLE: {len(blocked)} -> {blocked}")
        sys.exit(1)
    print("\nAll feeds readable from this runner.")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the manual workflow**

`.github/workflows/spike.yml`:
```yaml
name: feed-spike
on:
  workflow_dispatch:
jobs:
  probe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: python scripts/spike_feeds.py
```

- [ ] **Step 3: Verify the script locally first**

Run: `python scripts/spike_feeds.py`
Expected: 9 `PASS` lines (your machine is not a datacenter IP, so this should pass; it sets the baseline).

- [ ] **Step 4: Resolve the tcgsorted real domain**

Run:
```bash
curl -s -L -A "Mozilla/5.0" "https://shop.app/m/tcgsorted" | grep -o -E 'https://[a-z0-9.-]+\.myshopify\.com' | sort -u | head
curl -s -o /dev/null -w "%{http_code}\n" -A "Mozilla/5.0" "https://tcgsorted.com/products.json?limit=1"
```
If a real storefront domain is found and returns `200`, add it to the `FEEDS` list and to `config.toml` in Task 4. If it cannot be resolved to a working `/products.json`, leave it out of Phase 1 and note it as a Phase 2 item — **do not block on it.**

- [ ] **Step 5: Create the GitHub repo (public) and push**

```bash
gh repo create tcg-restock-watcher --public --source=. --remote=origin --push
```
Expected: repo created, `main` pushed.

- [ ] **Step 6: Run the spike on a real runner and read the result**

```bash
gh workflow run feed-spike
sleep 20
gh run list --workflow=feed-spike --limit 1
gh run view --log | tail -40
```
Expected: job **succeeds** with all `PASS`. **If any feed FAILs from the runner**, stop and report which stores are blocked — mitigation is a proxy or the always-on-box fallback (Landmine #1). Disable blocked stores in `config.toml` so the rest still ship.

- [ ] **Step 7: Commit**

```bash
git add scripts/spike_feeds.py .github/workflows/spike.yml
git commit -m "test: add Cloudflare-from-Actions feed spike (landmine #1 gate)"
git push
```

---

## Task 3: Data models

**Files:**
- Create: `src/tcg_watcher/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from tcg_watcher.models import Product, Event, EventType

def test_product_is_frozen_and_hashable():
    p = Product(store="s", product_id="1", variant_id="11", title="ETB",
                price=59.99, currency="USD", in_stock=True, url="http://x/p")
    assert p.in_stock is True
    assert hash(p)  # frozen + tuple fields => hashable

def test_event_defaults():
    p = Product(store="s", product_id="1", variant_id="11", title="ETB",
                price=59.99, currency="USD", in_stock=True, url="http://x/p")
    e = Event(type=EventType.RESTOCK, product=p)
    assert e.type == "restock"
    assert e.previous_price is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tcg_watcher.models'`.

- [ ] **Step 3: Implement `models.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class EventType(str, Enum):
    RESTOCK = "restock"
    NEW_PRODUCT = "new_product"
    PREORDER_OPEN = "preorder_open"
    PRICE_CHANGE = "price_change"


@dataclass(frozen=True)
class Product:
    store: str
    product_id: str
    variant_id: str
    title: str
    price: float
    currency: str
    in_stock: bool
    url: str
    image: str | None = None
    product_type: str = ""
    tags: tuple[str, ...] = ()
    is_preorder: bool = False
    is_sealed: bool = False
    franchise: str | None = None


@dataclass(frozen=True)
class Event:
    type: EventType
    product: Product
    previous_price: float | None = None
    previous_in_stock: bool | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/models.py tests/test_models.py
git commit -m "feat: add Product/Event data models"
```

---

## Task 4: Config loader + config.toml

**Files:**
- Create: `src/tcg_watcher/config.py`
- Create: `config.toml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from pathlib import Path
from tcg_watcher.config import load_config

def test_load_config(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[[stores]]
key = "hobbiesville"
base_url = "https://hobbiesville.com"
platform = "shopify"
currency = "CAD"

[[stores]]
key = "disabled_store"
base_url = "https://x.com"
platform = "shopify"
currency = "USD"
enabled = false

[franchise_synonyms]
pokemon = ["pokemon", "pokémon"]
"one piece" = ["one piece"]

[thresholds]
max_events_per_store = 25
price_epsilon = 0.01
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    keys = [s.key for s in cfg.stores]
    assert keys == ["hobbiesville", "disabled_store"]
    assert cfg.stores[0].currency == "CAD"
    assert cfg.stores[1].enabled is False
    assert cfg.franchise_synonyms["pokemon"] == ("pokemon", "pokémon")
    assert cfg.max_events_per_store == 25
    assert cfg.price_epsilon == 0.01
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tcg_watcher.config'`.

- [ ] **Step 3: Implement `config.py`**

```python
from __future__ import annotations
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Store:
    key: str
    base_url: str
    platform: str
    currency: str
    enabled: bool = True


@dataclass(frozen=True)
class Config:
    stores: tuple[Store, ...]
    franchise_synonyms: dict[str, tuple[str, ...]]
    max_events_per_store: int
    price_epsilon: float


def load_config(path: Path) -> Config:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    stores = tuple(
        Store(
            key=s["key"],
            base_url=s["base_url"].rstrip("/"),
            platform=s["platform"],
            currency=s["currency"],
            enabled=s.get("enabled", True),
        )
        for s in data["stores"]
    )
    synonyms = {k: tuple(v) for k, v in data["franchise_synonyms"].items()}
    thresholds = data["thresholds"]
    return Config(
        stores=stores,
        franchise_synonyms=synonyms,
        max_events_per_store=thresholds["max_events_per_store"],
        price_epsilon=thresholds["price_epsilon"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Create the real `config.toml`**

`config.toml` (the 10-store Phase-1 roster; add tcgsorted here only if Task 2 Step 4 resolved it):
```toml
[[stores]]
key = "collectorsrow"
base_url = "https://collectorsrow.cards"
platform = "shopify"
currency = "USD"

[[stores]]
key = "collectorstore"
base_url = "https://collectorstore.com"
platform = "shopify"
currency = "USD"

[[stores]]
key = "thepokehive"
base_url = "https://thepokehive.com"
platform = "shopify"
currency = "USD"

[[stores]]
key = "hobbiesville"
base_url = "https://hobbiesville.com"
platform = "shopify"
currency = "CAD"

[[stores]]
key = "deckoutgaming"
base_url = "https://deckoutgaming.ca"
platform = "shopify"
currency = "CAD"

[[stores]]
key = "allpoketcg"
base_url = "https://allpoketcg.com"
platform = "shopify"
currency = "USD"

[[stores]]
key = "skyboxct"
base_url = "https://skyboxct.com"
platform = "shopify"
currency = "USD"

[[stores]]
key = "matrixtcg"
base_url = "https://matrixtcg.com"
platform = "shopify"
currency = "USD"

[[stores]]
key = "401games"
base_url = "https://401games.ca"
platform = "shopify"
currency = "CAD"

[franchise_synonyms]
pokemon = ["pokemon", "pokémon"]
"one piece" = ["one piece", "one-piece"]
"dragon ball" = ["dragon ball", "dragon ball super", "dragonball", "fusion world"]

[thresholds]
max_events_per_store = 25
price_epsilon = 0.01
```

- [ ] **Step 6: Verify the real config loads**

Run: `uv run python -c "from tcg_watcher.config import load_config; c=load_config('config.toml'); print(len(c.stores),'stores', [s.key for s in c.stores])"`
Expected: prints `9 stores [...]` (or 10 if tcgsorted resolved).

- [ ] **Step 7: Commit**

```bash
git add src/tcg_watcher/config.py config.toml tests/test_config.py
git commit -m "feat: add TOML config loader and 10-store roster"
```

---

## Task 5: Shopify adapter

**Files:**
- Create: `src/tcg_watcher/adapters/__init__.py`
- Create: `src/tcg_watcher/adapters/shopify.py`
- Test: `tests/test_shopify_adapter.py`

- [ ] **Step 1: Write the failing test**

`tests/test_shopify_adapter.py`:
```python
from tcg_watcher.config import Store
from tcg_watcher.adapters.shopify import fetch_products

STORE = Store(key="demo", base_url="https://demo.test", platform="shopify", currency="USD")

PAGE1 = {
    "products": [
        {
            "id": 100, "handle": "surging-sparks-etb", "title": "Surging Sparks Elite Trainer Box",
            "product_type": "Sealed Pokemon", "tags": ["Pokemon", "Preorder"],
            "images": [{"src": "https://img/etb.jpg"}],
            "variants": [
                {"id": 9001, "title": "Default Title", "price": "59.99", "available": False},
            ],
        },
        {
            "id": 101, "handle": "op-romance-dawn-bb", "title": "One Piece Romance Dawn Booster Box",
            "product_type": "Sealed", "tags": ["One Piece"], "images": [],
            "variants": [
                {"id": 9002, "title": "English", "price": "120.00", "available": True},
                {"id": 9003, "title": "Japanese", "price": "95.00", "available": True},
            ],
        },
    ]
}

def make_http_get(pages):
    def http_get(url, params=None):
        page = (params or {}).get("page", 1)
        return pages.get(page, {"products": []})
    return http_get

def test_fetch_maps_variants_and_flags():
    http_get = make_http_get({1: PAGE1})
    products = fetch_products(STORE, http_get)
    assert len(products) == 3  # 1 + 2 variants
    etb = products[0]
    assert etb.store == "demo"
    assert etb.variant_id == "9001"
    assert etb.price == 59.99
    assert etb.in_stock is False
    assert etb.url == "https://demo.test/products/surging-sparks-etb"
    assert etb.image == "https://img/etb.jpg"
    assert etb.is_preorder is True          # "Preorder" tag
    assert etb.is_sealed is True            # "Elite Trainer Box" in title
    assert "Pokemon" in etb.tags
    # variant title appended when not "Default Title"
    jp = products[2]
    assert jp.title.endswith("Japanese")
    assert jp.image is None

def test_pagination_stops_on_empty():
    http_get = make_http_get({1: PAGE1, 2: {"products": []}})
    products = fetch_products(STORE, http_get)
    assert len(products) == 3
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_shopify_adapter.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `adapters/__init__.py` (empty) and implement `shopify.py`**

`src/tcg_watcher/adapters/__init__.py`:
```python
```

`src/tcg_watcher/adapters/shopify.py`:
```python
from __future__ import annotations
from ..config import Store
from ..models import Product

_SEALED_MARKERS = (
    "booster box", "elite trainer", "etb", "booster bundle", "bundle",
    "collection", "case", "tin", "blister", "booster pack",
)
_PREORDER_MARKERS = ("preorder", "pre-order", "pre order")
_PAGE_LIMIT = 250
_MAX_PAGES = 50


def _has_marker(text: str, markers: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(m in low for m in markers)


def _is_preorder(title: str, tags: tuple[str, ...]) -> bool:
    blob = title + " " + " ".join(tags)
    return _has_marker(blob, _PREORDER_MARKERS)


def fetch_products(store: Store, http_get) -> list[Product]:
    out: list[Product] = []
    page = 1
    while page <= _MAX_PAGES:
        data = http_get(
            f"{store.base_url}/products.json",
            params={"limit": _PAGE_LIMIT, "page": page},
        )
        items = data.get("products", [])
        if not items:
            break
        for it in items:
            handle = it.get("handle", "")
            url = f"{store.base_url}/products/{handle}"
            images = it.get("images") or []
            image = images[0].get("src") if images else None
            tags_raw = it.get("tags", [])
            tags = tuple(tags_raw) if isinstance(tags_raw, list) else tuple(
                t.strip() for t in str(tags_raw).split(",") if t.strip()
            )
            base_title = it.get("title", "")
            product_type = it.get("product_type", "") or ""
            preorder = _is_preorder(base_title, tags)
            sealed = _has_marker(base_title + " " + product_type, _SEALED_MARKERS)
            for v in it.get("variants", []):
                vtitle = v.get("title")
                title = base_title if vtitle in (None, "Default Title") else f"{base_title} - {vtitle}"
                out.append(
                    Product(
                        store=store.key,
                        product_id=str(it.get("id")),
                        variant_id=str(v.get("id")),
                        title=title,
                        price=float(v.get("price")),
                        currency=store.currency,
                        in_stock=bool(v.get("available")),
                        url=url,
                        image=image,
                        product_type=product_type,
                        tags=tags,
                        is_preorder=preorder,
                        is_sealed=sealed,
                    )
                )
        page += 1
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_shopify_adapter.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/adapters tests/test_shopify_adapter.py
git commit -m "feat: add Shopify products.json adapter"
```

---

## Task 6: Franchise filter

**Files:**
- Create: `src/tcg_watcher/filtering.py`
- Test: `tests/test_filtering.py`

- [ ] **Step 1: Write the failing test**

`tests/test_filtering.py`:
```python
from tcg_watcher.models import Product
from tcg_watcher.filtering import filter_franchises

SYN = {
    "pokemon": ("pokemon", "pokémon"),
    "one piece": ("one piece",),
    "dragon ball": ("dragon ball", "fusion world"),
}

def mk(title, tags=(), product_type=""):
    return Product(store="s", product_id="1", variant_id="v", title=title, price=1.0,
                   currency="USD", in_stock=True, url="u", tags=tags, product_type=product_type)

def test_matches_by_tag_then_title():
    prods = [
        mk("Surging Sparks ETB", tags=("Pokemon",)),       # tag match
        mk("Romance Dawn Booster Box", product_type="One Piece"),  # product_type match
        mk("Fusion World Starter Deck"),                   # title match -> dragon ball
        mk("Lorcana Chapter 5 Booster"),                   # no match -> dropped
    ]
    out = filter_franchises(prods, SYN)
    assert [p.franchise for p in out] == ["pokemon", "one piece", "dragon ball"]
    assert len(out) == 3

def test_franchise_set_on_returned_products():
    out = filter_franchises([mk("Pokemon Booster Bundle")], SYN)
    assert out[0].franchise == "pokemon"
    assert out[0].title == "Pokemon Booster Bundle"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_filtering.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `filtering.py`**

```python
from __future__ import annotations
from dataclasses import replace
from .models import Product


def _match(product: Product, synonyms: dict[str, tuple[str, ...]]) -> str | None:
    haystacks = [
        " ".join(product.tags).lower(),
        product.product_type.lower(),
        product.title.lower(),
    ]
    for source in haystacks:
        for franchise, syns in synonyms.items():
            if any(s in source for s in syns):
                return franchise
    return None


def filter_franchises(
    products: list[Product], synonyms: dict[str, tuple[str, ...]]
) -> list[Product]:
    out: list[Product] = []
    for p in products:
        fr = _match(p, synonyms)
        if fr is not None:
            out.append(replace(p, franchise=fr))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_filtering.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/filtering.py tests/test_filtering.py
git commit -m "feat: add franchise watchlist filter (tags/type/title)"
```

---

## Task 7: State (load / build / save snapshot)

**Files:**
- Create: `src/tcg_watcher/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write the failing test**

`tests/test_state.py`:
```python
from pathlib import Path
from tcg_watcher.models import Product
from tcg_watcher.state import snapshot_path, load_snapshot, build_snapshot, save_snapshot

def mk(vid, price, in_stock, title="ETB", preorder=False):
    return Product(store="s", product_id="1", variant_id=vid, title=title, price=price,
                   currency="USD", in_stock=in_stock, url="u", is_preorder=preorder)

def test_load_missing_returns_unseeded(tmp_path: Path):
    snap = load_snapshot(tmp_path / "nope.json")
    assert snap == {"seeded": False, "last_run": None, "variants": {}}

def test_build_and_roundtrip(tmp_path: Path):
    products = [mk("v1", 10.0, True), mk("v2", 20.0, False, preorder=True)]
    snap = build_snapshot(products, now_iso="2026-06-30T00:00:00Z")
    assert snap["seeded"] is True
    assert snap["last_run"] == "2026-06-30T00:00:00Z"
    assert snap["variants"]["v1"] == {"price": 10.0, "in_stock": True, "title": "ETB", "is_preorder": False}
    assert snap["variants"]["v2"]["is_preorder"] is True

    p = snapshot_path(tmp_path, "mystore")
    save_snapshot(p, snap)
    assert p.name == "mystore.json"
    reloaded = load_snapshot(p)
    assert reloaded == snap
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `state.py`**

```python
from __future__ import annotations
import json
from pathlib import Path
from .models import Product


def snapshot_path(state_dir: Path, store_key: str) -> Path:
    return Path(state_dir) / f"{store_key}.json"


def load_snapshot(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {"seeded": False, "last_run": None, "variants": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def build_snapshot(products: list[Product], now_iso: str) -> dict:
    variants = {
        p.variant_id: {
            "price": p.price,
            "in_stock": p.in_stock,
            "title": p.title,
            "is_preorder": p.is_preorder,
        }
        for p in products
    }
    return {"seeded": True, "last_run": now_iso, "variants": variants}


def save_snapshot(path: Path, snapshot: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/state.py tests/test_state.py
git commit -m "feat: add snapshot state load/build/save"
```

---

## Task 8: Diff engine (the heart)

**Files:**
- Create: `src/tcg_watcher/diff.py`
- Test: `tests/test_diff.py`

Detection rules (from spec §8): seed-first returns no events; new variant → NEW_PRODUCT (or PREORDER_OPEN if preorder); out→in → RESTOCK (or PREORDER_OPEN if preorder) and **restock takes precedence over price_change** for the same variant in one run; price delta beyond epsilon on an in-both variant → PRICE_CHANGE.

- [ ] **Step 1: Write the failing test**

`tests/test_diff.py`:
```python
from tcg_watcher.models import Product, EventType
from tcg_watcher.diff import detect_events

def mk(vid, price, in_stock, preorder=False):
    return Product(store="s", product_id="1", variant_id=vid, title="T", price=price,
                   currency="USD", in_stock=in_stock, url="u", is_preorder=preorder)

def snap(variants, seeded=True):
    return {"seeded": seeded, "last_run": "x", "variants": variants}

def test_unseeded_emits_nothing():
    events = detect_events([mk("v1", 10.0, True)], snap({}, seeded=False))
    assert events == []

def test_new_product_and_preorder():
    prev = snap({})
    events = detect_events([mk("v1", 10.0, True), mk("v2", 20.0, True, preorder=True)], prev)
    types = {e.product.variant_id: e.type for e in events}
    assert types["v1"] == EventType.NEW_PRODUCT
    assert types["v2"] == EventType.PREORDER_OPEN

def test_restock_out_to_in():
    prev = snap({"v1": {"price": 10.0, "in_stock": False, "title": "T", "is_preorder": False}})
    events = detect_events([mk("v1", 10.0, True)], prev)
    assert len(events) == 1
    assert events[0].type == EventType.RESTOCK
    assert events[0].previous_in_stock is False

def test_restock_takes_precedence_over_price_change():
    prev = snap({"v1": {"price": 8.0, "in_stock": False, "title": "T", "is_preorder": False}})
    events = detect_events([mk("v1", 10.0, True)], prev)  # both restocked AND price changed
    assert [e.type for e in events] == [EventType.RESTOCK]  # only one event

def test_price_change_when_already_in_stock():
    prev = snap({"v1": {"price": 10.0, "in_stock": True, "title": "T", "is_preorder": False}})
    events = detect_events([mk("v1", 12.5, True)], prev)
    assert len(events) == 1
    assert events[0].type == EventType.PRICE_CHANGE
    assert events[0].previous_price == 10.0

def test_no_event_within_epsilon():
    prev = snap({"v1": {"price": 10.00, "in_stock": True, "title": "T", "is_preorder": False}})
    events = detect_events([mk("v1", 10.005, True)], prev, epsilon=0.01)
    assert events == []

def test_disappearance_emits_nothing():
    prev = snap({"v1": {"price": 10.0, "in_stock": True, "title": "T", "is_preorder": False}})
    events = detect_events([], prev)  # product gone
    assert events == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_diff.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `diff.py`**

```python
from __future__ import annotations
from .models import Product, Event, EventType


def detect_events(
    current: list[Product], previous: dict, epsilon: float = 0.01
) -> list[Event]:
    if not previous.get("seeded"):
        return []

    prev_variants = previous.get("variants", {})
    events: list[Event] = []

    for p in current:
        old = prev_variants.get(p.variant_id)

        if old is None:
            etype = EventType.PREORDER_OPEN if p.is_preorder else EventType.NEW_PRODUCT
            events.append(Event(type=etype, product=p))
            continue

        restocked = (not old["in_stock"]) and p.in_stock
        if restocked:
            etype = EventType.PREORDER_OPEN if p.is_preorder else EventType.RESTOCK
            events.append(
                Event(
                    type=etype,
                    product=p,
                    previous_in_stock=False,
                    previous_price=old["price"],
                )
            )
            continue  # restock alert already conveys the current price

        if abs(p.price - old["price"]) > epsilon:
            events.append(
                Event(
                    type=EventType.PRICE_CHANGE,
                    product=p,
                    previous_price=old["price"],
                    previous_in_stock=old["in_stock"],
                )
            )

    return events
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_diff.py -v`
Expected: PASS (all 7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/diff.py tests/test_diff.py
git commit -m "feat: add snapshot diff engine with event classification"
```

---

## Task 9: Notifier (Discord embeds, loud/quiet, flood cap)

**Files:**
- Create: `src/tcg_watcher/notify.py`
- Test: `tests/test_notify.py`

- [ ] **Step 1: Write the failing test**

`tests/test_notify.py`:
```python
from tcg_watcher.models import Product, Event, EventType
from tcg_watcher.notify import build_embed, route_loud, send_events

def mk_event(etype, store="hobbiesville", vid="v1", price=59.99, prev_price=None, prev_in=None):
    p = Product(store=store, product_id="1", variant_id=vid, title="Surging Sparks ETB",
                price=price, currency="USD", in_stock=True, url="https://x/p",
                image="https://img/x.jpg", franchise="pokemon")
    return Event(type=etype, product=p, previous_price=prev_price, previous_in_stock=prev_in)

def test_build_embed_has_core_fields():
    emb = build_embed(mk_event(EventType.RESTOCK, prev_in=False))
    assert emb["title"].startswith("Surging Sparks")
    assert emb["url"] == "https://x/p"
    assert emb["image"]["url"] == "https://img/x.jpg"
    blob = str(emb)
    assert "hobbiesville" in blob and "restock" in blob.lower() and "59.99" in blob

def test_price_change_shows_previous():
    emb = build_embed(mk_event(EventType.PRICE_CHANGE, price=49.99, prev_price=59.99))
    assert "59.99" in str(emb) and "49.99" in str(emb)

def test_route_loud_for_restock_and_preorder():
    assert route_loud(mk_event(EventType.RESTOCK)) is True
    assert route_loud(mk_event(EventType.PREORDER_OPEN)) is True
    assert route_loud(mk_event(EventType.NEW_PRODUCT)) is False
    assert route_loud(mk_event(EventType.PRICE_CHANGE)) is False

def test_send_events_routes_and_counts():
    loud, quiet = [], []
    events = [mk_event(EventType.RESTOCK), mk_event(EventType.PRICE_CHANGE, vid="v2")]
    sent = send_events(events, loud.append, quiet.append, max_events_per_store=25)
    assert sent == 2
    assert len(loud) == 1 and len(quiet) == 1
    assert loud[0]["embeds"][0]["title"].startswith("Surging Sparks")

def test_flood_cap_collapses_to_summary():
    loud, quiet = [], []
    events = [mk_event(EventType.NEW_PRODUCT, vid=f"v{i}") for i in range(30)]
    sent = send_events(events, loud.append, quiet.append, max_events_per_store=25)
    assert sent == 1                       # collapsed
    assert len(quiet) == 1                 # summary goes quiet
    assert "30" in quiet[0]["content"]     # mentions the count
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_notify.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `notify.py`**

```python
from __future__ import annotations
from collections import defaultdict
from .models import Event, EventType

_LOUD_TYPES = {EventType.RESTOCK, EventType.PREORDER_OPEN}
_COLOR = {
    EventType.RESTOCK: 0x2ECC71,
    EventType.PREORDER_OPEN: 0x3498DB,
    EventType.NEW_PRODUCT: 0x9B59B6,
    EventType.PRICE_CHANGE: 0xF1C40F,
}
_LABEL = {
    EventType.RESTOCK: "🟢 RESTOCK",
    EventType.PREORDER_OPEN: "🔵 PREORDER OPEN",
    EventType.NEW_PRODUCT: "🟣 NEW LISTING",
    EventType.PRICE_CHANGE: "🟡 PRICE CHANGE",
}


def route_loud(event: Event) -> bool:
    return event.type in _LOUD_TYPES


def build_embed(event: Event) -> dict:
    p = event.product
    cur = f"{p.currency} {p.price:.2f}"
    if event.type == EventType.PRICE_CHANGE and event.previous_price is not None:
        arrow = "▲" if p.price > event.previous_price else "▼"
        price_line = f"{p.currency} {event.previous_price:.2f} → {cur} {arrow}"
    else:
        price_line = cur
    fields = [
        {"name": "Store", "value": p.store, "inline": True},
        {"name": "Price", "value": price_line, "inline": True},
        {"name": "Franchise", "value": p.franchise or "—", "inline": True},
    ]
    embed = {
        "title": f"{_LABEL[event.type]} — {p.title}"[:256],
        "url": p.url,
        "color": _COLOR[event.type],
        "fields": fields,
    }
    if p.image:
        embed["image"] = {"url": p.image}
    return embed


def _payload(embed: dict, loud: bool) -> dict:
    payload = {"embeds": [embed]}
    if loud:
        payload["content"] = "@here"
        payload["allowed_mentions"] = {"parse": ["everyone"]}
    return payload


def send_events(events, post_loud, post_quiet, max_events_per_store, route=route_loud) -> int:
    by_store: dict[str, list[Event]] = defaultdict(list)
    for e in events:
        by_store[e.product.store].append(e)

    sent = 0
    for store, store_events in by_store.items():
        if len(store_events) > max_events_per_store:
            summary = {
                "content": f"📦 **{store}**: {len(store_events)} changes this run "
                           f"(flood cap {max_events_per_store} exceeded — summarized).",
            }
            post_quiet(summary)
            sent += 1
            continue
        for e in store_events:
            embed = build_embed(e)
            loud = route(e)
            payload = _payload(embed, loud)
            (post_loud if loud else post_quiet)(payload)
            sent += 1
    return sent
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_notify.py -v`
Expected: PASS (all 5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/notify.py tests/test_notify.py
git commit -m "feat: add Discord notifier with loud/quiet routing and flood cap"
```

---

## Task 10: HTTP helpers + Runner orchestration

**Files:**
- Create: `src/tcg_watcher/http.py`
- Create: `src/tcg_watcher/runner.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write the failing test**

`tests/test_runner.py`:
```python
from pathlib import Path
from tcg_watcher.config import Config, Store
from tcg_watcher.runner import run_once
from tcg_watcher.state import load_snapshot, snapshot_path

SYN = {"pokemon": ("pokemon",)}

def cfg(*stores):
    return Config(stores=tuple(stores), franchise_synonyms=SYN,
                  max_events_per_store=25, price_epsilon=0.01)

def shopify_page(available):
    return {"products": [{
        "id": 1, "handle": "h", "title": "Pokemon Surging Sparks ETB",
        "product_type": "Sealed", "tags": ["Pokemon"], "images": [{"src": "i"}],
        "variants": [{"id": 50, "title": "Default Title", "price": "59.99", "available": available}],
    }]}

def make_http_get(pages_by_host):
    def http_get(url, params=None):
        page = (params or {}).get("page", 1)
        if page != 1:
            return {"products": []}
        for host, payload in pages_by_host.items():
            if host in url:
                return payload
        return {"products": []}
    return http_get

def test_first_run_seeds_silently(tmp_path: Path):
    store = Store(key="demo", base_url="https://demo.test", platform="shopify", currency="USD")
    http_get = make_http_get({"demo.test": shopify_page(available=False)})
    loud, quiet = [], []
    report = run_once(cfg(store), http_get, loud.append, quiet.append, tmp_path, "2026-06-30T00:00:00Z")
    assert report.events_sent == 0
    assert "demo" in report.seeded
    assert loud == [] and quiet == []
    assert load_snapshot(snapshot_path(tmp_path, "demo"))["seeded"] is True

def test_second_run_detects_restock(tmp_path: Path):
    store = Store(key="demo", base_url="https://demo.test", platform="shopify", currency="USD")
    # seed (out of stock)
    run_once(cfg(store), make_http_get({"demo.test": shopify_page(False)}),
             (lambda x: None), (lambda x: None), tmp_path, "t0")
    # second run (in stock) -> restock -> loud
    loud, quiet = [], []
    report = run_once(cfg(store), make_http_get({"demo.test": shopify_page(True)}),
                      loud.append, quiet.append, tmp_path, "t1")
    assert report.events_sent == 1
    assert len(loud) == 1

def test_adapter_failure_isolated(tmp_path: Path):
    good = Store(key="good", base_url="https://good.test", platform="shopify", currency="USD")
    bad = Store(key="bad", base_url="https://bad.test", platform="shopify", currency="USD")
    def http_get(url, params=None):
        if "bad.test" in url:
            raise RuntimeError("boom")
        if (params or {}).get("page", 1) != 1:
            return {"products": []}
        return shopify_page(True)
    report = run_once(cfg(good, bad), http_get, (lambda x: None), (lambda x: None), tmp_path, "t0")
    assert report.stores_ok == 1
    assert report.stores_failed == 1   # bad failed, good still processed (seeded)

def test_disabled_store_skipped(tmp_path: Path):
    store = Store(key="off", base_url="https://off.test", platform="shopify", currency="USD", enabled=False)
    report = run_once(cfg(store), make_http_get({}), (lambda x: None), (lambda x: None), tmp_path, "t0")
    assert report.stores_ok == 0 and report.stores_failed == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_runner.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `http.py`**

```python
from __future__ import annotations
import httpx

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def make_httpx_get():
    client = httpx.Client(timeout=20.0, headers={"User-Agent": _UA}, follow_redirects=True)

    def get(url, params=None):
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    return get


def make_discord_poster(webhook_url: str):
    client = httpx.Client(timeout=20.0)

    def post(payload: dict) -> None:
        resp = client.post(webhook_url, json=payload)
        resp.raise_for_status()

    return post
```

- [ ] **Step 4: Implement `runner.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .adapters import shopify
from .filtering import filter_franchises
from .state import load_snapshot, build_snapshot, save_snapshot, snapshot_path
from .diff import detect_events
from .notify import send_events

_ADAPTERS = {"shopify": shopify.fetch_products}


@dataclass
class RunReport:
    stores_ok: int = 0
    stores_failed: int = 0
    events_sent: int = 0
    seeded: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"ok={self.stores_ok} failed={self.stores_failed} "
            f"events_sent={self.events_sent} seeded={self.seeded}"
        )


def run_once(config: Config, http_get, post_loud, post_quiet, state_dir, now_iso) -> RunReport:
    report = RunReport()
    state_dir = Path(state_dir)

    for store in config.stores:
        if not store.enabled:
            continue
        adapter = _ADAPTERS.get(store.platform)
        if adapter is None:
            report.stores_failed += 1
            print(f"[{store.key}] no adapter for platform={store.platform}")
            continue
        try:
            products = adapter(store, http_get)
        except Exception as exc:  # adapter isolation: one store never breaks the run
            report.stores_failed += 1
            print(f"[{store.key}] adapter failed: {type(exc).__name__}: {exc}")
            continue

        watched = filter_franchises(products, config.franchise_synonyms)
        prev = load_snapshot(snapshot_path(state_dir, store.key))

        if not prev.get("seeded"):
            save_snapshot(snapshot_path(state_dir, store.key), build_snapshot(watched, now_iso))
            report.seeded.append(store.key)
            report.stores_ok += 1
            print(f"[{store.key}] seeded {len(watched)} watched variants (no alerts)")
            continue

        events = detect_events(watched, prev, config.price_epsilon)
        report.events_sent += send_events(
            events, post_loud, post_quiet, config.max_events_per_store
        )
        save_snapshot(snapshot_path(state_dir, store.key), build_snapshot(watched, now_iso))
        report.stores_ok += 1
        print(f"[{store.key}] {len(watched)} watched, {len(events)} events")

    return report
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_runner.py -v`
Expected: PASS (all 4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/tcg_watcher/http.py src/tcg_watcher/runner.py tests/test_runner.py
git commit -m "feat: add httpx helpers and run_once orchestration with adapter isolation"
```

---

## Task 11: CLI entrypoint

**Files:**
- Create: `src/tcg_watcher/__main__.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_runner.py`:
```python
def test_now_iso_helper_format():
    from tcg_watcher.__main__ import now_iso
    s = now_iso()
    assert s.endswith("Z") and "T" in s and len(s) == 20  # YYYY-MM-DDTHH:MM:SSZ
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_runner.py::test_now_iso_helper_format -v`
Expected: FAIL — `ModuleNotFoundError` / no `now_iso`.

- [ ] **Step 3: Implement `__main__.py`**

```python
from __future__ import annotations
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config
from .http import make_httpx_get, make_discord_poster
from .runner import run_once


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    config = load_config(os.environ.get("TCG_CONFIG", "config.toml"))
    http_get = make_httpx_get()

    deals_url = os.environ["DISCORD_DEALS_WEBHOOK"]
    tracker_url = os.environ["DISCORD_TRACKER_WEBHOOK"]
    post_loud = make_discord_poster(deals_url)
    post_quiet = make_discord_poster(tracker_url)

    state_dir = Path(os.environ.get("TCG_STATE_DIR", "state"))
    report = run_once(config, http_get, post_loud, post_quiet, state_dir, now_iso())
    print("RUN:", report.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runner.py::test_now_iso_helper_format -v`
Expected: PASS.

- [ ] **Step 5: Full suite green**

Run: `uv run pytest -v`
Expected: ALL tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tcg_watcher/__main__.py tests/test_runner.py
git commit -m "feat: add python -m tcg_watcher CLI entrypoint"
```

---

## Task 12: Production GitHub Actions workflow

**Files:**
- Create: `.github/workflows/watch.yml`
- Create: `.gitignore` entry for local state (optional)

- [ ] **Step 1: Write the workflow**

`.github/workflows/watch.yml`:
```yaml
name: watch
on:
  schedule:
    - cron: "*/5 * * * *"
  workflow_dispatch:

concurrency:
  group: tcg-watch
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  watch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - name: Run watcher
        env:
          DISCORD_DEALS_WEBHOOK: ${{ secrets.DISCORD_DEALS_WEBHOOK }}
          DISCORD_TRACKER_WEBHOOK: ${{ secrets.DISCORD_TRACKER_WEBHOOK }}
        run: uv run python -m tcg_watcher
      - name: Commit state
        run: |
          git config user.name "tcg-watcher-bot"
          git config user.email "actions@users.noreply.github.com"
          git add state/
          if git diff --staged --quiet; then
            echo "no state changes"
          else
            git commit -m "state: update snapshots [skip ci]"
            git pull --rebase origin main
            git push
          fi
```

- [ ] **Step 2: Set the Discord secrets**

Create two Discord channels (#deals, #tracker), add an Incoming Webhook to each (Channel → Edit → Integrations → Webhooks → New Webhook → Copy URL), then:
```bash
gh secret set DISCORD_DEALS_WEBHOOK    # paste the #deals webhook URL
gh secret set DISCORD_TRACKER_WEBHOOK  # paste the #tracker webhook URL
```

- [ ] **Step 3: Commit and push**

```bash
git add .github/workflows/watch.yml
git commit -m "ci: add scheduled watcher workflow (5-min cron, commit state back)"
git push
```

- [ ] **Step 4: First production run = silent seed (verify)**

```bash
gh workflow run watch
sleep 30
gh run view --log | tail -30
```
Expected: log shows each store `seeded ... (no alerts)`; a `state: update snapshots` commit appears on `main`. **No Discord messages yet** (seed-first). Confirm `state/*.json` exist in the repo.

- [ ] **Step 5: Second run = live alerts (verify)**

Wait for the next scheduled run (or `gh workflow run watch` again after ~5 min). Expected: any real restock/new/preorder/price change posts to the matching Discord channel. Confirm at least the run completes green and state commits update.

- [ ] **Step 6: Commit (if any tweaks)**

```bash
git add -A && git commit -m "ci: tweaks from first live runs" && git push  # only if needed
```

---

## Task 13: README + operations doc

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# TCG Restock Watcher

Polls Shopify TCG stores every ~5 min for Pokémon / One Piece / Dragon Ball
inventory and price changes, and posts alerts to Discord.

## How it works
Per-store adapter → franchise filter → diff vs committed snapshot → Discord.
State is JSON committed to this repo each run (free history; runs on GitHub Actions).

## Setup
1. Create two Discord channels (`#deals`, `#tracker`) and an Incoming Webhook in each.
2. `gh secret set DISCORD_DEALS_WEBHOOK` and `gh secret set DISCORD_TRACKER_WEBHOOK`.
3. Push to a **public** repo (free unlimited Actions minutes).
4. First scheduled run seeds silently (no alerts). Alerts begin on run 2.

## Notifications
- **#deals** (loud, @here): restocks and preorder openings.
- **#tracker** (quiet): new listings and price changes.
- Until Phase 3 (market-price deal-flagging) lands, set `#tracker` to **All Messages**
  in Discord notification settings if you want a phone buzz on every change.

## Add / remove a store
Edit `config.toml` (`[[stores]]` block). Only `platform = "shopify"` is supported in Phase 1.
Disable a store with `enabled = false` (e.g. if it starts blocking GitHub IPs).

## Tune franchise matching
Edit `[franchise_synonyms]` in `config.toml`. Matching checks tags → product_type → title.

## Local test run
```bash
export DISCORD_DEALS_WEBHOOK=... DISCORD_TRACKER_WEBHOOK=...
uv run python -m tcg_watcher
```

## Known limitations (Phase 1)
- Shopify reports in/out of stock only, not quantity.
- GitHub cron is best-effort (~5–15 min); not for sub-minute drop sniping.
- 3 non-Shopify sites (2 Wix + rarecandy) are Phase 2.
- TCGplayer "below market" deal-flagging is Phase 3.

## Tests
`uv run pytest -v`
```

- [ ] **Step 2: Commit and push**

```bash
git add README.md
git commit -m "docs: add README with setup and operations"
git push
```

---

## Self-Review (completed during planning)

**Spec coverage:**
- 10-store Shopify roster → Task 4 (`config.toml`) ✅
- Shopify `/products.json` paginated adapter → Task 5 ✅
- Franchise filter (tags→type→title) → Task 6 ✅
- 4 event types + seed-first + restock-precedence → Task 8 ✅
- Discord loud/quiet + flood cap → Task 9 ✅
- Snapshot state committed to repo → Tasks 7, 12 ✅
- GitHub Actions 5-min cron + concurrency + auto-keep-alive → Task 12 ✅
- Adapter isolation / never crash the run → Task 10 ✅
- Landmine #1 spike (gates build) → Task 2 ✅
- tcgsorted domain spike → Task 2 Step 4 ✅
- 401games feed validation → covered by Task 2 spike (probes 401games) ✅
- Currency carried per-store for Phase 3 normalization → Task 4 (`currency` field) ✅
- Phase 2 (Wix/Next) and Phase 3 (tcgcsv deal-flagging) → **out of scope, separate plans** ✅

**Deferred to their own plans (by design):** Phase 2 Tier-2 adapters; Phase 3 price oracle, USD FX normalization, sealed-first fuzzy matching, below-market loud routing.

**Placeholder scan:** no TBD/TODO; every code step has complete code. ✅
**Type consistency:** `http_get(url, params=None)`, `fetch_products(store, http_get)`, `detect_events(current, previous, epsilon)`, `send_events(events, post_loud, post_quiet, max_events_per_store, route)`, snapshot shape `{seeded,last_run,variants}` — consistent across Tasks 5–12. ✅
