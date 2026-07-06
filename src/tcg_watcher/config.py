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
    collections: tuple[str, ...] = ()


@dataclass(frozen=True)
class PricingConfig:
    enabled: bool
    deal_threshold: float
    match_threshold: float
    index_path: str
    fx_path: str
    fx_url: str
    categories: dict[str, tuple[int, ...]]


@dataclass(frozen=True)
class Config:
    stores: tuple[Store, ...]
    franchise_synonyms: dict[str, tuple[str, ...]]
    max_events_per_store: int
    price_epsilon: float
    post_delay_seconds: float = 0.0
    price_change_pct: float = 0.05
    pricing: "PricingConfig | None" = None


def load_config(path: Path) -> Config:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    stores = tuple(
        Store(
            key=s["key"],
            base_url=s["base_url"].rstrip("/"),
            platform=s["platform"],
            currency=s["currency"],
            enabled=s.get("enabled", True),
            collections=tuple(s.get("collections", [])),
        )
        for s in data["stores"]
    )
    synonyms = {k: tuple(v) for k, v in data["franchise_synonyms"].items()}
    thresholds = data["thresholds"]
    pricing = None
    if "pricing" in data:
        pr = data["pricing"]
        pricing = PricingConfig(
            enabled=pr.get("enabled", True),
            deal_threshold=pr["deal_threshold"],
            match_threshold=pr["match_threshold"],
            index_path=pr["index_path"],
            fx_path=pr["fx_path"],
            fx_url=pr["fx_url"],
            categories={k: tuple(v) for k, v in pr.get("categories", {}).items()},
        )
    return Config(
        stores=stores,
        franchise_synonyms=synonyms,
        max_events_per_store=thresholds["max_events_per_store"],
        price_epsilon=thresholds["price_epsilon"],
        post_delay_seconds=thresholds.get("post_delay_seconds", 0.0),
        price_change_pct=thresholds.get("price_change_pct", 0.05),
        pricing=pricing,
    )
