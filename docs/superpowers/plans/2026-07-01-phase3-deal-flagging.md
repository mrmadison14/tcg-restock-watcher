# Phase 3 — Deal-Flagging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach a TCGplayer market-price verdict (from tcgcsv.com's daily mirror) to every event, and fire loud `#deals` alerts when a listing is ≥10% below market or is a restock/preorder.

**Architecture:** A separate daily GitHub Action builds a sealed-only `{franchise: {normalized_name: {market_usd, display_name}}}` index (+ a daily USD FX rate) and commits them to `data/`. The 5-min `watch` run loads that index once, matches each event's product with `difflib`, normalizes CAD→USD, and computes a `Verdict`. Enrichment never suppresses an alert.

**Tech Stack:** Python 3.13, `uv`, `httpx` (existing), `difflib` + `json` (stdlib — no new deps).

**Spec:** `docs/superpowers/specs/2026-07-01-phase3-deal-flagging-design.md`

---

## File Structure

- **Create** `src/tcg_watcher/pricing/__init__.py` — package marker (empty).
- **Create** `src/tcg_watcher/pricing/match.py` — pure `normalize()` + `best_match()` (difflib). No I/O.
- **Create** `src/tcg_watcher/pricing/tcgcsv.py` — thin client: `groups/products/prices` over an injected `http_get`.
- **Create** `src/tcg_watcher/pricing/build_index.py` — `sealed_entries()` (pure join) + `build()` (walk + FX + write JSON) + `main()` CLI.
- **Create** `src/tcg_watcher/pricing/oracle.py` — `Oracle.load()` + `Oracle.verdict(product)`.
- **Modify** `src/tcg_watcher/models.py` — add `Verdict`; add `Event.verdict`.
- **Modify** `src/tcg_watcher/config.py` — add `PricingConfig`; add optional `Config.pricing`.
- **Modify** `src/tcg_watcher/notify.py` — `route_deal_or_urgent()`; verdict/dual-currency embed line.
- **Modify** `src/tcg_watcher/runner.py` — accept optional `oracle`; enrich events; use deal route.
- **Modify** `src/tcg_watcher/__main__.py` — build oracle from config, pass to `run_once`.
- **Modify** `config.toml` — add `[pricing]` + `[pricing.categories]`.
- **Create** `.github/workflows/build-index.yml` — daily builder workflow.
- **Tests:** `tests/test_match.py`, `tests/test_tcgcsv.py`, `tests/test_build_index.py`, `tests/test_oracle.py`, `tests/test_notify_verdict.py`, extend `tests/test_runner.py`, `tests/test_config.py`.

Dependency order: models → match → tcgcsv → build_index → config → oracle → notify → runner/main → workflow+config.toml.

---

## Task 1: `Verdict` model + `Event.verdict`

**Files:**
- Modify: `src/tcg_watcher/models.py`
- Test: `tests/test_models_verdict.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models_verdict.py
from dataclasses import replace
from tcg_watcher.models import Product, Event, EventType, Verdict


def _p():
    return Product(store="s", product_id="1", variant_id="v", title="t", price=1.0,
                   currency="USD", in_stock=True, url="u")


def test_verdict_fields():
    v = Verdict(status="deal", market_usd=100.0, store_usd=80.0, pct_under=0.2,
                matched_name="Set Booster Box", currency="USD")
    assert v.status == "deal" and v.pct_under == 0.2


def test_event_defaults_verdict_none_and_replaceable():
    e = Event(type=EventType.RESTOCK, product=_p())
    assert e.verdict is None
    v = Verdict(status="na", market_usd=None, store_usd=1.0, pct_under=None,
                matched_name=None, currency="USD")
    e2 = replace(e, verdict=v)
    assert e2.verdict.status == "na" and e.verdict is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models_verdict.py -q`
Expected: FAIL — `ImportError: cannot import name 'Verdict'`.

- [ ] **Step 3: Add `Verdict` and `Event.verdict`**

In `src/tcg_watcher/models.py`, add after the `EventType` enum (before `Product`):

```python
@dataclass(frozen=True)
class Verdict:
    status: str  # "deal" | "market" | "na"
    market_usd: float | None
    store_usd: float | None
    pct_under: float | None
    matched_name: str | None
    currency: str
```

Add one field to the existing `Event` dataclass (keep the others):

```python
@dataclass(frozen=True)
class Event:
    type: EventType
    product: Product
    previous_price: float | None = None
    previous_in_stock: bool | None = None
    verdict: "Verdict | None" = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models_verdict.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/models.py tests/test_models_verdict.py
git commit -m "feat(models): add Verdict and Event.verdict for deal-flagging"
```

---

## Task 2: `pricing/match.py` — normalize + best_match

**Files:**
- Create: `src/tcg_watcher/pricing/__init__.py` (empty)
- Create: `src/tcg_watcher/pricing/match.py`
- Test: `tests/test_match.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_match.py
from tcg_watcher.pricing.match import normalize, best_match


def test_normalize_strips_franchise_and_expands_etb():
    assert normalize("Pokemon - Surging Sparks - ETB") == "surging sparks elite trainer box"
    assert normalize("One Piece Card Game - Romance Dawn Booster Box") == "card game romance dawn booster box"


def test_normalize_drops_edition_and_punct():
    assert normalize("Pokemon - Terastal Festival ex - Japanese Booster Box") == "terastal festival ex booster box"


INDEX = {
    "surging sparks elite trainer box": {"market_usd": 60.0, "display_name": "Surging Sparks Elite Trainer Box"},
    "prismatic evolutions booster bundle": {"market_usd": 30.0, "display_name": "Prismatic Evolutions Booster Bundle"},
}


def test_best_match_hits_above_threshold():
    m = best_match(normalize("Pokemon - Surging Sparks - Elite Trainer Box"), INDEX, 0.86)
    assert m == ("Surging Sparks Elite Trainer Box", 60.0)


def test_best_match_returns_none_below_threshold():
    assert best_match("scarlet violet 151 booster box", INDEX, 0.86) is None


def test_best_match_requires_token_overlap():
    assert best_match("", INDEX, 0.86) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_match.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tcg_watcher.pricing'`.

- [ ] **Step 3: Create the package + implementation**

Create empty `src/tcg_watcher/pricing/__init__.py`.

Create `src/tcg_watcher/pricing/match.py`:

```python
from __future__ import annotations
import re
from difflib import SequenceMatcher

_STRIP_WORDS = (
    "pokémon", "pokemon", "one piece",
    "dragon ball super", "dragon ball", "fusion world",
    "english", "japanese",
)


def normalize(title: str) -> str:
    s = title.lower()
    s = re.sub(r"\betb\b", "elite trainer box", s)
    for w in _STRIP_WORDS:
        s = s.replace(w, " ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def best_match(norm_title: str, index: dict, threshold: float):
    q = set(norm_title.split())
    if not q:
        return None
    best = None
    best_ratio = 0.0
    for name, entry in index.items():
        ratio = SequenceMatcher(None, norm_title, name).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = (name, entry)
    if best is None or best_ratio < threshold:
        return None
    name, entry = best
    if not (q & set(name.split())):
        return None
    return (entry["display_name"], entry["market_usd"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_match.py -q`
Expected: PASS (5 passed). If `test_normalize_*` mismatch, adjust `_STRIP_WORDS` ordering (longest phrase first) — do not weaken the assertions.

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/pricing/__init__.py src/tcg_watcher/pricing/match.py tests/test_match.py
git commit -m "feat(pricing): add name normalization + difflib matcher"
```

---

## Task 3: `pricing/tcgcsv.py` — client

**Files:**
- Create: `src/tcg_watcher/pricing/tcgcsv.py`
- Test: `tests/test_tcgcsv.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tcgcsv.py
from tcg_watcher.pricing import tcgcsv


def make_get(calls):
    def get(url, params=None):
        calls.append(url)
        return {"success": True, "results": [{"url": url}]}
    return get


def test_urls_and_results():
    calls = []
    get = make_get(calls)
    assert tcgcsv.groups(get, 3) == [{"url": "https://tcgcsv.com/tcgplayer/3/groups"}]
    assert tcgcsv.products(get, 3, 3170) == [{"url": "https://tcgcsv.com/tcgplayer/3/3170/products"}]
    assert tcgcsv.prices(get, 3, 3170) == [{"url": "https://tcgcsv.com/tcgplayer/3/3170/prices"}]
    assert calls == [
        "https://tcgcsv.com/tcgplayer/3/groups",
        "https://tcgcsv.com/tcgplayer/3/3170/products",
        "https://tcgcsv.com/tcgplayer/3/3170/prices",
    ]


def test_missing_results_is_empty_list():
    assert tcgcsv.groups(lambda u, params=None: {}, 3) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tcgcsv.py -q`
Expected: FAIL — `AttributeError: module 'tcg_watcher.pricing.tcgcsv' has no attribute 'groups'` (or ModuleNotFound).

- [ ] **Step 3: Implement**

Create `src/tcg_watcher/pricing/tcgcsv.py`:

```python
from __future__ import annotations

_BASE = "https://tcgcsv.com/tcgplayer"


def groups(http_get, category_id: int) -> list[dict]:
    return (http_get(f"{_BASE}/{category_id}/groups") or {}).get("results", [])


def products(http_get, category_id: int, group_id) -> list[dict]:
    return (http_get(f"{_BASE}/{category_id}/{group_id}/products") or {}).get("results", [])


def prices(http_get, category_id: int, group_id) -> list[dict]:
    return (http_get(f"{_BASE}/{category_id}/{group_id}/prices") or {}).get("results", [])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tcgcsv.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/pricing/tcgcsv.py tests/test_tcgcsv.py
git commit -m "feat(pricing): add thin tcgcsv client"
```

---

## Task 4: `pricing/build_index.py` — sealed join (pure)

**Files:**
- Create: `src/tcg_watcher/pricing/build_index.py`
- Test: `tests/test_build_index.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_build_index.py
from tcg_watcher.pricing.build_index import sealed_entries

PRODUCTS = [
    {"productId": 1, "name": "Silver Tempest Booster Box"},
    {"productId": 2, "name": "Lugia VSTAR"},                       # single -> dropped
    {"productId": 3, "name": "Silver Tempest Elite Trainer Box"},
    {"productId": 4, "name": "Fall 2022 Collector Chest Case"},    # sealed but unpriced -> dropped
]
PRICES = [
    {"productId": 1, "marketPrice": 544.53, "subTypeName": "Normal"},
    {"productId": 2, "marketPrice": 3.21, "subTypeName": "Holofoil"},
    {"productId": 3, "marketPrice": 170.2, "subTypeName": "Normal"},
    {"productId": 4, "marketPrice": None, "subTypeName": "Normal"},
]


def test_sealed_entries_filters_and_joins():
    out = sealed_entries(PRODUCTS, PRICES)
    assert set(out) == {"silver tempest booster box", "silver tempest elite trainer box"}
    assert out["silver tempest booster box"] == {"market_usd": 544.53,
                                                 "display_name": "Silver Tempest Booster Box"}


def test_sealed_entries_prefers_normal_subtype():
    products = [{"productId": 9, "name": "Set Booster Box"}]
    prices = [
        {"productId": 9, "marketPrice": 1.0, "subTypeName": "Holofoil"},
        {"productId": 9, "marketPrice": 500.0, "subTypeName": "Normal"},
    ]
    out = sealed_entries(products, prices)
    assert out["set booster box"]["market_usd"] == 500.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_build_index.py -q`
Expected: FAIL — `ImportError: cannot import name 'sealed_entries'`.

- [ ] **Step 3: Implement `sealed_entries`**

Create `src/tcg_watcher/pricing/build_index.py`:

```python
from __future__ import annotations
from .match import normalize

_SEALED_MARKERS = (
    "booster box", "elite trainer", "etb", "booster bundle", "booster pack",
    "collection", "tin", "blister", "case", "premium",
)


def _market_for(pid, price_rows: list[dict]):
    normal = None
    fallback = None
    for pr in price_rows:
        if pr.get("productId") != pid or pr.get("marketPrice") is None:
            continue
        if pr.get("subTypeName") == "Normal":
            normal = pr["marketPrice"]
        elif fallback is None:
            fallback = pr["marketPrice"]
    return normal if normal is not None else fallback


def sealed_entries(products: list[dict], prices: list[dict]) -> dict:
    out: dict = {}
    for p in products:
        name = p.get("name", "")
        low = name.lower()
        if not any(m in low for m in _SEALED_MARKERS):
            continue
        mp = _market_for(p["productId"], prices)
        if mp is None:
            continue
        out[normalize(name)] = {"market_usd": mp, "display_name": name}
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_build_index.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/pricing/build_index.py tests/test_build_index.py
git commit -m "feat(pricing): sealed-product price join for index build"
```

---

## Task 5: `pricing/build_index.py` — walk + FX + write

**Files:**
- Modify: `src/tcg_watcher/pricing/build_index.py`
- Test: `tests/test_build_index.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_index.py`:

```python
import json
from tcg_watcher.pricing.build_index import build


def test_build_walks_categories_and_writes(tmp_path):
    groups_by_cat = {3: [{"groupId": 3170}], 68: [{"groupId": 500}]}
    prod_by = {(3, 3170): [{"productId": 1, "name": "Silver Tempest Booster Box"}],
               (68, 500): [{"productId": 2, "name": "Romance Dawn Booster Box"}]}
    price_by = {(3, 3170): [{"productId": 1, "marketPrice": 500.0, "subTypeName": "Normal"}],
                (68, 500): [{"productId": 2, "marketPrice": 120.0, "subTypeName": "Normal"}]}

    def http_get(url, params=None):
        if url.endswith("/groups"):
            cat = int(url.split("/")[-2]); return {"results": groups_by_cat.get(cat, [])}
        if url.endswith("/products"):
            cat = int(url.split("/")[-3]); grp = int(url.split("/")[-2]); return {"results": prod_by.get((cat, grp), [])}
        if url.endswith("/prices"):
            cat = int(url.split("/")[-3]); grp = int(url.split("/")[-2]); return {"results": price_by.get((cat, grp), [])}
        if "er-api" in url:
            return {"result": "success", "rates": {"CAD": 1.36}}
        raise AssertionError(url)

    categories = {"pokemon": (3,), "one piece": (68,)}
    idx_path = tmp_path / "price_index.json"
    fx_path = tmp_path / "fx.json"
    build(http_get, categories, "https://open.er-api.com/v6/latest/USD",
          idx_path, fx_path, now_iso="2026-07-01T20:30:00Z")

    idx = json.loads(idx_path.read_text())
    assert idx["pokemon"]["silver tempest booster box"]["market_usd"] == 500.0
    assert idx["one piece"]["romance dawn booster box"]["market_usd"] == 120.0
    fx = json.loads(fx_path.read_text())
    assert fx["rates"]["CAD"] == 1.36 and fx["fetched_at"] == "2026-07-01T20:30:00Z"


def test_build_isolates_category_failure(tmp_path):
    def http_get(url, params=None):
        if "/3/" in url or url.endswith("/3/groups"):
            raise RuntimeError("cat 3 down")
        if url.endswith("/groups"):
            return {"results": [{"groupId": 500}]}
        if url.endswith("/products"):
            return {"results": [{"productId": 2, "name": "Romance Dawn Booster Box"}]}
        if url.endswith("/prices"):
            return {"results": [{"productId": 2, "marketPrice": 120.0, "subTypeName": "Normal"}]}
        if "er-api" in url:
            return {"rates": {"CAD": 1.36}}
        raise AssertionError(url)

    idx_path = tmp_path / "i.json"; fx_path = tmp_path / "f.json"
    build(http_get, {"pokemon": (3,), "one piece": (68,)},
          "https://open.er-api.com/v6/latest/USD", idx_path, fx_path, now_iso="t")
    idx = json.loads(idx_path.read_text())
    assert "romance dawn booster box" in idx["one piece"]        # survived
    assert idx.get("pokemon", {}) == {}                          # failed cat -> empty, no crash
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_build_index.py -q`
Expected: FAIL — `ImportError: cannot import name 'build'`.

- [ ] **Step 3: Implement `build` + `main`**

Append to `src/tcg_watcher/pricing/build_index.py`:

```python
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import tcgcsv
from ..http import make_httpx_get


def _franchise_index(http_get, category_ids) -> dict:
    merged: dict = {}
    for cat in category_ids:
        try:
            for g in tcgcsv.groups(http_get, cat):
                gid = g["groupId"]
                products = tcgcsv.products(http_get, cat, gid)
                prices = tcgcsv.prices(http_get, cat, gid)
                merged.update(sealed_entries(products, prices))
        except Exception as exc:  # noqa: BLE001 - one category never aborts the whole build
            print(f"[build-index] category {cat} failed: {type(exc).__name__}: {exc}")
    return merged


def build(http_get, categories: dict, fx_url: str, index_path, fx_path, now_iso: str) -> None:
    index = {franchise: _franchise_index(http_get, cats) for franchise, cats in categories.items()}
    fx = http_get(fx_url) or {}
    fx_out = {"rates": fx.get("rates", {}), "fetched_at": now_iso}

    index_path = Path(index_path); fx_path = Path(fx_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    fx_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    fx_path.write_text(json.dumps(fx_out, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    total = sum(len(v) for v in index.values())
    print(f"[build-index] wrote {total} sealed entries across {len(index)} franchises; fx rates={list(fx_out['rates'])}")


def main() -> int:
    from ..config import load_config
    config = load_config(os.environ.get("TCG_CONFIG", "config.toml"))
    if config.pricing is None:
        print("[build-index] no [pricing] config; nothing to do")
        return 0
    http_get = make_httpx_get(min_interval=1.0)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    build(http_get, config.pricing.categories, config.pricing.fx_url,
          config.pricing.index_path, config.pricing.fx_path, now_iso)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_build_index.py -q`
Expected: PASS (4 passed). Note: `main()` is exercised in Task 9; these tests cover `build()` directly.

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/pricing/build_index.py tests/test_build_index.py
git commit -m "feat(pricing): daily index builder (walk categories, FX, write JSON)"
```

---

## Task 6: `config.py` — `[pricing]` parsing

**Files:**
- Modify: `src/tcg_watcher/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from tcg_watcher.config import load_config

BASE = """
[[stores]]
key = "s"
base_url = "https://s.test"
platform = "shopify"
currency = "USD"

[franchise_synonyms]
pokemon = ["pokemon"]

[thresholds]
max_events_per_store = 25
price_epsilon = 0.01
"""

PRICING = """
[pricing]
enabled = true
deal_threshold = 0.10
match_threshold = 0.86
index_path = "data/price_index.json"
fx_path = "data/fx.json"
fx_url = "https://open.er-api.com/v6/latest/USD"

[pricing.categories]
pokemon = [3, 85]
"one piece" = [68]
"dragon ball" = [23, 27, 80]
"""


def test_pricing_absent_is_none(tmp_path):
    f = tmp_path / "c.toml"; f.write_text(BASE)
    assert load_config(f).pricing is None


def test_pricing_parsed(tmp_path):
    f = tmp_path / "c.toml"; f.write_text(BASE + PRICING)
    pr = load_config(f).pricing
    assert pr.enabled is True and pr.deal_threshold == 0.10
    assert pr.categories["pokemon"] == (3, 85)
    assert pr.categories["dragon ball"] == (23, 27, 80)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'pricing'`.

- [ ] **Step 3: Implement**

In `src/tcg_watcher/config.py`, add a dataclass after `Store`:

```python
@dataclass(frozen=True)
class PricingConfig:
    enabled: bool
    deal_threshold: float
    match_threshold: float
    index_path: str
    fx_path: str
    fx_url: str
    categories: dict[str, tuple[int, ...]]
```

Add a field to `Config` (keep existing fields):

```python
@dataclass(frozen=True)
class Config:
    stores: tuple[Store, ...]
    franchise_synonyms: dict[str, tuple[str, ...]]
    max_events_per_store: int
    price_epsilon: float
    pricing: "PricingConfig | None" = None
```

In `load_config`, before the `return`, parse the optional block:

```python
    pricing = None
    if "pricing" in data:
        pr = data["pricing"]
        pricing = PricingConfig(
            enabled=pr.get("enabled", True),
            deal_threshold=pr["deal_threshold"],
            match_threshold=pr["match_threshold"],
            index_path=pr["index_path"],
            fx_path=pr["fx_path"],
            fx_url=pr["fx_url"],
            categories={k: tuple(v) for k, v in pr.get("categories", {}).items()},
        )
```

Then pass `pricing=pricing` into the `Config(...)` constructor.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/config.py tests/test_config.py
git commit -m "feat(config): parse optional [pricing] section"
```

---

## Task 7: `pricing/oracle.py` — verdict

**Files:**
- Create: `src/tcg_watcher/pricing/oracle.py`
- Test: `tests/test_oracle.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_oracle.py
import json
from tcg_watcher.models import Product
from tcg_watcher.pricing.oracle import Oracle


def _oracle(tmp_path, index, rates):
    ip = tmp_path / "i.json"; fp = tmp_path / "f.json"
    ip.write_text(json.dumps(index)); fp.write_text(json.dumps({"rates": rates, "fetched_at": "t"}))
    return Oracle.load(ip, fp, deal_threshold=0.10, match_threshold=0.86)


def _prod(title, price, currency="USD", franchise="pokemon"):
    return Product(store="s", product_id="1", variant_id="v", title=title, price=price,
                   currency=currency, in_stock=True, url="u", franchise=franchise)


IDX = {"pokemon": {"surging sparks elite trainer box":
                   {"market_usd": 60.0, "display_name": "Surging Sparks Elite Trainer Box"}}}


def test_deal_when_10pct_or_more_under(tmp_path):
    o = _oracle(tmp_path, IDX, {"CAD": 1.36})
    v = o.verdict(_prod("Pokemon - Surging Sparks - Elite Trainer Box", 48.0))
    assert v.status == "deal" and round(v.pct_under, 2) == 0.20


def test_market_when_under_threshold(tmp_path):
    o = _oracle(tmp_path, IDX, {"CAD": 1.36})
    v = o.verdict(_prod("Pokemon - Surging Sparks - Elite Trainer Box", 57.0))
    assert v.status == "market" and v.market_usd == 60.0


def test_cad_normalized_to_usd(tmp_path):
    o = _oracle(tmp_path, IDX, {"CAD": 1.36})
    v = o.verdict(_prod("Pokemon - Surging Sparks - Elite Trainer Box", 68.0, currency="CAD"))
    assert round(v.store_usd, 2) == 50.0 and v.status == "deal"


def test_na_on_no_match(tmp_path):
    o = _oracle(tmp_path, IDX, {"CAD": 1.36})
    v = o.verdict(_prod("Pokemon - Journey Together - Booster Box", 300.0))
    assert v.status == "na" and v.matched_name is None


def test_na_but_never_raises_when_index_missing(tmp_path):
    o = Oracle.load(tmp_path / "nope.json", tmp_path / "no-fx.json", 0.10, 0.86)
    v = o.verdict(_prod("anything", 10.0))
    assert v.status == "na"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_oracle.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tcg_watcher.pricing.oracle'`.

- [ ] **Step 3: Implement**

Create `src/tcg_watcher/pricing/oracle.py`:

```python
from __future__ import annotations
import json
from pathlib import Path

from ..models import Product, Verdict
from .match import normalize, best_match


class Oracle:
    def __init__(self, index: dict, fx: dict, deal_threshold: float, match_threshold: float):
        self.index = index
        self.rates = fx.get("rates", {})
        self.deal_threshold = deal_threshold
        self.match_threshold = match_threshold

    @classmethod
    def load(cls, index_path, fx_path, deal_threshold: float, match_threshold: float) -> "Oracle":
        index = cls._read(index_path)
        fx = cls._read(fx_path)
        return cls(index, fx, deal_threshold, match_threshold)

    @staticmethod
    def _read(path) -> dict:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _to_usd(self, price: float, currency: str):
        if currency == "USD":
            return price
        rate = self.rates.get(currency)
        if not rate:
            return None
        return price / rate

    def verdict(self, product: Product) -> Verdict:
        store_usd = self._to_usd(product.price, product.currency)
        fr_index = self.index.get(product.franchise or "", {})
        match = best_match(normalize(product.title), fr_index, self.match_threshold) if fr_index else None
        if match is None or store_usd is None:
            return Verdict(status="na", market_usd=(match[1] if match else None),
                           store_usd=store_usd, pct_under=None,
                           matched_name=(match[0] if match else None), currency=product.currency)
        display_name, market_usd = match
        pct = (market_usd - store_usd) / market_usd if market_usd else None
        status = "deal" if (pct is not None and pct >= self.deal_threshold) else "market"
        return Verdict(status=status, market_usd=market_usd, store_usd=store_usd,
                       pct_under=pct, matched_name=display_name, currency=product.currency)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_oracle.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/pricing/oracle.py tests/test_oracle.py
git commit -m "feat(pricing): oracle verdict (deal/market/na, FX, never-raise)"
```

---

## Task 8: `notify.py` — deal routing + verdict embed line

**Files:**
- Modify: `src/tcg_watcher/notify.py`
- Test: `tests/test_notify_verdict.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_notify_verdict.py
from tcg_watcher.models import Product, Event, EventType, Verdict
from tcg_watcher.notify import route_deal_or_urgent, build_embed


def _p(currency="USD", price=50.0):
    return Product(store="s", product_id="1", variant_id="v", title="Set Booster Box",
                   price=price, currency=currency, in_stock=True, url="u", franchise="pokemon")


def _ev(etype, verdict=None):
    return Event(type=etype, product=_p(), verdict=verdict)


DEAL = Verdict("deal", 100.0, 80.0, 0.20, "Set Booster Box", "USD")
MARKET = Verdict("market", 100.0, 98.0, 0.02, "Set Booster Box", "USD")


def test_deal_routes_loud_even_for_new_listing():
    assert route_deal_or_urgent(_ev(EventType.NEW_PRODUCT, DEAL)) is True


def test_restock_loud_without_verdict():
    assert route_deal_or_urgent(_ev(EventType.RESTOCK, None)) is True


def test_market_new_listing_quiet():
    assert route_deal_or_urgent(_ev(EventType.NEW_PRODUCT, MARKET)) is False


def test_embed_shows_deal_market_field():
    fields = build_embed(_ev(EventType.NEW_PRODUCT, DEAL))["fields"]
    market = [f["value"] for f in fields if f["name"] == "Market"][0]
    assert "under market" in market and "US$100" in market


def test_embed_market_field_na_when_no_verdict():
    fields = build_embed(_ev(EventType.RESTOCK, None))["fields"]
    assert [f["value"] for f in fields if f["name"] == "Market"][0] == "n/a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_notify_verdict.py -q`
Expected: FAIL — `ImportError: cannot import name 'route_deal_or_urgent'`.

- [ ] **Step 3: Implement**

In `src/tcg_watcher/notify.py`, add after `route_loud`:

```python
def route_deal_or_urgent(event: Event) -> bool:
    v = event.verdict
    if v is not None and v.status == "deal":
        return True
    return event.type in _LOUD_TYPES


def _market_line(event: Event) -> str:
    v = event.verdict
    if v is None or v.status == "na" or v.market_usd is None or v.store_usd is None:
        return "n/a"
    if v.status == "deal":
        return f"🔥 {v.pct_under * 100:.0f}% under market (≈US${v.store_usd:.2f} vs US${v.market_usd:.2f})"
    if v.pct_under is not None and v.pct_under > 0:
        rel = f"{v.pct_under * 100:.0f}% under market"
    elif v.pct_under is not None and v.pct_under < 0:
        rel = f"{-v.pct_under * 100:.0f}% above market"
    else:
        rel = "at market"
    return f"{rel} (≈US${v.store_usd:.2f} vs US${v.market_usd:.2f})"
```

In `build_embed`, add a `Market` field to the `fields` list (after the Franchise field):

```python
        {"name": "Market", "value": _market_line(event), "inline": True},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_notify_verdict.py -q` then `uv run pytest -q`
Expected: PASS. If any pre-existing notify test asserts an exact embed field count, update that assertion to include the new `Market` field — do not remove the field.

- [ ] **Step 5: Commit**

```bash
git add src/tcg_watcher/notify.py tests/test_notify_verdict.py
git commit -m "feat(notify): deal-aware routing + market verdict embed field"
```

---

## Task 9: Wire oracle into `runner.py` + `__main__.py`

**Files:**
- Modify: `src/tcg_watcher/runner.py`
- Modify: `src/tcg_watcher/__main__.py`
- Test: `tests/test_runner.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_runner.py` (self-contained — builds its own `Config` and fake `http_get`):

```python
from dataclasses import replace as _replace
from tcg_watcher.models import Verdict


class _StubOracle:
    def verdict(self, product):
        # any matched product priced as a deal
        return Verdict("deal", 100.0, 50.0, 0.5, product.title, product.currency)


def test_run_once_enriches_and_routes_deal_loud(tmp_path):
    # Build a config with one full-crawl store that yields a seeded restock is complex;
    # assert enrichment path directly: a seeded store with a new product -> NEW_PRODUCT,
    # verdict deal -> must go to post_loud.
    from tcg_watcher.config import Config, Store
    store = Store(key="s", base_url="https://s.test", platform="shopify", currency="USD")
    config = Config(stores=(store,), franchise_synonyms={"pokemon": ("pokemon",)},
                    max_events_per_store=25, price_epsilon=0.01)

    page = {"products": [{"id": 1, "handle": "h", "title": "Pokemon Booster Box",
                          "product_type": "", "tags": ["Pokemon"], "images": [],
                          "variants": [{"id": 9, "title": "Default Title", "price": "50.00", "available": True}]}]}

    def http_get(url, params=None):
        return page if (params or {}).get("page", 1) == 1 else {"products": []}

    # pre-seed so the product is a NEW_PRODUCT on this run
    (tmp_path / "s.json").write_text('{"seeded": true, "last_run": "t", "variants": {}}')

    loud, quiet = [], []
    from tcg_watcher.runner import run_once
    run_once(config, http_get, loud.append, quiet.append, tmp_path, "t", oracle=_StubOracle())
    assert len(loud) == 1 and loud[0]["content"] == "@here"
    assert quiet == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runner.py -q`
Expected: FAIL — `TypeError: run_once() got an unexpected keyword argument 'oracle'`.

- [ ] **Step 3: Implement runner change**

In `src/tcg_watcher/runner.py`: update imports and signature, enrich events, use the deal route.

Change the import line:

```python
from .notify import send_events, route_deal_or_urgent
```

Add `from dataclasses import replace` at the top (with the other imports).

Change the signature:

```python
def run_once(config, http_get, post_loud, post_quiet, state_dir, now_iso, oracle=None) -> RunReport:
```

Replace the `detect_events` → `send_events` block (currently lines ~62-65) with:

```python
        events = detect_events(watched, prev, config.price_epsilon)
        if oracle is not None:
            events = [replace(e, verdict=oracle.verdict(e.product)) for e in events]
        report.events_sent += send_events(
            events, post_loud, post_quiet, config.max_events_per_store, route=route_deal_or_urgent
        )
```

- [ ] **Step 4: Wire the oracle in `__main__.py`**

In `src/tcg_watcher/__main__.py`, after `config = load_config(...)`, build the oracle and pass it:

```python
    oracle = None
    if config.pricing is not None and config.pricing.enabled:
        from .pricing.oracle import Oracle
        oracle = Oracle.load(config.pricing.index_path, config.pricing.fx_path,
                             config.pricing.deal_threshold, config.pricing.match_threshold)
```

Change the `run_once(...)` call to pass `oracle=oracle`:

```python
    report = run_once(config, http_get, post_loud, post_quiet, state_dir, now_iso(), oracle=oracle)
```

- [ ] **Step 5: Run tests to verify pass (full suite)**

Run: `uv run pytest -q`
Expected: PASS — all prior tests + new ones green (existing `run_once` callers without `oracle` still work; verdict-less events route exactly as before).

- [ ] **Step 6: Commit**

```bash
git add src/tcg_watcher/runner.py src/tcg_watcher/__main__.py tests/test_runner.py
git commit -m "feat(runner): enrich events with market verdict + deal routing"
```

---

## Task 10: `config.toml` `[pricing]` + `build-index.yml` workflow

**Files:**
- Modify: `config.toml`
- Create: `.github/workflows/build-index.yml`

- [ ] **Step 1: Add `[pricing]` to `config.toml`**

Append to `config.toml` (after `[thresholds]`):

```toml
[pricing]
enabled = true
deal_threshold = 0.10
match_threshold = 0.86
index_path = "data/price_index.json"
fx_path = "data/fx.json"
fx_url = "https://open.er-api.com/v6/latest/USD"

[pricing.categories]
pokemon = [3, 85]
"one piece" = [68]
"dragon ball" = [23, 27, 80]
```

- [ ] **Step 2: Verify config loads**

Run: `uv run python -c "from tcg_watcher.config import load_config; p=load_config('config.toml').pricing; print(p.categories)"`
Expected: `{'pokemon': (3, 85), 'one piece': (68,), 'dragon ball': (23, 27, 80)}`

- [ ] **Step 3: Create the daily workflow**

Create `.github/workflows/build-index.yml`:

```yaml
name: build-index
on:
  schedule:
    - cron: "30 20 * * *"
  workflow_dispatch:

concurrency:
  group: tcg-build-index
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  build-index:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - name: Build price index
        run: uv run python -m tcg_watcher.pricing.build_index
      - name: Commit index
        run: |
          git config user.name "tcg-watcher-bot"
          git config user.email "actions@users.noreply.github.com"
          git add data/
          if git diff --staged --quiet; then
            echo "no index changes"
          else
            git commit -m "data: refresh price index + fx [skip ci]"
            git pull --rebase origin main
            git push
          fi
```

- [ ] **Step 4: Full suite green + commit**

Run: `uv run pytest -q`
Expected: PASS (all tests).

```bash
git add config.toml .github/workflows/build-index.yml
git commit -m "feat(ci): daily build-index workflow + [pricing] config"
```

---

## Task 11: Live smoke (post-merge, manual)

**Files:** none (operational verification).

- [ ] **Step 1: Trigger the builder**

Run: `gh workflow run build-index` — then get the run id from `gh run list --workflow=build-index --limit 1` and watch it with `gh run watch <id> --exit-status`.
Expected: run succeeds; a `data: refresh price index + fx [skip ci]` commit appears with `data/price_index.json` + `data/fx.json`.

- [ ] **Step 2: Sanity-check the committed index**

Run: `git pull --rebase && uv run python -c "import json; d=json.load(open('data/price_index.json')); print({k: len(v) for k,v in d.items()})"`
Expected: non-zero counts for `pokemon`, `one piece`, `dragon ball` (confirms category IDs 3/85/68/23/27/80 resolved; fix any zero-count franchise's IDs in `config.toml`).

- [ ] **Step 3: Trigger a watch run and confirm verdicts**

Run: `gh workflow run watch` then inspect the run log; steady-state expect `0 events`. If any event fires, confirm its embed carries a `Market` line and that a ≥10%-under listing landed in `#deals` (loud) while at/above-market went to `#tracker`.

- [ ] **Step 4: Update DEPLOYMENT/README + spec deltas**

Update `README.md` (add Phase 3: daily index, deal routing) and append an as-built note to the Phase 3 spec if reality diverged (e.g., corrected category IDs). Commit.

```bash
git add README.md docs/superpowers/specs/2026-07-01-phase3-deal-flagging-design.md
git commit -m "docs: reflect Phase 3 deal-flagging as-built"
```

---

## Notes for the implementer

- **No new dependencies** — `difflib`, `json`, `re` are stdlib; `httpx` already present. If you think you need `rapidfuzz`, stop and ask (CLAUDE.md rule).
- **No comments in production code** — matches the existing codebase style.
- **Never suppress an alert** — every enrichment failure path (missing index, no match, missing FX) must still emit the event (quiet unless restock/preorder) with `market: n/a`. This is asserted in Task 7 and Task 8.
- **`state/` bot commits every ~5 min** — always `git pull --rebase` before pushing local work.
- **tcgcsv Cloudflare** — the shared `make_httpx_get` UA is the realistic Chrome UA that passed the spike; don't swap it for a default httpx UA (that got 401'd).
