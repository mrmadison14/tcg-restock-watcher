from __future__ import annotations
from .match import normalize

_SEALED_MARKERS = (
    "booster box", "elite trainer", "etb", "booster bundle", "booster pack",
    "collection", "tin", "blister", "case", "premium",
)


def _market_for(pid, price_rows: list[dict]):
    normal = None
    fallback = None
    for pr in price_rows:
        if pr.get("productId") != pid or pr.get("marketPrice") is None:
            continue
        if pr.get("subTypeName") == "Normal":
            normal = pr["marketPrice"]
        elif fallback is None:
            fallback = pr["marketPrice"]
    return normal if normal is not None else fallback


def sealed_entries(products: list[dict], prices: list[dict]) -> dict:
    out: dict = {}
    for p in products:
        name = p.get("name", "")
        low = name.lower()
        if not any(m in low for m in _SEALED_MARKERS):
            continue
        mp = _market_for(p["productId"], prices)
        if mp is None:
            continue
        out[normalize(name)] = {"market_usd": mp, "display_name": name}
    return out
