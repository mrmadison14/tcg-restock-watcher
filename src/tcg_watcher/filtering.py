from __future__ import annotations
from dataclasses import replace
from .models import Product


def _match(product: Product, synonyms: dict[str, tuple[str, ...]]) -> str | None:
    haystacks = [
        " ".join(product.tags).lower(),
        product.product_type.lower(),
        product.title.lower(),
    ]
    for source in haystacks:
        for franchise, syns in synonyms.items():
            if any(s in source for s in syns):
                return franchise
    return None


def filter_franchises(
    products: list[Product], synonyms: dict[str, tuple[str, ...]]
) -> list[Product]:
    out: list[Product] = []
    for p in products:
        fr = _match(p, synonyms)
        if fr is not None:
            out.append(replace(p, franchise=fr))
    return out
