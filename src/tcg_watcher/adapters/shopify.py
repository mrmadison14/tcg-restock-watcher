from __future__ import annotations
from ..config import Store
from ..models import Product

_SEALED_MARKERS = (
    "booster box", "elite trainer", "etb", "booster bundle", "bundle",
    "collection", "case", "tin", "blister", "booster pack",
)
_PREORDER_MARKERS = ("preorder", "pre-order", "pre order")
_PAGE_LIMIT = 250
_MAX_PAGES = 50


def _has_marker(text: str, markers: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(m in low for m in markers)


def _is_preorder(title: str, tags: tuple[str, ...]) -> bool:
    blob = title + " " + " ".join(tags)
    return _has_marker(blob, _PREORDER_MARKERS)


def _to_products(store: Store, it: dict, franchise: str | None) -> list[Product]:
    handle = it.get("handle", "")
    url = f"{store.base_url}/products/{handle}"
    images = it.get("images") or []
    image = images[0].get("src") if images else None
    tags_raw = it.get("tags", [])
    tags = tuple(tags_raw) if isinstance(tags_raw, list) else tuple(
        t.strip() for t in str(tags_raw).split(",") if t.strip()
    )
    base_title = it.get("title", "")
    product_type = it.get("product_type", "") or ""
    preorder = _is_preorder(base_title, tags)
    sealed = _has_marker(base_title + " " + product_type, _SEALED_MARKERS)
    out: list[Product] = []
    for v in it.get("variants", []):
        vtitle = v.get("title")
        title = base_title if vtitle in (None, "Default Title") else f"{base_title} - {vtitle}"
        out.append(
            Product(
                store=store.key,
                product_id=str(it.get("id")),
                variant_id=str(v.get("id")),
                title=title,
                price=float(v.get("price")),
                currency=store.currency,
                in_stock=bool(v.get("available")),
                url=url,
                image=image,
                product_type=product_type,
                tags=tags,
                is_preorder=preorder,
                is_sealed=sealed,
                franchise=franchise,
            )
        )
    return out


def _fetch_path(store: Store, http_get, path: str, franchise: str | None) -> list[Product]:
    out: list[Product] = []
    page = 1
    while page <= _MAX_PAGES:
        data = http_get(f"{store.base_url}{path}", params={"limit": _PAGE_LIMIT, "page": page})
        items = data.get("products", [])
        if not items:
            break
        for it in items:
            out.extend(_to_products(store, it, franchise))
        if len(items) < _PAGE_LIMIT:
            break
        page += 1
    return out


def fetch_products(store: Store, http_get) -> list[Product]:
    if store.collections:
        out: list[Product] = []
        seen: set[str] = set()
        for spec in store.collections:
            franchise, _, handle = spec.partition(":")
            franchise = franchise.strip() or None
            handle = handle.strip()
            for p in _fetch_path(store, http_get, f"/collections/{handle}/products.json", franchise):
                if p.variant_id not in seen:
                    seen.add(p.variant_id)
                    out.append(p)
        return out
    return _fetch_path(store, http_get, "/products.json", None)
