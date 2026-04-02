from src.scanner.universe import screen_symbol


def test_universe_screen_rejects_symbol_below_thresholds() -> None:
    result = screen_symbol(
        "TEST",
        {
            "price": 5.0,
            "avg_daily_volume": 100,
            "avg_daily_dollar_volume": 1000.0,
            "security_type": "common_stock",
            "exchange": "NASDAQ",
        },
        {
            "universe": {
                "minimum_price": 10.0,
                "minimum_avg_daily_volume": 1000000,
                "minimum_avg_daily_dollar_volume": 20000000.0,
                "exclude_security_types": [],
                "allowed_exchanges": ["NASDAQ"],
            }
        },
    )
    assert result.is_eligible is False
    assert result.reasons
