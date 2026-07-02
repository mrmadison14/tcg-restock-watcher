from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path
from .models import Product

_CARRYOVER_TTL = timedelta(days=14)


def snapshot_path(state_dir: Path, store_key: str) -> Path:
    return Path(state_dir) / f"{store_key}.json"


def load_snapshot(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {"seeded": False, "last_run": None, "variants": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def build_snapshot(products: list[Product], now_iso: str) -> dict:
    variants = {
        p.variant_id: {
            "price": p.price,
            "in_stock": p.in_stock,
            "title": p.title,
            "is_preorder": p.is_preorder,
        }
        for p in products
    }
    return {"seeded": True, "last_run": now_iso, "variants": variants}


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def merge_snapshot(prev: dict, products: list[Product], now_iso: str) -> dict:
    now = _parse_ts(now_iso)
    variants: dict = {}
    if prev.get("seeded"):
        for vid, entry in prev.get("variants", {}).items():
            seen = _parse_ts(entry.get("last_seen"))
            if "last_seen" not in entry:
                entry = {**entry, "last_seen": now_iso}
            elif now is not None and seen is not None and now - seen > _CARRYOVER_TTL:
                continue
            variants[vid] = entry
    fresh = build_snapshot(products, now_iso)
    for vid, entry in fresh["variants"].items():
        variants[vid] = {**entry, "last_seen": now_iso}
    return {"seeded": True, "last_run": now_iso, "variants": variants}


def save_snapshot(path: Path, snapshot: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
