from pathlib import Path
from tcg_watcher.config import load_config

def test_load_config(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[[stores]]
key = "hobbiesville"
base_url = "https://hobbiesville.com"
platform = "shopify"
currency = "CAD"

[[stores]]
key = "disabled_store"
base_url = "https://x.com"
platform = "shopify"
currency = "USD"
enabled = false

[franchise_synonyms]
pokemon = ["pokemon", "pokémon"]
"one piece" = ["one piece"]

[thresholds]
max_events_per_store = 25
price_epsilon = 0.01
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    keys = [s.key for s in cfg.stores]
    assert keys == ["hobbiesville", "disabled_store"]
    assert cfg.stores[0].currency == "CAD"
    assert cfg.stores[1].enabled is False
    assert cfg.franchise_synonyms["pokemon"] == ("pokemon", "pokémon")
    assert cfg.max_events_per_store == 25
    assert cfg.price_epsilon == 0.01
    assert cfg.post_delay_seconds == 0.0
    assert cfg.price_change_pct == 0.05  # default when omitted


def test_load_config_collections(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '''
[[stores]]
key = "curated"
base_url = "https://c.test"
platform = "shopify"
currency = "USD"
collections = ["pokemon:pokemon-sealed", "one piece:op-sealed"]

[[stores]]
key = "plain"
base_url = "https://p.test"
platform = "shopify"
currency = "USD"

[franchise_synonyms]
pokemon = ["pokemon"]

[thresholds]
max_events_per_store = 25
price_epsilon = 0.01
''',
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.stores[0].collections == ("pokemon:pokemon-sealed", "one piece:op-sealed")
    assert cfg.stores[1].collections == ()


BASE = """
[[stores]]
key = "s"
base_url = "https://s.test"
platform = "shopify"
currency = "USD"

[franchise_synonyms]
pokemon = ["pokemon"]

[thresholds]
max_events_per_store = 25
price_epsilon = 0.01
"""

PRICING = """
[pricing]
enabled = true
deal_threshold = 0.10
match_threshold = 0.86
index_path = "data/price_index.json"
fx_path = "data/fx.json"
fx_url = "https://open.er-api.com/v6/latest/USD"

[pricing.categories]
pokemon = [3, 85]
"one piece" = [68]
"dragon ball" = [23, 27, 80]
"""


def test_pricing_absent_is_none(tmp_path):
    f = tmp_path / "c.toml"; f.write_text(BASE)
    assert load_config(f).pricing is None


def test_pricing_parsed(tmp_path):
    f = tmp_path / "c.toml"; f.write_text(BASE + PRICING)
    pr = load_config(f).pricing
    assert pr.enabled is True and pr.deal_threshold == 0.10
    assert pr.categories["pokemon"] == (3, 85)
    assert pr.categories["dragon ball"] == (23, 27, 80)


def test_post_delay_seconds_parsed(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text(BASE.replace("price_epsilon = 0.01", "price_epsilon = 0.01\npost_delay_seconds = 1.5"))
    assert load_config(f).post_delay_seconds == 1.5
