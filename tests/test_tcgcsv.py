from tcg_watcher.pricing import tcgcsv


def make_get(calls):
    def get(url, params=None):
        calls.append(url)
        return {"success": True, "results": [{"url": url}]}
    return get


def test_urls_and_results():
    calls = []
    get = make_get(calls)
    assert tcgcsv.groups(get, 3) == [{"url": "https://tcgcsv.com/tcgplayer/3/groups"}]
    assert tcgcsv.products(get, 3, 3170) == [{"url": "https://tcgcsv.com/tcgplayer/3/3170/products"}]
    assert tcgcsv.prices(get, 3, 3170) == [{"url": "https://tcgcsv.com/tcgplayer/3/3170/prices"}]
    assert calls == [
        "https://tcgcsv.com/tcgplayer/3/groups",
        "https://tcgcsv.com/tcgplayer/3/3170/products",
        "https://tcgcsv.com/tcgplayer/3/3170/prices",
    ]


def test_missing_results_is_empty_list():
    assert tcgcsv.groups(lambda u, params=None: {}, 3) == []
