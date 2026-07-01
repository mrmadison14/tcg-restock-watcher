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
