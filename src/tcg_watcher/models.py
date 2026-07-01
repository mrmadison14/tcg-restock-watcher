from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class EventType(str, Enum):
    RESTOCK = "restock"
    NEW_PRODUCT = "new_product"
    PREORDER_OPEN = "preorder_open"
    PRICE_CHANGE = "price_change"


@dataclass(frozen=True)
class Verdict:
    status: str
    market_usd: float | None
    store_usd: float | None
    pct_under: float | None
    matched_name: str | None
    currency: str


@dataclass(frozen=True)
class Product:
    store: str
    product_id: str
    variant_id: str
    title: str
    price: float
    currency: str
    in_stock: bool
    url: str
    image: str | None = None
    product_type: str = ""
    tags: tuple[str, ...] = ()
    is_preorder: bool = False
    is_sealed: bool = False
    franchise: str | None = None


@dataclass(frozen=True)
class Event:
    type: EventType
    product: Product
    previous_price: float | None = None
    previous_in_stock: bool | None = None
    verdict: "Verdict | None" = None
