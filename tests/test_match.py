from tcg_watcher.pricing.match import normalize, best_match


def test_normalize_strips_franchise_and_expands_etb():
    assert normalize("Pokemon - Surging Sparks - ETB") == "surging sparks elite trainer box"
    assert normalize("One Piece Card Game - Romance Dawn Booster Box") == "card game romance dawn booster box"


def test_normalize_drops_edition_and_punct():
    assert normalize("Pokemon - Terastal Festival ex - Japanese Booster Box") == "terastal festival ex booster box"


INDEX = {
    "surging sparks elite trainer box": {"market_usd": 60.0, "display_name": "Surging Sparks Elite Trainer Box"},
    "prismatic evolutions booster bundle": {"market_usd": 30.0, "display_name": "Prismatic Evolutions Booster Bundle"},
}


def test_best_match_hits_above_threshold():
    m = best_match(normalize("Pokemon - Surging Sparks - Elite Trainer Box"), INDEX, 0.86)
    assert m == ("Surging Sparks Elite Trainer Box", 60.0)


def test_best_match_returns_none_below_threshold():
    assert best_match("scarlet violet 151 booster box", INDEX, 0.86) is None


def test_best_match_requires_token_overlap():
    assert best_match("", INDEX, 0.86) is None
