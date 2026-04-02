from pathlib import Path

from src.modules.compression import evaluate_compression
from src.scanner.models import DecisionOutcome, SymbolContext
from tests.unit.conftest import load_multi_timeframe_bundle


def _compression_config() -> dict:
    return {
        "compression": {
            "minimum_base_bars": 5,
            "maximum_base_bars": 8,
            "maximum_pullback_depth_pct": 35.0,
            "minimum_range_contraction_pct": 20.0,
            "minimum_volatility_contraction_pct": 15.0,
            "require_upper_half_positioning": True,
            "enable_volume_dry_up_bonus": True,
        }
    }


def test_valid_constructive_compression_passes(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_compression_bullish.json")
    result = evaluate_compression(SymbolContext(symbol="NVDA"), bundle, _compression_config())
    assert result.module_name == "compression"
    assert result.outcome == DecisionOutcome.PASS
    assert result.passed is True
    assert result.flags["compression_pass"] is True


def test_loose_wide_base_fails(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_compression_loose.json")
    result = evaluate_compression(SymbolContext(symbol="AAPL"), bundle, _compression_config())
    assert result.outcome == DecisionOutcome.FAIL
    assert result.passed is False
    assert result.flags["range_contraction_pass"] is False or result.flags["volatility_contraction_pass"] is False


def test_pullback_too_deep_fails(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_compression_too_deep.json")
    result = evaluate_compression(SymbolContext(symbol="MSFT"), bundle, _compression_config())
    assert result.outcome == DecisionOutcome.FAIL
    assert result.passed is False
    assert result.flags["pullback_depth_pass"] is False


def test_insufficient_hourly_data_skips(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_compression_insufficient.json")
    result = evaluate_compression(SymbolContext(symbol="AMD"), bundle, _compression_config())
    assert result.outcome == DecisionOutcome.SKIP
    assert result.passed is False
    assert "Insufficient hourly bars" in result.reasons[0]


def test_compression_output_is_deterministic(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_compression_bullish.json")
    config = _compression_config()
    first = evaluate_compression(SymbolContext(symbol="NVDA"), bundle, config)
    second = evaluate_compression(SymbolContext(symbol="NVDA"), bundle, config)
    assert first.outcome == second.outcome
    assert first.passed == second.passed
    assert first.metrics == second.metrics
    assert first.reasons == second.reasons
