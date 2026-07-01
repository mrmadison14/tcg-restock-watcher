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
    run_once(cfg(store), make_http_get({"demo.test": shopify_page(False)}),
             (lambda x: None), (lambda x: None), tmp_path, "t0")
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
    assert report.stores_failed == 1

def test_disabled_store_skipped(tmp_path: Path):
    store = Store(key="off", base_url="https://off.test", platform="shopify", currency="USD", enabled=False)
    report = run_once(cfg(store), make_http_get({}), (lambda x: None), (lambda x: None), tmp_path, "t0")
    assert report.stores_ok == 0 and report.stores_failed == 0

def test_unknown_platform_counts_as_failed(tmp_path: Path):
    store = Store(key="weird", base_url="https://weird.test", platform="bigcommerce", currency="USD")
    report = run_once(cfg(store), make_http_get({}), (lambda x: None), (lambda x: None), tmp_path, "t0")
    assert report.stores_failed == 1
    assert report.stores_ok == 0

def test_now_iso_helper_format():
    from tcg_watcher.__main__ import now_iso
    s = now_iso()
    assert s.endswith("Z") and "T" in s and len(s) == 20  # YYYY-MM-DDTHH:MM:SSZ


def test_curated_store_trusts_collection_products(tmp_path: Path):
    store = Store(key="cur", base_url="https://cur.test", platform="shopify", currency="USD",
                  collections=("pokemon:pk-sealed",))
    def http_get(url, params=None):
        if (params or {}).get("page", 1) != 1:
            return {"products": []}
        return {"products": [{"id": 1, "handle": "x", "title": "Mystery Chest", "product_type": "", "tags": [], "images": [],
                "variants": [{"id": 7, "title": "Default Title", "price": "40.00", "available": True}]}]}
    report = run_once(cfg(store), http_get, (lambda x: None), (lambda x: None), tmp_path, "t0")
    assert "cur" in report.seeded
    snap = load_snapshot(snapshot_path(tmp_path, "cur"))
    assert "7" in snap["variants"]
