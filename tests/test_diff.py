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

def test_preorder_restock_emits_preorder_open():
    prev = snap({"v1": {"price": 10.0, "in_stock": False, "title": "T", "is_preorder": False}})
    events = detect_events([mk("v1", 10.0, True, preorder=True)], prev)
    assert len(events) == 1
    assert events[0].type == EventType.PREORDER_OPEN
    assert events[0].previous_in_stock is False

def test_no_price_change_when_out_of_stock():
    prev = snap({"v1": {"price": 10.0, "in_stock": True, "title": "T", "is_preorder": False}})
    events = detect_events([mk("v1", 8.0, False)], prev)  # price moved but now out of stock
    assert events == []

def test_price_change_suppressed_below_min_pct():
    # algorithmic $5 drift on a $500 box = 1% < 5% floor -> noise, no event
    prev = snap({"v1": {"price": 500.0, "in_stock": True, "title": "T", "is_preorder": False}})
    events = detect_events([mk("v1", 505.0, True)], prev, epsilon=0.01, min_pct=0.05)
    assert events == []

def test_price_change_fires_at_or_above_min_pct():
    # real 6% move clears the 5% floor
    prev = snap({"v1": {"price": 500.0, "in_stock": True, "title": "T", "is_preorder": False}})
    events = detect_events([mk("v1", 530.0, True)], prev, epsilon=0.01, min_pct=0.05)
    assert [e.type for e in events] == [EventType.PRICE_CHANGE]
    assert events[0].previous_price == 500.0

def test_min_pct_uses_old_price_as_base():
    # exactly at the floor (5% of 500 = 25) fires; just under does not
    prev = snap({"v1": {"price": 500.0, "in_stock": True, "title": "T", "is_preorder": False}})
    assert detect_events([mk("v1", 525.0, True)], prev, epsilon=0.01, min_pct=0.05)
    assert detect_events([mk("v1", 524.99, True)], prev, epsilon=0.01, min_pct=0.05) == []

def test_min_pct_zero_is_backwards_compatible():
    # default behaviour: any move beyond epsilon fires
    prev = snap({"v1": {"price": 10.0, "in_stock": True, "title": "T", "is_preorder": False}})
    events = detect_events([mk("v1", 10.10, True)], prev, epsilon=0.01)
    assert [e.type for e in events] == [EventType.PRICE_CHANGE]

def test_min_pct_free_item_still_fires():
    # old price 0 -> percentage undefined; any priced move should still fire (no div-by-zero)
    prev = snap({"v1": {"price": 0.0, "in_stock": True, "title": "T", "is_preorder": False}})
    events = detect_events([mk("v1", 5.0, True)], prev, epsilon=0.01, min_pct=0.05)
    assert [e.type for e in events] == [EventType.PRICE_CHANGE]
