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


def test_best_match_rejects_size_qualifier_mismatch():
    index = {"silver tempest booster box case": {"market_usd": 6100.0, "display_name": "Silver Tempest Booster Box Case"}}
    assert best_match("silver tempest booster box", index, 0.86) is None
    assert best_match("silver tempest booster box case", index, 0.86) == ("Silver Tempest Booster Box Case", 6100.0)


def test_best_match_prefilter_skips_zero_overlap():
    index = {"zzz qqq www": {"market_usd": 9.0, "display_name": "Zzz Qqq Www"}}
    assert best_match("surging sparks elite trainer box", index, 0.1) is None


def test_best_match_prefilter_keeps_overlapping_candidate():
    m = best_match("surging sparks elite trainer box", INDEX, 0.86)
    assert m == ("Surging Sparks Elite Trainer Box", 60.0)


def test_best_match_still_matches_same_size():
    index = {"surging sparks elite trainer box": {"market_usd": 60.0, "display_name": "Surging Sparks Elite Trainer Box"}}
    assert best_match("surging sparks elite trainer box", index, 0.86) == ("Surging Sparks Elite Trainer Box", 60.0)
