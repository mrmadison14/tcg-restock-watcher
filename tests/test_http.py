import httpx
import pytest
from tcg_watcher.http import make_httpx_get


def resp(status, payload=None, headers=None):
    req = httpx.Request("GET", "http://x")
    if payload is not None:
        return httpx.Response(status, json=payload, request=req, headers=headers or {})
    return httpx.Response(status, request=req, headers=headers or {})


class FakeClient:
    def __init__(self, items):
        self._items = list(items)
        self.calls = 0

    def get(self, url, params=None):
        self.calls += 1
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_retries_then_succeeds():
    slept = []
    client = FakeClient([resp(503), resp(200, {"products": []})])
    get = make_httpx_get(retries=2, backoff=0.1, min_interval=0, client=client, sleep=lambda s: slept.append(s))
    assert get("http://x") == {"products": []}
    assert client.calls == 2
    assert len(slept) == 1


def test_gives_up_after_retries_and_raises():
    client = FakeClient([resp(503), resp(503), resp(503)])
    get = make_httpx_get(retries=2, backoff=0, min_interval=0, client=client, sleep=lambda s: None)
    with pytest.raises(httpx.HTTPStatusError):
        get("http://x")
    assert client.calls == 3


def test_success_first_try_no_sleep():
    slept = []
    client = FakeClient([resp(200, {"ok": 1})])
    get = make_httpx_get(retries=2, backoff=0, min_interval=0, client=client, sleep=lambda s: slept.append(s))
    assert get("http://x") == {"ok": 1}
    assert client.calls == 1
    assert slept == []


def test_transport_error_is_retried():
    client = FakeClient([httpx.ConnectTimeout("t"), resp(200, {"ok": 1})])
    get = make_httpx_get(retries=2, backoff=0, min_interval=0, client=client, sleep=lambda s: None)
    assert get("http://x") == {"ok": 1}
    assert client.calls == 2


def test_404_not_retried():
    client = FakeClient([resp(404)])
    get = make_httpx_get(retries=2, backoff=0, min_interval=0, client=client, sleep=lambda s: None)
    with pytest.raises(httpx.HTTPStatusError):
        get("http://x")
    assert client.calls == 1


def test_honors_retry_after_header():
    slept = []
    client = FakeClient([resp(429, headers={"retry-after": "7"}), resp(200, {"ok": 1})])
    get = make_httpx_get(retries=2, backoff=1.0, min_interval=0, retry_after_cap=30,
                         client=client, sleep=lambda s: slept.append(s))
    assert get("http://x") == {"ok": 1}
    assert 7 in slept


def test_retry_after_capped():
    slept = []
    client = FakeClient([resp(429, headers={"retry-after": "999"}), resp(200, {"ok": 1})])
    get = make_httpx_get(retries=2, min_interval=0, retry_after_cap=30,
                         client=client, sleep=lambda s: slept.append(s))
    assert get("http://x") == {"ok": 1}
    assert 30 in slept


def test_as_text_returns_body_text():
    req = httpx.Request("GET", "http://x")
    client = FakeClient([httpx.Response(200, text="<html>hi</html>", request=req)])
    get = make_httpx_get(retries=0, min_interval=0, client=client, sleep=lambda s: None)
    assert get("http://x", as_text=True) == "<html>hi</html>"


def test_throttle_spaces_requests():
    slept = []
    clock = {"t": 0.0}
    def mono():
        return clock["t"]
    def slp(s):
        slept.append(s)
        clock["t"] += s
    client = FakeClient([resp(200, {"a": 1}), resp(200, {"b": 2})])
    get = make_httpx_get(retries=0, min_interval=2.5, client=client, sleep=slp, monotonic=mono)
    get("http://x")
    get("http://y")
    assert any(abs(s - 2.5) < 1e-9 for s in slept)
