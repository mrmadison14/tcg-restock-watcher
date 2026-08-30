import json
from pathlib import Path

import pytest

from tcg_watcher.config import Store
from tcg_watcher.adapters import alicecollectibles
from tcg_watcher.filtering import filter_franchises, keep_sealed

FIXTURE = Path(__file__).parent / "fixtures" / "alicecollectibles_search.html"


def _store():
    return Store(key="alicecollectibles", base_url="https://alicecollectibles.com",
                 platform="alicecollectibles", currency="USD")


def _fake_http(text):
    calls = []

    def get(url, params=None, as_text=False):
        calls.append({"url": url, "as_text": as_text})
        return text if as_text else json.loads(text)

    def post_json(url, body, params=None, headers=None):
        raise AssertionError("alicecollectibles must not POST")

    get.post_json = post_json
    return get, calls


def _by_id(html=None):
    http, _ = _fake_http(html if html is not None else FIXTURE.read_text(encoding="utf-8"))
    return {p.product_id: p for p in alicecollectibles.fetch_products(_store(), http)}


def _rec(pid, qty=1, status="ACTIVE", franchise="POKEMON", card=None, images=True):
    return {
        "id": pid, "sku": f"SKU-{pid}", "slug": f"slug-{pid}", "title": f"Title {pid}",
        "description": "d", "franchise": franchise, "productType": "BOOSTER_BOX",
        "language": "EN", "setName": "S", "productSets": [], "cardNumber": card,
        "priceCents": 1000, "quantity": qty, "status": status, "featured": False,
        "createdAt": "$D2026-07-30T18:22:50.702Z", "updatedAt": "$D2026-08-30T17:58:53.628Z",
        "images": [{"objectKey": f"products/{pid}/x.jpg", "alt": "a"}] if images else [],
        "priceHistory": [],
    }


def _page(records):
    raw = '5:["$","div",null,{"children":[' + ",".join(
        '["$","$L28","%s",%s]' % (r["id"], json.dumps({"product": r}, separators=(",", ":")))
        for r in records) + "]}]"
    escaped = json.dumps(raw)[1:-1]
    return ('<html><body><script>self.__next_f.push([0])</script>'
            f'<script>self.__next_f.push([1,"{escaped}"])</script></body></html>')


# --- field mapping ---

def test_maps_core_fields():
    p = _by_id()["aaa111"]
    assert p.product_id == "aaa111"
    assert p.variant_id == "aaa111"
    assert p.title == "Test Booster Box"
    assert p.price == 129.99
    assert p.currency == "USD"
    assert p.in_stock is True
    assert p.is_preorder is False
    assert p.is_sealed is True
    assert p.product_type == "BOOSTER_BOX"
    assert p.tags == ("pokemon",)
    assert p.url == "https://alicecollectibles.com/products/pokemon-tcg-test-booster-box"
    assert p.image == "https://alicecollectibles.com/api/images/products/aaa111/img-aaa111.jpg"


def test_record_split_across_chunks_parses():
    assert _by_id()["bbb222"].title == "Test Elite Trainer Box"


def test_zero_quantity_out_of_stock():
    assert _by_id()["bbb222"].in_stock is False


def test_sold_status_out_of_stock():
    assert _by_id()["ccc333"].in_stock is False


def test_card_number_not_sealed():
    assert _by_id()["ddd444"].is_sealed is False


def test_no_images_gives_none():
    assert _by_id()["eee555"].image is None


def test_franchise_underscore_normalized():
    assert _by_id()["eee555"].tags == ("one piece",)


# --- franchise filtering happens in the runner, not the adapter ---

def test_runner_filters_keep_sealed_franchise_matches():
    synonyms = {"pokemon": ("pokemon", "pokémon"),
                "one piece": ("one piece", "one-piece"),
                "dragon ball": ("dragon ball", "dragonball")}
    watched = keep_sealed(filter_franchises(list(_by_id().values()), synonyms))
    ids = {p.product_id for p in watched}
    assert ids == {"aaa111", "bbb222", "ccc333", "eee555"}  # single card ddd444 dropped


# --- fetch behavior ---

def test_fetches_search_page_as_text():
    http, calls = _fake_http(FIXTURE.read_text(encoding="utf-8"))
    alicecollectibles.fetch_products(_store(), http)
    assert calls == [{"url": "https://alicecollectibles.com/search?q=", "as_text": True}]


def test_dedupes_by_product_id():
    dup = _rec("x1")
    prods = _by_id(_page([dup, dup, _rec("x2")]))
    assert set(prods) == {"x1", "x2"}


def test_no_flight_chunks_raises():
    with pytest.raises(RuntimeError):
        _by_id("<html><body>maintenance</body></html>")


def test_no_product_records_raises():
    with pytest.raises(RuntimeError):
        _by_id(_page([]))


def test_registered_in_runner():
    from tcg_watcher import runner
    assert runner._ADAPTERS["alicecollectibles"] is alicecollectibles.fetch_products
