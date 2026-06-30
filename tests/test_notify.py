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
