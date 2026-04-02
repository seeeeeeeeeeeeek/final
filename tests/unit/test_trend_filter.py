from pathlib import Path

from src.modules.trend_filter import evaluate_trend_filter
from src.scanner.models import DecisionOutcome, MarketDataBundle, MarketDataSlice, SymbolContext
from tests.unit.conftest import load_daily_bundle


def _trend_config(*, require_structure: bool = True) -> dict:
    return {
        "trend_filter": {
            "moving_average_periods": {"fast": 3, "slow": 5},
            "minimum_slope_pct": 0.0,
            "minimum_trend_strength_score": 60.0,
            "require_price_above_fast_ma": True,
            "require_price_above_slow_ma": True,
            "require_higher_high_higher_low_structure": require_structure,
        }
    }


def test_trend_filter_clear_bullish_daily_uptrend_passes(fixture_dir: Path) -> None:
    bundle = load_daily_bundle(fixture_dir / "daily_trend_bullish.json")
    result = evaluate_trend_filter(SymbolContext(symbol="NVDA"), bundle, _trend_config())
    assert result.module_name == "trend_filter"
    assert result.outcome == DecisionOutcome.PASS
    assert result.passed is True
    assert result.metrics["trend_strength_score"] == 100.0


def test_trend_filter_sideways_structure_fails(fixture_dir: Path) -> None:
    bundle = load_daily_bundle(fixture_dir / "daily_trend_sideways.json")
    result = evaluate_trend_filter(SymbolContext(symbol="MSFT"), bundle, _trend_config())
    assert result.outcome == DecisionOutcome.FAIL
    assert result.passed is False
    assert any("higher-high / higher-low" in reason for reason in result.reasons)


def test_trend_filter_insufficient_data_skips() -> None:
    bundle = MarketDataBundle(
        daily=MarketDataSlice(
            timeframe="1D",
            bars=[{"timestamp_utc": "2026-01-01T00:00:00Z", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}],
        )
    )
    result = evaluate_trend_filter(SymbolContext(symbol="AAPL"), bundle, _trend_config())
    assert result.outcome == DecisionOutcome.SKIP
    assert result.passed is False
    assert "Insufficient daily bars" in result.reasons[0]


def test_trend_filter_price_below_key_ma_fails(fixture_dir: Path) -> None:
    bundle = load_daily_bundle(fixture_dir / "daily_trend_below_ma.json")
    result = evaluate_trend_filter(SymbolContext(symbol="TSLA"), bundle, _trend_config(require_structure=False))
    assert result.outcome == DecisionOutcome.FAIL
    assert result.flags["price_above_fast_ma"] is False
    assert result.flags["price_above_slow_ma"] is False


def test_trend_filter_is_deterministic_for_identical_inputs(fixture_dir: Path) -> None:
    bundle = load_daily_bundle(fixture_dir / "daily_trend_bullish.json")
    config = _trend_config()
    first = evaluate_trend_filter(SymbolContext(symbol="NVDA"), bundle, config)
    second = evaluate_trend_filter(SymbolContext(symbol="NVDA"), bundle, config)
    assert first.outcome == second.outcome
    assert first.passed == second.passed
    assert first.metrics == second.metrics
    assert first.reasons == second.reasons
