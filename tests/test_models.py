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
