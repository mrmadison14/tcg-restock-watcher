from __future__ import annotations
import httpx

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def make_httpx_get():
    client = httpx.Client(timeout=20.0, headers={"User-Agent": _UA}, follow_redirects=True)

    def get(url, params=None):
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    return get


def make_discord_poster(webhook_url: str):
    client = httpx.Client(timeout=20.0)

    def post(payload: dict) -> None:
        resp = client.post(webhook_url, json=payload)
        resp.raise_for_status()

    return post
