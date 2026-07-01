from __future__ import annotations

_BASE = "https://tcgcsv.com/tcgplayer"


def groups(http_get, category_id: int) -> list[dict]:
    return (http_get(f"{_BASE}/{category_id}/groups") or {}).get("results", [])


def products(http_get, category_id: int, group_id) -> list[dict]:
    return (http_get(f"{_BASE}/{category_id}/{group_id}/products") or {}).get("results", [])


def prices(http_get, category_id: int, group_id) -> list[dict]:
    return (http_get(f"{_BASE}/{category_id}/{group_id}/prices") or {}).get("results", [])
