from __future__ import annotations
import time
import httpx

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_RETRY_STATUS = {429, 500, 502, 503, 504}


def make_httpx_get(retries: int = 2, backoff: float = 0.5, client=None, sleep=time.sleep):
    if client is None:
        client = httpx.Client(timeout=20.0, headers={"User-Agent": _UA}, follow_redirects=True)

    def get(url, params=None):
        for attempt in range(retries + 1):
            try:
                resp = client.get(url, params=params)
            except httpx.TransportError:
                if attempt < retries:
                    sleep(backoff * (attempt + 1))
                    continue
                raise
            if resp.status_code in _RETRY_STATUS and attempt < retries:
                sleep(backoff * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()

    return get


def make_discord_poster(webhook_url: str):
    client = httpx.Client(timeout=20.0)

    def post(payload: dict) -> None:
        resp = client.post(webhook_url, json=payload)
        resp.raise_for_status()

    return post
