from pathlib import Path

from src.modules.breakout_trigger import evaluate_breakout_trigger
from src.scanner.models import DecisionOutcome, SymbolContext
from tests.unit.conftest import load_multi_timeframe_bundle


def _breakout_config() -> dict:
    return {
        "compression": {
            "minimum_base_bars": 5,
            "maximum_base_bars": 8,
            "maximum_pullback_depth_pct": 35.0,
            "minimum_range_contraction_pct": 20.0,
            "minimum_volatility_contraction_pct": 15.0,
            "require_upper_half_positioning": True,
            "enable_volume_dry_up_bonus": True,
        },
        "breakout_trigger": {
            "breakout_buffer_pct": 0.1,
            "minimum_breakout_range_vs_base_avg": 1.5,
            "confirmation_bar_count": 2,
            "use_volume_confirmation": True,
            "minimum_relative_volume": 1.2,
        },
    }


def test_valid_breakout_passes(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_breakout_valid.json")
    result = evaluate_breakout_trigger(SymbolContext(symbol="NVDA"), bundle, _breakout_config())
    assert result.module_name == "breakout_trigger"
    assert result.outcome == DecisionOutcome.PASS
    assert result.passed is True
    assert result.flags["trigger_pass"] is True


def test_breakout_with_weak_followthrough_fails(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_breakout_weak_followthrough.json")
    result = evaluate_breakout_trigger(SymbolContext(symbol="AAPL"), bundle, _breakout_config())
    assert result.outcome == DecisionOutcome.FAIL
    assert result.flags["follow_through_pass"] is False


def test_breakout_without_enough_expansion_fails(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_breakout_no_expansion.json")
    result = evaluate_breakout_trigger(SymbolContext(symbol="MSFT"), bundle, _breakout_config())
    assert result.outcome == DecisionOutcome.FAIL
    assert result.flags["breakout_expansion_pass"] is False


def test_insufficient_intraday_data_skips(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_breakout_insufficient.json")
    result = evaluate_breakout_trigger(SymbolContext(symbol="AMD"), bundle, _breakout_config())
    assert result.outcome == DecisionOutcome.SKIP
    assert "Insufficient 5m bars" in result.reasons[0]


def test_breakout_output_is_deterministic(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_breakout_valid.json")
    config = _breakout_config()
    first = evaluate_breakout_trigger(SymbolContext(symbol="NVDA"), bundle, config)
    second = evaluate_breakout_trigger(SymbolContext(symbol="NVDA"), bundle, config)
    assert first.outcome == second.outcome
    assert first.passed == second.passed
    assert first.metrics == second.metrics
    assert first.reasons == second.reasons
