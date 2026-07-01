import json
from pathlib import Path

from tcg_watcher.config import Store
from tcg_watcher.adapters import rarecandy

FIXTURE = Path(__file__).parent / "fixtures" / "rarecandy_apollo.json"


def _store():
    return Store(key="rarecandy", base_url="https://rarecandy.com", platform="rarecandy", currency="USD")


def _apollo():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _by_vid():
    return {p.variant_id: p for p in rarecandy.products_from_apollo(_store(), _apollo())}


def test_maps_core_fields():
    p = _by_vid()["217222"]
    assert p.product_id == "298699"
    assert p.title.startswith("BUNDLE: 1 ASSORTED")
    assert p.price == 141.99
    assert p.currency == "USD"
    assert p.in_stock is True
    assert p.is_preorder is False
    assert p.is_sealed is True
    assert p.url == ("https://rarecandy.com/"
                     "bundle-1-assorted-ascended-heroes-mega-ex-box-and-1-first-partner-series-1-box-65659177")
    assert p.image == "https://images.rarecandy.com/tr:n-thumbnail/stores/352/inventory/17818486043501.png"


def test_franchise_tags_normalized():
    b = _by_vid()
    assert "one piece" in b["217220"].tags
    assert "dragon ball" in b["217216"].tags
    assert "pokemon" in b["217222"].tags


def test_out_of_stock_quantity_zero():
    assert _by_vid()["217226"].in_stock is False


def test_preorder_flag_from_is_preorder():
    assert _by_vid()["217246"].is_preorder is True


def test_returns_all_listings_including_unwatched():
    assert len(_by_vid()) == 6


def test_extract_apollo_from_html():
    apollo = {"Product:1": {"__typename": "Product"}}
    payload = {"props": {"pageProps": {"__APOLLO_STATE__": apollo}}}
    html = ('<html><body><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload) + "</script></body></html>")
    assert rarecandy.extract_apollo(html) == apollo


def test_extract_apollo_missing_returns_empty():
    assert rarecandy.extract_apollo("<html>no next data here</html>") == {}


def test_fetch_products_unions_surfaces_and_dedupes():
    payload = {"props": {"pageProps": {"__APOLLO_STATE__": _apollo()}}}
    html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + "</script>"
    calls = []

    def fake_get(url, params=None, as_text=False):
        calls.append((url, as_text))
        return html

    prods = rarecandy.fetch_products(_store(), fake_get)
    assert len({p.variant_id for p in prods}) == 6
    assert len(prods) == 6
    assert len(calls) >= 2
    assert all(as_text for (_url, as_text) in calls)
