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

def test_tags_matched_individually_no_cross_boundary():
    p = mk("Mystery Item", tags=("someone", "piecemeal"))
    assert filter_franchises([p], SYN) == []
    q = mk("Mystery Item", tags=("One Piece",))
    assert filter_franchises([q], SYN)[0].franchise == "one piece"


def test_keep_sealed_filters_non_sealed():
    from tcg_watcher.filtering import keep_sealed
    box = Product(store="s", product_id="1", variant_id="a", title="Booster Box", price=1.0,
                  currency="USD", in_stock=True, url="u", is_sealed=True)
    single = Product(store="s", product_id="2", variant_id="b", title="Charizard", price=1.0,
                     currency="USD", in_stock=True, url="u", is_sealed=False)
    assert keep_sealed([box, single]) == [box]
