from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .adapters import shopify
from .filtering import filter_franchises
from .state import load_snapshot, build_snapshot, save_snapshot, snapshot_path
from .diff import detect_events
from .notify import send_events

_ADAPTERS = {"shopify": shopify.fetch_products}


@dataclass
class RunReport:
    stores_ok: int = 0
    stores_failed: int = 0
    events_sent: int = 0
    seeded: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"ok={self.stores_ok} failed={self.stores_failed} "
            f"events_sent={self.events_sent} seeded={self.seeded}"
        )


def run_once(config: Config, http_get, post_loud, post_quiet, state_dir, now_iso) -> RunReport:
    report = RunReport()
    state_dir = Path(state_dir)

    for store in config.stores:
        if not store.enabled:
            continue
        adapter = _ADAPTERS.get(store.platform)
        if adapter is None:
            report.stores_failed += 1
            print(f"[{store.key}] no adapter for platform={store.platform}")
            continue
        try:
            products = adapter(store, http_get)
        except Exception as exc:
            report.stores_failed += 1
            print(f"[{store.key}] adapter failed: {type(exc).__name__}: {exc}")
            continue

        watched = filter_franchises(products, config.franchise_synonyms)
        prev = load_snapshot(snapshot_path(state_dir, store.key))

        if not prev.get("seeded"):
            save_snapshot(snapshot_path(state_dir, store.key), build_snapshot(watched, now_iso))
            report.seeded.append(store.key)
            report.stores_ok += 1
            print(f"[{store.key}] seeded {len(watched)} watched variants (no alerts)")
            continue

        events = detect_events(watched, prev, config.price_epsilon)
        report.events_sent += send_events(
            events, post_loud, post_quiet, config.max_events_per_store
        )
        save_snapshot(snapshot_path(state_dir, store.key), build_snapshot(watched, now_iso))
        report.stores_ok += 1
        print(f"[{store.key}] {len(watched)} watched, {len(events)} events")

    return report
