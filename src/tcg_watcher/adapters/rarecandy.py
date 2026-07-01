from __future__ import annotations
import json
import re
from ..config import Store
from ..models import Product

_SURFACES = ("/shop", "/discover")
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
_FRANCHISE_TAG = {"onepiece": "one piece", "dbz": "dragon ball"}


def extract_apollo(html: str) -> dict:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return {}
    data = json.loads(m.group(1))
    return data.get("props", {}).get("pageProps", {}).get("__APOLLO_STATE__", {})


def _norm_tags(tags) -> tuple[str, ...]:
    return tuple(_FRANCHISE_TAG.get(t, t) for t in tags)


def products_from_apollo(store: Store, apollo: dict) -> list[Product]:
    out: list[Product] = []
    for key, rf in apollo.items():
        if not key.startswith("RareFind:"):
            continue
        ref = (rf.get("product") or {}).get("__ref")
        product = apollo.get(ref) if ref else None
        if product is None:
            continue
        tags = _norm_tags(product.get("tags") or ())
        thumb = product.get("thumbnail") or {}
        out.append(
            Product(
                store=store.key,
                product_id=str(product["id"]),
                variant_id=str(rf["id"]),
                title=product.get("name", ""),
                price=float(product["price"]),
                currency=store.currency,
                in_stock=(product.get("quantity") or 0) > 0,
                url=f"{store.base_url}/{rf['slug']}",
                image=thumb.get("thumbnail"),
                tags=tags,
                is_preorder=bool(product.get("isPreorder")),
                is_sealed="sealed" in tags,
            )
        )
    return out


def fetch_products(store: Store, http_get) -> list[Product]:
    seen: set[str] = set()
    out: list[Product] = []
    for surface in _SURFACES:
        apollo = extract_apollo(http_get(f"{store.base_url}{surface}", as_text=True))
        for p in products_from_apollo(store, apollo):
            if p.variant_id not in seen:
                seen.add(p.variant_id)
                out.append(p)
    return out
