from pathlib import Path
from tcg_watcher.models import Product
from tcg_watcher.state import snapshot_path, load_snapshot, build_snapshot, merge_snapshot, save_snapshot

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

def seeded(variants, last_run="2026-07-01T00:00:00Z"):
    return {"seeded": True, "last_run": last_run, "variants": variants}

def entry(price, in_stock, last_seen=None):
    e = {"price": price, "in_stock": in_stock, "title": "ETB", "is_preorder": False}
    if last_seen is not None:
        e["last_seen"] = last_seen
    return e

def test_merge_keeps_departed_variant():
    prev = seeded({"v1": entry(10.0, True, "2026-07-01T00:00:00Z"),
                   "v2": entry(20.0, False, "2026-07-01T00:00:00Z")})
    snap = merge_snapshot(prev, [mk("v1", 10.0, True)], "2026-07-02T00:00:00Z")
    assert snap["variants"]["v2"]["price"] == 20.0
    assert snap["variants"]["v2"]["in_stock"] is False

def test_merge_overlays_current_and_stamps_last_seen():
    prev = seeded({"v1": entry(10.0, False, "2026-07-01T00:00:00Z")})
    snap = merge_snapshot(prev, [mk("v1", 12.0, True)], "2026-07-02T00:00:00Z")
    v1 = snap["variants"]["v1"]
    assert v1["price"] == 12.0 and v1["in_stock"] is True
    assert v1["last_seen"] == "2026-07-02T00:00:00Z"
    assert snap["last_run"] == "2026-07-02T00:00:00Z"

def test_merge_prunes_departed_older_than_ttl():
    prev = seeded({"old": entry(5.0, True, "2026-06-10T00:00:00Z"),
                   "fresh": entry(6.0, True, "2026-06-25T00:00:00Z")})
    snap = merge_snapshot(prev, [], "2026-07-01T00:00:00Z")
    assert "old" not in snap["variants"]
    assert "fresh" in snap["variants"]

def test_merge_stamps_legacy_entry_missing_last_seen():
    prev = seeded({"legacy": entry(5.0, True)})
    snap = merge_snapshot(prev, [], "2026-07-01T00:00:00Z")
    assert snap["variants"]["legacy"]["last_seen"] == "2026-07-01T00:00:00Z"

def test_merge_unseeded_prev_builds_fresh():
    prev = {"seeded": False, "last_run": None, "variants": {"stale": entry(1.0, True)}}
    snap = merge_snapshot(prev, [mk("v1", 10.0, True)], "2026-07-01T00:00:00Z")
    assert set(snap["variants"]) == {"v1"}
    assert snap["seeded"] is True

def test_merge_tolerates_unparseable_timestamps():
    prev = seeded({"v2": entry(20.0, True, "t0")}, last_run="t0")
    snap = merge_snapshot(prev, [mk("v1", 10.0, True)], "t1")
    assert "v2" in snap["variants"]
