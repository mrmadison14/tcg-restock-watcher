from __future__ import annotations
import json
from pathlib import Path
from .models import Product


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


def save_snapshot(path: Path, snapshot: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
