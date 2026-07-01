import json
from tcg_watcher.models import Product
from tcg_watcher.pricing.oracle import Oracle


def _oracle(tmp_path, index, rates):
    ip = tmp_path / "i.json"; fp = tmp_path / "f.json"
    ip.write_text(json.dumps(index)); fp.write_text(json.dumps({"rates": rates, "fetched_at": "t"}))
    return Oracle.load(ip, fp, deal_threshold=0.10, match_threshold=0.86)


def _prod(title, price, currency="USD", franchise="pokemon"):
    return Product(store="s", product_id="1", variant_id="v", title=title, price=price,
                   currency=currency, in_stock=True, url="u", franchise=franchise)


IDX = {"pokemon": {"surging sparks elite trainer box":
                   {"market_usd": 60.0, "display_name": "Surging Sparks Elite Trainer Box"}}}


def test_deal_when_10pct_or_more_under(tmp_path):
    o = _oracle(tmp_path, IDX, {"CAD": 1.36})
    v = o.verdict(_prod("Pokemon - Surging Sparks - Elite Trainer Box", 48.0))
    assert v.status == "deal" and round(v.pct_under, 2) == 0.20


def test_market_when_under_threshold(tmp_path):
    o = _oracle(tmp_path, IDX, {"CAD": 1.36})
    v = o.verdict(_prod("Pokemon - Surging Sparks - Elite Trainer Box", 57.0))
    assert v.status == "market" and v.market_usd == 60.0


def test_cad_normalized_to_usd(tmp_path):
    o = _oracle(tmp_path, IDX, {"CAD": 1.36})
    v = o.verdict(_prod("Pokemon - Surging Sparks - Elite Trainer Box", 68.0, currency="CAD"))
    assert round(v.store_usd, 2) == 50.0 and v.status == "deal"


def test_na_on_no_match(tmp_path):
    o = _oracle(tmp_path, IDX, {"CAD": 1.36})
    v = o.verdict(_prod("Pokemon - Journey Together - Booster Box", 300.0))
    assert v.status == "na" and v.matched_name is None


def test_na_but_never_raises_when_index_missing(tmp_path):
    o = Oracle.load(tmp_path / "nope.json", tmp_path / "no-fx.json", 0.10, 0.86)
    v = o.verdict(_prod("anything", 10.0))
    assert v.status == "na"
