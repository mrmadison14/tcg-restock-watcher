import json
from pathlib import Path

import pytest

from tcg_watcher.config import Store
from tcg_watcher.adapters import rarecandy
from tcg_watcher.filtering import filter_franchises, keep_sealed

FIXTURE = Path(__file__).parent / "fixtures" / "rarecandy_catalog.json"


def _store():
    return Store(key="rarecandy", base_url="https://rarecandy.com", platform="rarecandy", currency="USD")


def _catalog():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _page(rarefinds, total, page=1, pagesize=20):
    return {"data": {"rareFindCatalog": {
        "count": len(rarefinds), "page": page, "pageSize": pagesize,
        "totalCount": total, "showStoreName": True, "rareFinds": rarefinds,
    }}}


def _fake_http(pages):
    calls = []

    def get(url, params=None, as_text=False):
        raise AssertionError("rarecandy must not use plain GET")

    def post_json(url, body, params=None, headers=None):
        calls.append({"url": url, "body": body})
        i = body["variables"]["page"] - 1
        if i < len(pages):
            return pages[i]
        return _page([], pages[0]["data"]["rareFindCatalog"]["totalCount"], page=i + 1)

    get.post_json = post_json
    return get, calls


def _by_vid():
    http, _ = _fake_http([_catalog()])
    return {p.variant_id: p for p in rarecandy.fetch_products(_store(), http)}


def _rf(name, tags, quantity=1, rid=1, slug="s-slug", store_slug="somestore", preorder=False, price=1.0):
    return {
        "id": rid, "slug": slug,
        "store": {"id": 5, "name": "Some Store", "slug": store_slug},
        "product": {"id": 900 + rid, "name": name, "price": price, "quantity": quantity,
                    "tags": list(tags), "categories": list(tags), "isPreorder": preorder,
                    "thumbnail": {"thumbnail": "https://img.example/x.png"}},
    }


def _sealed(name, tags=("pokemon", "sealed")):
    return rarecandy.products_from_catalog(_store(), [_rf(name, list(tags))])[0].is_sealed


# --- field mapping ---

def test_maps_core_fields():
    p = _by_vid()["217110"]
    assert p.product_id == "298485"
    assert p.variant_id == "217110"
    assert p.title == "Gem 3 Booster Box (S-Chinese)"
    assert p.price == 89.99
    assert p.currency == "USD"
    assert p.in_stock is True
    assert p.is_preorder is False
    assert p.is_sealed is True
    assert p.url == "https://rarecandy.com/pokejpn/shop/gem-3-booster-box-s-chinese-d03b8cba"
    assert p.image == "https://images.rarecandy.com/tr:n-thumbnail/stores/38/inventory/17821774671691.jpeg"


def test_franchise_tags_normalized():
    assert "one piece" in _by_vid()["217323"].tags


def test_out_of_stock_quantity_zero():
    assert _by_vid()["217246"].in_stock is False


def test_preorder_flag_from_is_preorder():
    assert _by_vid()["217246"].is_preorder is True


def test_singles_tag_excluded_from_sealed():
    assert _by_vid()["217323"].is_sealed is False


def test_sealed_without_singles_is_sealed():
    assert _by_vid()["18610"].is_sealed is True


def test_url_uses_store_slug_and_rarefind_slug():
    assert _by_vid()["18610"].url == (
        "https://rarecandy.com/otakuanimegoods/shop/"
        "pokemon-center-tohoku-hiroshima-and-fukuoka-special-boxes-2025-jp-52f47bd9"
    )


# --- sealed heuristic (carried over from the Apollo-era contract) ---

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
    assert _sealed("EVOLVING SKIES Sleeved Booster Pack") is True


def test_catchall_tagged_etb_stays_sealed():
    tags = ["pokemon", "accessories", "merch", "sealed", "japanese", "mtg"]
    assert _sealed("Perfect Order Elite Trainer Box - ME03", tags) is True


def test_unresolvable_store_slug_skips_listing():
    rf = _rf("X", ["pokemon", "sealed"])
    rf["store"] = None
    assert rarecandy.products_from_catalog(_store(), [rf]) == []


# --- franchise filtering happens in the runner, not the adapter ---

def test_adapter_returns_nonfranchise_sealed_runner_drops_it():
    # MTG sealed: adapter keeps it (is_sealed True); runner's franchise filter drops it
    mtg = _by_vid()["19192"]
    assert mtg.is_sealed is True
    synonyms = {"pokemon": ("pokemon", "pokémon"),
                "one piece": ("one piece", "one-piece"),
                "dragon ball": ("dragon ball", "dragonball")}
    watched = keep_sealed(filter_franchises(list(_by_vid().values()), synonyms))
    titles = {p.title for p in watched}
    assert "OUTLAWS OF THUNDER JUNCTION Magic The Gathering Play Booster Pack" not in titles
    assert "Gem 3 Booster Box (S-Chinese)" in titles


# --- pagination ---

def test_fetch_paginates_and_stops_on_empty_page():
    p1 = _page([_rf("A", ["pokemon", "sealed"], rid=1), _rf("B", ["pokemon", "sealed"], rid=2)], total=999)
    http, calls = _fake_http([p1])  # page 2 auto-returns empty -> stop
    prods = rarecandy.fetch_products(_store(), http)
    assert len(prods) == 2
    assert len(calls) == 2


def test_fetch_stops_at_total_count():
    pages = [
        _page([_rf(f"P{i}", ["pokemon", "sealed"], rid=i) for i in range(0, 20)], total=40, page=1),
        _page([_rf(f"P{i}", ["pokemon", "sealed"], rid=i) for i in range(20, 40)], total=40, page=2),
    ]
    http, calls = _fake_http(pages)
    prods = rarecandy.fetch_products(_store(), http)
    assert len(prods) == 40
    assert len(calls) == 2  # stops once seen >= totalCount, no 3rd request


def test_fetch_respects_max_pages_cap():
    # every page returns 20 fresh ids and totalCount is effectively unbounded
    pages = [_page([_rf(f"p{pg}_{i}", ["pokemon", "sealed"], rid=pg * 100 + i) for i in range(20)],
                   total=10 ** 9, page=pg + 1) for pg in range(rarecandy._MAX_PAGES + 5)]
    http, calls = _fake_http(pages)
    rarecandy.fetch_products(_store(), http)
    assert len(calls) == rarecandy._MAX_PAGES


def test_fetch_dedupes_by_rarefind_id():
    shared = _rf("dup", ["pokemon", "sealed"], rid=7)
    pages = [_page([shared, _rf("a", ["pokemon", "sealed"], rid=1)], total=999, page=1),
             _page([shared, _rf("b", ["pokemon", "sealed"], rid=2)], total=999, page=2)]
    http, _ = _fake_http(pages)  # page 3 empty
    prods = rarecandy.fetch_products(_store(), http)
    assert len({p.variant_id for p in prods}) == 3


def test_fetch_sends_sealed_newest_query():
    http, calls = _fake_http([_catalog()])
    rarecandy.fetch_products(_store(), http)
    body = calls[0]["body"]
    assert calls[0]["url"] == "https://api.rarecandy.com/graphql"
    assert body["operationName"] == "RareFindCatalog"
    assert body["variables"]["page"] == 1
    assert body["variables"]["filters"] == {"categories": ["sealed"], "sortBy": "newest"}


def test_graphql_errors_raise():
    def get(url, params=None, as_text=False):
        raise AssertionError("no GET")

    def post_json(url, body, params=None, headers=None):
        return {"errors": [{"message": "An unknown error has occurred", "code": "UNKNOWN"}]}

    get.post_json = post_json
    with pytest.raises(RuntimeError):
        rarecandy.fetch_products(_store(), get)


def test_registered_in_runner():
    from tcg_watcher import runner
    assert runner._ADAPTERS["rarecandy"] is rarecandy.fetch_products
