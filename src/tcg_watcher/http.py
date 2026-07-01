from __future__ import annotations
import time
import httpx

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _retry_after_seconds(resp, cap):
    val = resp.headers.get("retry-after")
    if not val:
        return None
    try:
        secs = float(val)
    except ValueError:
        return None
    return max(0.0, min(secs, cap))


def make_httpx_get(
    retries: int = 3,
    backoff: float = 1.0,
    min_interval: float = 2.5,
    retry_after_cap: float = 30.0,
    client=None,
    sleep=time.sleep,
    monotonic=time.monotonic,
):
    if client is None:
        client = httpx.Client(timeout=30.0, headers={"User-Agent": _UA}, follow_redirects=True)
    last = {"t": None}

    def get(url, params=None):
        for attempt in range(retries + 1):
            if last["t"] is not None:
                wait = min_interval - (monotonic() - last["t"])
                if wait > 0:
                    sleep(wait)
            try:
                resp = client.get(url, params=params)
            except httpx.TransportError:
                last["t"] = monotonic()
                if attempt < retries:
                    sleep(backoff * (2 ** attempt))
                    continue
                raise
            last["t"] = monotonic()
            if resp.status_code in _RETRY_STATUS and attempt < retries:
                ra = _retry_after_seconds(resp, retry_after_cap)
                sleep(ra if ra is not None else backoff * (2 ** attempt))
                continue
            resp.raise_for_status()
            return resp.json()

    return get


def make_discord_poster(
    webhook_url: str,
    retries: int = 4,
    backoff: float = 1.0,
    retry_after_cap: float = 30.0,
    client=None,
    sleep=time.sleep,
):
    if client is None:
        client = httpx.Client(timeout=20.0)

    def post(payload: dict) -> None:
        for attempt in range(retries + 1):
            resp = client.post(webhook_url, json=payload)
            if resp.status_code == 429 and attempt < retries:
                ra = _retry_after_seconds(resp, retry_after_cap)
                sleep(ra if ra is not None else backoff * (2 ** attempt))
                continue
            resp.raise_for_status()
            return

    return post
