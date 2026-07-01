from __future__ import annotations
import json
from pathlib import Path

from ..models import Product, Verdict
from .match import normalize, best_match


class Oracle:
    def __init__(self, index: dict, fx: dict, deal_threshold: float, match_threshold: float):
        self.index = index
        self.rates = fx.get("rates", {})
        self.deal_threshold = deal_threshold
        self.match_threshold = match_threshold

    @classmethod
    def load(cls, index_path, fx_path, deal_threshold: float, match_threshold: float) -> "Oracle":
        index = cls._read(index_path)
        fx = cls._read(fx_path)
        return cls(index, fx, deal_threshold, match_threshold)

    @staticmethod
    def _read(path) -> dict:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _to_usd(self, price: float, currency: str):
        if currency == "USD":
            return price
        rate = self.rates.get(currency)
        if not rate:
            return None
        return price / rate

    def verdict(self, product: Product) -> Verdict:
        store_usd = self._to_usd(product.price, product.currency)
        fr_index = self.index.get(product.franchise or "", {})
        match = best_match(normalize(product.title), fr_index, self.match_threshold) if fr_index else None
        if match is None or store_usd is None:
            return Verdict(status="na", market_usd=(match[1] if match else None),
                           store_usd=store_usd, pct_under=None,
                           matched_name=(match[0] if match else None), currency=product.currency)
        display_name, market_usd = match
        pct = (market_usd - store_usd) / market_usd if market_usd else None
        status = "deal" if (pct is not None and pct >= self.deal_threshold) else "market"
        return Verdict(status=status, market_usd=market_usd, store_usd=store_usd,
                       pct_under=pct, matched_name=display_name, currency=product.currency)
