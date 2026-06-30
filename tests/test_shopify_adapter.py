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
