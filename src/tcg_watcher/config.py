from __future__ import annotations
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Store:
    key: str
    base_url: str
    platform: str
    currency: str
    enabled: bool = True


@dataclass(frozen=True)
class Config:
    stores: tuple[Store, ...]
    franchise_synonyms: dict[str, tuple[str, ...]]
    max_events_per_store: int
    price_epsilon: float


def load_config(path: Path) -> Config:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    stores = tuple(
        Store(
            key=s["key"],
            base_url=s["base_url"].rstrip("/"),
            platform=s["platform"],
            currency=s["currency"],
            enabled=s.get("enabled", True),
        )
        for s in data["stores"]
    )
    synonyms = {k: tuple(v) for k, v in data["franchise_synonyms"].items()}
    thresholds = data["thresholds"]
    return Config(
        stores=stores,
        franchise_synonyms=synonyms,
        max_events_per_store=thresholds["max_events_per_store"],
        price_epsilon=thresholds["price_epsilon"],
    )
