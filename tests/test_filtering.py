from tcg_watcher.models import Product
from tcg_watcher.filtering import filter_franchises

SYN = {
    "pokemon": ("pokemon", "pokémon"),
    "one piece": ("one piece",),
    "dragon ball": ("dragon ball", "fusion world"),
}

def mk(title, tags=(), product_type=""):
    return Product(store="s", product_id="1", variant_id="v", title=title, price=1.0,
                   currency="USD", in_stock=True, url="u", tags=tags, product_type=product_type)

def test_matches_by_tag_then_title():
    prods = [
        mk("Surging Sparks ETB", tags=("Pokemon",)),       # tag match
        mk("Romance Dawn Booster Box", product_type="One Piece"),  # product_type match
        mk("Fusion World Starter Deck"),                   # title match -> dragon ball
        mk("Lorcana Chapter 5 Booster"),                   # no match -> dropped
    ]
    out = filter_franchises(prods, SYN)
    assert [p.franchise for p in out] == ["pokemon", "one piece", "dragon ball"]
    assert len(out) == 3

def test_franchise_set_on_returned_products():
    out = filter_franchises([mk("Pokemon Booster Bundle")], SYN)
    assert out[0].franchise == "pokemon"
    assert out[0].title == "Pokemon Booster Bundle"
