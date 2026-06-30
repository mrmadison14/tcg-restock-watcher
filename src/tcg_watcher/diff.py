from __future__ import annotations
from .models import Product, Event, EventType


def detect_events(
    current: list[Product], previous: dict, epsilon: float = 0.01
) -> list[Event]:
    if not previous.get("seeded"):
        return []

    prev_variants = previous.get("variants", {})
    events: list[Event] = []

    for p in current:
        old = prev_variants.get(p.variant_id)

        if old is None:
            etype = EventType.PREORDER_OPEN if p.is_preorder else EventType.NEW_PRODUCT
            events.append(Event(type=etype, product=p))
            continue

        restocked = (not old["in_stock"]) and p.in_stock
        if restocked:
            etype = EventType.PREORDER_OPEN if p.is_preorder else EventType.RESTOCK
            events.append(
                Event(
                    type=etype,
                    product=p,
                    previous_in_stock=False,
                    previous_price=old["price"],
                )
            )
            continue

        if abs(p.price - old["price"]) > epsilon:
            events.append(
                Event(
                    type=EventType.PRICE_CHANGE,
                    product=p,
                    previous_price=old["price"],
                    previous_in_stock=old["in_stock"],
                )
            )

    return events
