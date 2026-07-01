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
