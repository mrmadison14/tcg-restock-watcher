from __future__ import annotations
from ..config import Store
from ..models import Product

_API_URL = "https://api.rarecandy.com/graphql"
_FILTERS = {"categories": ["sealed"], "sortBy": "newest"}
_MAX_PAGES = 40
_FRANCHISE_TAG = {"onepiece": "one piece", "dbz": "dragon ball"}
_ACCESSORY_MARKERS = (
    "playmat", "play mat", "binder", "toploader", "top loader",
    "deck box", "deckbox", "portfolio", "penny sleeve", "card sleeves",
    "deck protector", "dice set", "damage counter",
)
_QUERY = """query RareFindCatalog($page: Int!, $filters: RareFindFilters) {
  rareFindCatalog(page: $page, filters: $filters) {
    totalCount
    rareFinds {
      id slug
      store { id name slug }
      product { id name price quantity tags categories isPreorder thumbnail { thumbnail } }
    }
  }
}"""


def _is_accessory(name: str) -> bool:
    low = name.lower()
    return any(m in low for m in _ACCESSORY_MARKERS)


def _norm_tags(tags) -> tuple[str, ...]:
    return tuple(_FRANCHISE_TAG.get(t, t) for t in tags)


def products_from_catalog(store: Store, rarefinds: list[dict]) -> list[Product]:
    out: list[Product] = []
    for rf in rarefinds:
        product = rf.get("product")
        seller = rf.get("store")
        if not product or not seller or not seller.get("slug"):
            continue
        tags = _norm_tags(product.get("tags") or ())
        name = product.get("name", "")
        thumb = product.get("thumbnail") or {}
        out.append(
            Product(
                store=store.key,
                product_id=str(product["id"]),
                variant_id=str(rf["id"]),
                title=name,
                price=float(product["price"]),
                currency=store.currency,
                in_stock=(product.get("quantity") or 0) > 0,
                url=f"{store.base_url}/{seller['slug']}/shop/{rf['slug']}",
                image=thumb.get("thumbnail"),
                tags=tags,
                is_preorder=bool(product.get("isPreorder")),
                is_sealed="sealed" in tags and "singles" not in tags and not _is_accessory(name),
            )
        )
    return out


def fetch_products(store: Store, http_get) -> list[Product]:
    seen: set[str] = set()
    rarefinds: list[dict] = []
    for page in range(1, _MAX_PAGES + 1):
        payload = http_get.post_json(
            _API_URL,
            {"operationName": "RareFindCatalog", "query": _QUERY,
             "variables": {"page": page, "filters": _FILTERS}},
        )
        if payload.get("errors"):
            raise RuntimeError(f"rarecandy graphql errors: {payload['errors']}")
        catalog = payload["data"]["rareFindCatalog"]
        batch = catalog.get("rareFinds") or []
        if not batch:
            break
        for rf in batch:
            vid = str(rf["id"])
            if vid not in seen:
                seen.add(vid)
                rarefinds.append(rf)
        total = catalog.get("totalCount")
        if total is not None and len(seen) >= total:
            break
    return products_from_catalog(store, rarefinds)
