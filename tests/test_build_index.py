import json
from tcg_watcher.pricing.build_index import build, sealed_entries

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


def test_sealed_entries_drops_bare_case_nonsealed():
    products = [
        {"productId": 1, "name": "Alakazam Case File Binder"},
        {"productId": 2, "name": "Silver Tempest Booster Box"},
    ]
    prices = [
        {"productId": 1, "marketPrice": 20.0, "subTypeName": "Normal"},
        {"productId": 2, "marketPrice": 500.0, "subTypeName": "Normal"},
    ]
    out = sealed_entries(products, prices)
    assert set(out) == {"silver tempest booster box"}


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
    assert "romance dawn booster box" in idx["one piece"]
    assert idx.get("pokemon", {}) == {}
