import json
from pathlib import Path

import pytest

from tcg_watcher.config import Store
from tcg_watcher.adapters import wix
from tcg_watcher.filtering import filter_franchises, keep_sealed

FIXTURES = Path(__file__).parent / "fixtures"


def _store(franchise="pokemon"):
    return Store(key="bulbacards", base_url="https://bulbacards.com", platform="wix",
                 currency="USD", franchise=franchise)


def _fake_http(pages=None):
    tokens = json.loads((FIXTURES / "wix_access_tokens.json").read_text(encoding="utf-8"))
    if pages is None:
        pages = [json.loads((FIXTURES / "wix_graphql_page.json").read_text(encoding="utf-8"))]
    calls = {"gets": [], "posts": []}

    def get(url, params=None, as_text=False):
        calls["gets"].append(url)
        return tokens

    def post_json(url, body, params=None, headers=None):
        calls["posts"].append({"url": url, "body": body, "params": params, "headers": headers})
        return pages[len(calls["posts"]) - 1]

    get.post_json = post_json
    return get, calls


def _page(n_items, total, start=0):
    return {"data": {"catalog": {"category": {"productsWithMetaData": {
        "totalCount": total,
        "list": [
            {"id": f"id-{start + i}", "name": f"Item {start + i} Booster Box",
             "urlPart": f"item-{start + i}", "price": 1.0, "isInStock": True,
             "ribbon": "", "media": []}
            for i in range(n_items)
        ],
    }}}}}


def _by_vid(franchise="pokemon"):
    http, _ = _fake_http()
    return {p.variant_id: p for p in wix.fetch_products(_store(franchise), http)}


def test_maps_core_fields():
    p = _by_vid()["ec9519ff-e220-8123-c33a-f2d2b5c26a04"]
    assert p.store == "bulbacards"
    assert p.product_id == "ec9519ff-e220-8123-c33a-f2d2b5c26a04"
    assert p.title == "Mega Greninja ex Premium Collection"
    assert p.price == 49.99
    assert p.currency == "USD"
    assert p.in_stock is True
    assert p.url == "https://bulbacards.com/product-page/mega-greninja-ex-premium-collection"
    assert p.image == "https://static.wixstatic.com/media/6e6f92_e74d1dce4a304f4b8f7d3c13a74da213~mv2.png"
    assert p.is_sealed is True
    assert p.is_preorder is False
    assert p.tags == ("pokemon",)


def test_ribbon_preorder_detected():
    p = _by_vid()["680f8573-3b4f-698f-39ea-acfdff6f30d0"]
    assert p.is_preorder is True
    assert p.is_sealed is False


def test_name_preorder_detected():
    p = _by_vid()["201a7e40-e0cd-357f-a83c-427bffab31cc"]
    assert p.is_preorder is True
    assert p.in_stock is False


def test_out_of_stock_booster_box():
    p = _by_vid()["ce74181d-0326-b11d-2e53-112f104dcea7"]
    assert p.in_stock is False
    assert p.is_sealed is True


def test_graded_single_not_sealed():
    p = _by_vid()["01977a10-212a-5c10-e119-b4793217d084"]
    assert p.is_sealed is False


def test_elitetrainer_typo_matches_sealed():
    page = _page(0, 1)
    page["data"]["catalog"]["category"]["productsWithMetaData"]["list"] = [
        {"id": "x1", "name": "Pitch Black EliteTrainer Box", "urlPart": "x1",
         "price": 59.0, "isInStock": True, "ribbon": "", "media": []}
    ]
    http, _ = _fake_http([page])
    products = wix.fetch_products(_store(), http)
    assert products[0].is_sealed is True


def test_no_franchise_config_means_no_tags():
    p = _by_vid(franchise=None)["ec9519ff-e220-8123-c33a-f2d2b5c26a04"]
    assert p.tags == ()


def test_auth_uses_minted_token():
    http, calls = _fake_http()
    wix.fetch_products(_store(), http)
    assert calls["gets"] == ["https://bulbacards.com/_api/v1/access-tokens"]
    post = calls["posts"][0]
    assert post["url"] == "https://bulbacards.com/_api/wix-ecommerce-storefront-web/api"
    assert post["headers"] == {"Authorization": "test-instance-token-not-real"}
    assert post["params"] == {"o": "getFilteredProducts", "s": "WixStoresWebClient"}


def test_paginates_until_total_count():
    pages = [_page(100, 250, 0), _page(100, 250, 100), _page(50, 250, 200)]
    http, calls = _fake_http(pages)
    products = wix.fetch_products(_store(), http)
    assert len(products) == 250
    offsets = [p["body"]["variables"]["offset"] for p in calls["posts"]]
    assert offsets == [0, 100, 200]


def test_page_cap_bounds_crawl():
    pages = [_page(100, 999999, i * 100) for i in range(wix._MAX_PAGES + 5)]
    http, calls = _fake_http(pages)
    products = wix.fetch_products(_store(), http)
    assert len(calls["posts"]) == wix._MAX_PAGES
    assert len(products) == 100 * wix._MAX_PAGES


def test_empty_page_stops():
    http, calls = _fake_http([_page(0, 500)])
    assert wix.fetch_products(_store(), http) == []
    assert len(calls["posts"]) == 1


def test_graphql_errors_raise():
    http, _ = _fake_http([{"errors": [{"message": "boom"}]}])
    with pytest.raises(RuntimeError):
        wix.fetch_products(_store(), http)


def test_stable_ids_across_fetches():
    http1, _ = _fake_http()
    http2, _ = _fake_http()
    ids1 = [p.variant_id for p in wix.fetch_products(_store(), http1)]
    ids2 = [p.variant_id for p in wix.fetch_products(_store(), http2)]
    assert ids1 == ids2


def test_runner_filter_keeps_blanket_tagged_sealed_only():
    http, _ = _fake_http()
    products = wix.fetch_products(_store(), http)
    synonyms = {"pokemon": ("pokemon", "pokémon")}
    watched = keep_sealed(filter_franchises(products, synonyms))
    titles = sorted(p.title for p in watched)
    assert titles == ["Mega Greninja ex Premium Collection", "Pitch Black Booster Box"]
    assert all(p.franchise == "pokemon" for p in watched)


def test_registered_in_runner():
    from tcg_watcher import runner
    assert runner._ADAPTERS["wix"] is wix.fetch_products
