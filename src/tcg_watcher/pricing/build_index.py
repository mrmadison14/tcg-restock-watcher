from __future__ import annotations
from .match import normalize
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import tcgcsv
from ..http import make_httpx_get

_SEALED_MARKERS = (
    "booster box", "elite trainer", "etb", "booster bundle", "booster pack",
    "collection", "tin", "blister", "premium",
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


def _franchise_index(http_get, category_ids) -> dict:
    merged: dict = {}
    for cat in category_ids:
        try:
            for g in tcgcsv.groups(http_get, cat):
                gid = g["groupId"]
                products = tcgcsv.products(http_get, cat, gid)
                prices = tcgcsv.prices(http_get, cat, gid)
                merged.update(sealed_entries(products, prices))
        except Exception as exc:
            print(f"[build-index] category {cat} failed: {type(exc).__name__}: {exc}")
    return merged


def build(http_get, categories: dict, fx_url: str, index_path, fx_path, now_iso: str) -> None:
    index = {franchise: _franchise_index(http_get, cats) for franchise, cats in categories.items()}
    fx = http_get(fx_url) or {}
    fx_out = {"rates": fx.get("rates", {}), "fetched_at": now_iso}

    index_path = Path(index_path); fx_path = Path(fx_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    fx_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    fx_path.write_text(json.dumps(fx_out, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    total = sum(len(v) for v in index.values())
    print(f"[build-index] wrote {total} sealed entries across {len(index)} franchises; fx rates={list(fx_out['rates'])}")


def main() -> int:
    from ..config import load_config
    config = load_config(os.environ.get("TCG_CONFIG", "config.toml"))
    if config.pricing is None:
        print("[build-index] no [pricing] config; nothing to do")
        return 0
    http_get = make_httpx_get(min_interval=1.0)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    build(http_get, config.pricing.categories, config.pricing.fx_url,
          config.pricing.index_path, config.pricing.fx_path, now_iso)
    return 0


if __name__ == "__main__":
    sys.exit(main())
