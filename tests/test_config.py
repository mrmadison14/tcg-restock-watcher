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
