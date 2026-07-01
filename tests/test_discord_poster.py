import httpx
import pytest
from tcg_watcher.http import make_discord_poster


def _resp(code, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return httpx.Response(code, headers=headers, request=httpx.Request("POST", "https://hook"))


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def post(self, url, json=None):
        r = self.responses[self.calls]
        self.calls += 1
        return r


def test_poster_retries_on_429_then_succeeds():
    slept = []
    client = _FakeClient([_resp(429, "0"), _resp(204)])
    post = make_discord_poster("https://hook", client=client, sleep=slept.append)
    post({"content": "x"})
    assert client.calls == 2
    assert slept == [0.0]


def test_poster_raises_after_exhausting_retries():
    client = _FakeClient([_resp(429, "0")] * 10)
    post = make_discord_poster("https://hook", client=client, sleep=lambda s: None,
                               retries=3, max_429_waits=10)
    with pytest.raises(httpx.HTTPStatusError):
        post({"content": "x"})
    assert client.calls == 4


def test_poster_caps_429_waits():
    slept = []
    client = _FakeClient([_resp(429, "1")] * 10)
    post = make_discord_poster("https://hook", client=client, sleep=slept.append,
                               retries=8, max_429_waits=2)
    with pytest.raises(httpx.HTTPStatusError):
        post({"content": "x"})
    assert len(slept) == 2
    assert client.calls == 3


def test_poster_caps_cumulative_wait():
    slept = []
    client = _FakeClient([_resp(429, "30")] * 10)
    post = make_discord_poster("https://hook", client=client, sleep=slept.append,
                               retries=8, max_429_waits=10, total_wait_cap=45.0)
    with pytest.raises(httpx.HTTPStatusError):
        post({"content": "x"})
    assert sum(slept) <= 45.0
    assert len(slept) == 1
