from __future__ import annotations
import json
import re
from ..config import Store
from ..models import Product

# Bespoke Next.js store, no product JSON endpoint (robots.txt disallows /api/).
# /search?q= server-renders the entire catalog (~111 products) into RSC flight
# chunks on one page, so a run costs a single request.
_SEARCH_PATH = "/search?q="
_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\]\)</script>', re.S)
_PRODUCT_ANCHOR = re.compile(r'"product":\{"id":"')
_DATE_MARKER_RE = re.compile(r'"\$D([^"]+)"')


def _flight_text(html: str) -> str:
    # Chunks are independently escaped slices of one text stream; join the raw
    # bodies before decoding so records split across chunk boundaries survive.
    chunks = _CHUNK_RE.findall(html)
    if not chunks:
        raise RuntimeError("no flight chunks in search page")
    return json.loads('"' + "".join(chunks) + '"')


def _product_objects(flight: str) -> list[dict]:
    out: list[dict] = []
    for m in _PRODUCT_ANCHOR.finditer(flight):
        start = m.start() + len('"product":')
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(flight)):
            ch = flight[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    raw = _DATE_MARKER_RE.sub(r'"\1"', flight[start:i + 1])
                    out.append(json.loads(raw))
                    break
    return out


def products_from_page(store: Store, html: str) -> list[Product]:
    objs = _product_objects(_flight_text(html))
    if not objs:
        raise RuntimeError("search page had no product records")
    seen: set[str] = set()
    out: list[Product] = []
    for p in objs:
        pid = str(p["id"])
        if pid in seen:
            continue
        seen.add(pid)
        images = p.get("images") or []
        out.append(
            Product(
                store=store.key,
                product_id=pid,
                variant_id=pid,
                title=p.get("title", ""),
                price=p["priceCents"] / 100,
                currency=store.currency,
                in_stock=(p.get("quantity") or 0) > 0,
                url=f"{store.base_url}/products/{p['slug']}",
                image=f"{store.base_url}/api/images/{images[0]['objectKey']}" if images else None,
                product_type=p.get("productType") or "",
                tags=((p.get("franchise") or "").lower().replace("_", " "),),
                is_sealed=p.get("cardNumber") is None,
            )
        )
    return out


def fetch_products(store: Store, http_get) -> list[Product]:
    html = http_get(f"{store.base_url}{_SEARCH_PATH}", as_text=True)
    return products_from_page(store, html)
