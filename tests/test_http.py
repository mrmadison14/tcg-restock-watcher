import httpx
import pytest
from tcg_watcher.http import make_httpx_get


def resp(status, payload=None):
    req = httpx.Request("GET", "http://x")
    if payload is not None:
        return httpx.Response(status, json=payload, request=req)
    return httpx.Response(status, request=req)


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
    get = make_httpx_get(retries=2, backoff=0.1, client=client, sleep=lambda s: slept.append(s))
    assert get("http://x") == {"products": []}
    assert client.calls == 2
    assert len(slept) == 1


def test_gives_up_after_retries_and_raises():
    client = FakeClient([resp(503), resp(503), resp(503)])
    get = make_httpx_get(retries=2, backoff=0, client=client, sleep=lambda s: None)
    with pytest.raises(httpx.HTTPStatusError):
        get("http://x")
    assert client.calls == 3


def test_success_first_try_no_sleep():
    slept = []
    client = FakeClient([resp(200, {"ok": 1})])
    get = make_httpx_get(retries=2, backoff=0, client=client, sleep=lambda s: slept.append(s))
    assert get("http://x") == {"ok": 1}
    assert client.calls == 1
    assert slept == []


def test_transport_error_is_retried():
    client = FakeClient([httpx.ConnectTimeout("t"), resp(200, {"ok": 1})])
    get = make_httpx_get(retries=2, backoff=0, client=client, sleep=lambda s: None)
    assert get("http://x") == {"ok": 1}
    assert client.calls == 2


def test_404_not_retried():
    client = FakeClient([resp(404)])
    get = make_httpx_get(retries=2, backoff=0, client=client, sleep=lambda s: None)
    with pytest.raises(httpx.HTTPStatusError):
        get("http://x")
    assert client.calls == 1
