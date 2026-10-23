from __future__ import annotations
from ..config import Store
from ..models import Product

_STORES_APP_ID = "1380b703-ce81-ff05-f115-39571d94dfcd"
_ALL_PRODUCTS_CATEGORY = "00000000-000000-000000-000000000001"
_MEDIA_BASE = "https://static.wixstatic.com/media/"
_PAGE_LIMIT = 100
_MAX_PAGES = 20
_SEALED_MARKERS = (
    "booster box", "elite trainer", "etb", "booster bundle",
    "collection", "case", "tin", "blister", "booster pack", "trainer box",
)
_PREORDER_MARKERS = ("preorder", "pre-order", "pre order")
_QUERY = """query getFilteredProducts($mainCollectionId: String!, $offset: Int, $limit: Int) {
  catalog {
    category(categoryId: $mainCollectionId) {
      productsWithMetaData(limit: $limit, offset: $offset, onlyVisible: true) {
        totalCount
        list { id name urlPart price isInStock ribbon sku productType media { url } }
      }
    }
  }
}"""


def _has_marker(text: str, markers: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(m in low for m in markers)


def _to_product(store: Store, it: dict, franchise: str | None) -> Product:
    name = it["name"]
    ribbon = it.get("ribbon") or ""
    media = it.get("media") or []
    return Product(
        store=store.key,
        product_id=it["id"],
        variant_id=it["id"],
        title=name,
        price=float(it["price"]),
        currency=store.currency,
        in_stock=bool(it["isInStock"]),
        url=f"{store.base_url}/product-page/{it['urlPart']}",
        image=_MEDIA_BASE + media[0]["url"] if media else None,
        product_type=it.get("productType") or "",
        tags=(franchise,) if franchise else (),
        is_preorder=_has_marker(f"{name} {ribbon}", _PREORDER_MARKERS),
        is_sealed=_has_marker(name, _SEALED_MARKERS),
        franchise=franchise,
    )


def _mint_token(store: Store, http_get) -> str:
    data = http_get(f"{store.base_url}/_api/v1/access-tokens")
    return data["apps"][_STORES_APP_ID]["instance"]


def _fetch_category(store: Store, http_get, token: str, category_id: str,
                    franchise: str | None) -> list[Product]:
    out: list[Product] = []
    offset = 0
    for _ in range(_MAX_PAGES):
        payload = http_get.post_json(
            f"{store.base_url}/_api/wix-ecommerce-storefront-web/api",
            {
                "query": _QUERY,
                "variables": {
                    "mainCollectionId": category_id,
                    "offset": offset,
                    "limit": _PAGE_LIMIT,
                },
            },
            params={"o": "getFilteredProducts", "s": "WixStoresWebClient"},
            headers={"Authorization": token},
        )
        if payload.get("errors"):
            raise RuntimeError(f"wix graphql errors: {payload['errors']}")
        meta = payload["data"]["catalog"]["category"]["productsWithMetaData"]
        if offset == 0 and meta["totalCount"] == 0:
            # A wrong category id answers with no error, so fail loudly
            # rather than seed an empty snapshot.
            raise RuntimeError(f"wix category {category_id} reported totalCount 0")
        items = meta["list"]
        out.extend(_to_product(store, it, franchise) for it in items)
        offset += _PAGE_LIMIT
        if not items or offset >= meta["totalCount"]:
            break
    return out


def fetch_products(store: Store, http_get) -> list[Product]:
    token = _mint_token(store, http_get)
    if not store.collections:
        return _fetch_category(store, http_get, token, _ALL_PRODUCTS_CATEGORY, store.franchise)
    # Wix sites can give "All Products" its own id, so a store lists its
    # categories as "<franchise>:<category-id>", like Shopify handles.
    out: list[Product] = []
    seen: set[str] = set()
    for spec in store.collections:
        franchise, _, category_id = spec.partition(":")
        for p in _fetch_category(store, http_get, token, category_id.strip(),
                                 franchise.strip() or None):
            if p.variant_id not in seen:
                seen.add(p.variant_id)
                out.append(p)
    return out
