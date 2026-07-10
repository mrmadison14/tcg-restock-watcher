import pytest
from tcg_watcher.config import Store
from tcg_watcher.adapters.shopify import fetch_products

STORE = Store(key="demo", base_url="https://demo.test", platform="shopify", currency="USD")

PAGE1 = {
    "products": [
        {
            "id": 100, "handle": "surging-sparks-etb", "title": "Surging Sparks Elite Trainer Box",
            "product_type": "Sealed Pokemon", "tags": ["Pokemon", "Preorder"],
            "images": [{"src": "https://img/etb.jpg"}],
            "variants": [
                {"id": 9001, "title": "Default Title", "price": "59.99", "available": False},
            ],
        },
        {
            "id": 101, "handle": "op-romance-dawn-bb", "title": "One Piece Romance Dawn Booster Box",
            "product_type": "Sealed", "tags": ["One Piece"], "images": [],
            "variants": [
                {"id": 9002, "title": "English", "price": "120.00", "available": True},
                {"id": 9003, "title": "Japanese", "price": "95.00", "available": True},
            ],
        },
    ]
}

def make_http_get(pages):
    def http_get(url, params=None):
        page = (params or {}).get("page", 1)
        return pages.get(page, {"products": []})
    return http_get

def test_fetch_maps_variants_and_flags():
    http_get = make_http_get({1: PAGE1})
    products = fetch_products(STORE, http_get)
    assert len(products) == 3  # 1 + 2 variants
    etb = products[0]
    assert etb.store == "demo"
    assert etb.variant_id == "9001"
    assert etb.price == 59.99
    assert etb.in_stock is False
    assert etb.url == "https://demo.test/products/surging-sparks-etb"
    assert etb.image == "https://img/etb.jpg"
    assert etb.is_preorder is True          # "Preorder" tag
    assert etb.is_sealed is True            # "Elite Trainer Box" in title
    assert "Pokemon" in etb.tags
    # variant title appended when not "Default Title"
    jp = products[2]
    assert jp.title.endswith("Japanese")
    assert jp.image is None

def test_pagination_stops_on_empty():
    http_get = make_http_get({1: PAGE1, 2: {"products": []}})
    products = fetch_products(STORE, http_get)
    assert len(products) == 3


def test_collection_mode_tags_franchise_and_dedups():
    store = Store(key="c", base_url="https://c.test", platform="shopify", currency="USD",
                  collections=("pokemon:pk-sealed", "one piece:op-sealed"))
    pk = {"id": 1, "handle": "etb", "title": "Surging Sparks ETB", "product_type": "", "tags": [], "images": [],
          "variants": [{"id": 11, "title": "Default Title", "price": "50.00", "available": True}]}
    op = {"id": 2, "handle": "opbb", "title": "OP Booster Box", "product_type": "", "tags": [], "images": [],
          "variants": [{"id": 22, "title": "Default Title", "price": "100.00", "available": True}]}
    def http_get(url, params=None):
        if (params or {}).get("page", 1) != 1:
            return {"products": []}
        if "pk-sealed" in url:
            return {"products": [pk, op]}
        if "op-sealed" in url:
            return {"products": [op]}
        return {"products": []}
    prods = fetch_products(store, http_get)
    fr = {p.variant_id: p.franchise for p in prods}
    assert fr["11"] == "pokemon"
    assert fr["22"] == "pokemon"
    assert len(prods) == 2


def test_full_crawl_early_stops_on_short_page():
    store = Store(key="s", base_url="https://s.test", platform="shopify", currency="USD")
    calls = []
    def http_get(url, params=None):
        page = (params or {}).get("page", 1); calls.append(page)
        if page == 1:
            return {"products": [{"id": 1, "handle": "h", "title": "Booster Box", "product_type": "", "tags": [], "images": [],
                    "variants": [{"id": 9, "title": "Default Title", "price": "1.00", "available": True}]}]}
        return {"products": []}
    fetch_products(store, http_get)
    assert calls == [1]


def test_bare_bundle_marker_does_not_flag_sealed():
    store = Store(key="d", base_url="https://d.test", platform="shopify", currency="USD")
    page = {"products": [
        {"id": 200, "handle": "sleeve-bundle", "title": "Ultra Pro Card Sleeve Bundle",
         "product_type": "Accessories", "tags": [], "images": [],
         "variants": [{"id": 8001, "title": "Default Title", "price": "9.99", "available": True}]},
        {"id": 201, "handle": "booster-bundle", "title": "Prismatic Evolutions Booster Bundle",
         "product_type": "", "tags": [], "images": [],
         "variants": [{"id": 8002, "title": "Default Title", "price": "26.99", "available": True}]},
    ]}
    prods = fetch_products(store, make_http_get({1: page}))
    sealed = {p.variant_id: p.is_sealed for p in prods}
    assert sealed["8001"] is False   # bare "bundle" must not flag sealed
    assert sealed["8002"] is True    # "booster bundle" still flags sealed


def test_marker_matching_respects_word_boundaries():
    # "tin" must not match inside "setting"; a real "Tin" must still flag sealed.
    store = Store(key="d", base_url="https://d.test", platform="shopify", currency="USD")
    page = {"products": [
        {"id": 1, "handle": "a", "title": "Figuarts ZERO Luffy Setting Sail for the New World",
         "product_type": "Figures", "tags": [], "images": [],
         "variants": [{"id": 1, "title": "Default Title", "price": "50", "available": True}]},
        {"id": 2, "handle": "b", "title": "Mega Moonlit Tin", "product_type": "", "tags": [], "images": [],
         "variants": [{"id": 2, "title": "Default Title", "price": "25", "available": True}]},
        {"id": 3, "handle": "c", "title": "Vintage Showcase Poster", "product_type": "", "tags": [], "images": [],
         "variants": [{"id": 3, "title": "Default Title", "price": "10", "available": True}]},
    ]}
    sealed = {p.variant_id: p.is_sealed for p in fetch_products(store, make_http_get({1: page}))}
    assert sealed["1"] is False   # "setting" must not match "tin"
    assert sealed["2"] is True    # real "Tin" still sealed
    assert sealed["3"] is False   # "showcase" must not match "case"


def test_missing_product_id_crashes():
    store = Store(key="d", base_url="https://d.test", platform="shopify", currency="USD")
    page = {"products": [
        {"handle": "no-id", "title": "Mystery Booster Box", "product_type": "", "tags": [], "images": [],
         "variants": [{"id": 7001, "title": "Default Title", "price": "1.00", "available": True}]},
    ]}
    with pytest.raises(KeyError):
        fetch_products(store, make_http_get({1: page}))


def test_missing_variant_id_crashes():
    store = Store(key="d", base_url="https://d.test", platform="shopify", currency="USD")
    page = {"products": [
        {"id": 300, "handle": "v-no-id", "title": "Mystery Booster Box", "product_type": "", "tags": [], "images": [],
         "variants": [{"title": "Default Title", "price": "1.00", "available": True}]},
    ]}
    with pytest.raises(KeyError):
        fetch_products(store, make_http_get({1: page}))
