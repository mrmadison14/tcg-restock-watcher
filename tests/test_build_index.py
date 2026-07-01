from tcg_watcher.pricing.build_index import sealed_entries

PRODUCTS = [
    {"productId": 1, "name": "Silver Tempest Booster Box"},
    {"productId": 2, "name": "Lugia VSTAR"},                       # single -> dropped
    {"productId": 3, "name": "Silver Tempest Elite Trainer Box"},
    {"productId": 4, "name": "Fall 2022 Collector Chest Case"},    # sealed but unpriced -> dropped
]
PRICES = [
    {"productId": 1, "marketPrice": 544.53, "subTypeName": "Normal"},
    {"productId": 2, "marketPrice": 3.21, "subTypeName": "Holofoil"},
    {"productId": 3, "marketPrice": 170.2, "subTypeName": "Normal"},
    {"productId": 4, "marketPrice": None, "subTypeName": "Normal"},
]


def test_sealed_entries_filters_and_joins():
    out = sealed_entries(PRODUCTS, PRICES)
    assert set(out) == {"silver tempest booster box", "silver tempest elite trainer box"}
    assert out["silver tempest booster box"] == {"market_usd": 544.53,
                                                 "display_name": "Silver Tempest Booster Box"}


def test_sealed_entries_prefers_normal_subtype():
    products = [{"productId": 9, "name": "Set Booster Box"}]
    prices = [
        {"productId": 9, "marketPrice": 1.0, "subTypeName": "Holofoil"},
        {"productId": 9, "marketPrice": 500.0, "subTypeName": "Normal"},
    ]
    out = sealed_entries(products, prices)
    assert out["set booster box"]["market_usd"] == 500.0
