from __future__ import annotations
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config
from .http import make_httpx_get, make_discord_poster
from .runner import run_once


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    config = load_config(os.environ.get("TCG_CONFIG", "config.toml"))
    http_get = make_httpx_get()

    deals_url = os.environ["DISCORD_DEALS_WEBHOOK"]
    tracker_url = os.environ["DISCORD_TRACKER_WEBHOOK"]
    post_loud = make_discord_poster(deals_url)
    post_quiet = make_discord_poster(tracker_url)

    state_dir = Path(os.environ.get("TCG_STATE_DIR", "state"))
    report = run_once(config, http_get, post_loud, post_quiet, state_dir, now_iso())
    print("RUN:", report.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
