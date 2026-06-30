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
