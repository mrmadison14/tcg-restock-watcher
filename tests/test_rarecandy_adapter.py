import json
import logging
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
    assert p.url == ("https://rarecandy.com/ninetalestradingcompany/shop/"
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


def _apollo_with_tags(tags):
    return {
        "RareFind:x": {"id": "vX", "slug": "x", "product": {"__ref": "Product:X"},
                       "store": {"__ref": "Store:S"}},
        "Product:X": {"id": 1, "name": "Test", "price": 1.0, "quantity": 1, "tags": tags},
        "Store:S": {"id": 5, "slug": "somestore", "name": "Some Store"},
    }


def test_url_is_store_slug_shop_path():
    b = _by_vid()
    assert b["217226"].url == "https://rarecandy.com/pokejpn/shop/abyss-eye-japanese-booster-box-81fb6611"
    assert b["217220"].url.startswith("https://rarecandy.com/otakuanimegoods/shop/")


def test_inline_store_object_used_for_url():
    apollo = {
        "RareFind:y": {"id": "vY", "slug": "y-slug", "product": {"__ref": "Product:Y"},
                       "store": {"__typename": "Store", "slug": "inlinestore"}},
        "Product:Y": {"id": 2, "name": "Y", "price": 2.0, "quantity": 1, "tags": ["pokemon", "sealed"]},
    }
    prods = rarecandy.products_from_apollo(_store(), apollo)
    assert prods[0].url == "https://rarecandy.com/inlinestore/shop/y-slug"


def test_unresolvable_store_skips_listing():
    apollo = {
        "RareFind:z": {"id": "vZ", "slug": "z-slug", "product": {"__ref": "Product:Z"}, "store": None},
        "Product:Z": {"id": 3, "name": "Z", "price": 3.0, "quantity": 1, "tags": ["pokemon", "sealed"]},
    }
    assert rarecandy.products_from_apollo(_store(), apollo) == []


def test_singles_tag_excluded_from_sealed():
    prods = rarecandy.products_from_apollo(_store(), _apollo_with_tags(["pokemon", "singles", "sealed"]))
    assert prods[0].is_sealed is False


def test_sealed_without_singles_is_sealed():
    prods = rarecandy.products_from_apollo(_store(), _apollo_with_tags(["pokemon", "sealed"]))
    assert prods[0].is_sealed is True


def _apollo_named(name, tags):
    return {
        "RareFind:x": {"id": "vX", "slug": "x", "product": {"__ref": "Product:X"},
                       "store": {"__ref": "Store:S"}},
        "Product:X": {"id": 1, "name": name, "price": 1.0, "quantity": 1, "tags": tags},
        "Store:S": {"id": 5, "slug": "somestore", "name": "Some Store"},
    }


def _sealed(name, tags=("pokemon", "sealed")):
    return rarecandy.products_from_apollo(_store(), _apollo_named(name, list(tags)))[0].is_sealed


def test_accessory_titles_excluded_from_sealed():
    for name in [
        "Ultra Pro Elite Series Playmat",
        "Vault X Premium Exo-Tec Zip Binder - 9 Pocket",
        '3" x 4" Premium Toploaders 130pt (10 Pack)',
        "Dragon Shield Deck Box",
        "9-Pocket Portfolio Album",
    ]:
        assert _sealed(name) is False, name


def test_sleeved_booster_pack_stays_sealed():
    # 'Sleeved Booster Pack' is a sealed product, NOT an accessory sleeve
    assert _sealed("EVOLVING SKIES Sleeved Booster Pack") is True


def test_catchall_tagged_etb_stays_sealed():
    # real sealed ETB swept into a catch-all tag dump incl. accessories/merch:
    # title-based guard must NOT drop it (tag-based exclusion would)
    tags = ["pokemon", "accessories", "merch", "sealed", "japanese", "mtg"]
    assert _sealed("Perfect Order Elite Trainer Box - ME03", tags) is True


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


def test_fetch_products_warns_on_nonempty_html_no_products(caplog):
    html = "<html><body>totally different layout, no next data</body></html>"

    def fake_get(url, params=None, as_text=False):
        return html

    with caplog.at_level(logging.WARNING):
        prods = rarecandy.fetch_products(_store(), fake_get)
    assert prods == []
    assert any("no products extracted" in r.message for r in caplog.records)
    assert any("rarecandy" in r.getMessage() for r in caplog.records)
