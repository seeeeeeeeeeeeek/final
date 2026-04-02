from pathlib import Path

from src.modules.trap_risk import evaluate_trap_risk
from src.scanner.models import DecisionOutcome, SymbolContext
from tests.unit.conftest import load_multi_timeframe_bundle


def _trap_risk_config() -> dict:
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
        "trap_risk": {
            "maximum_distance_from_trend_ref_pct": 8.0,
            "maximum_rejection_wick_pct": 25.0,
            "minimum_overhead_clearance_pct": 2.0,
            "maximum_failed_follow_through_bars": 2,
            "abnormal_gap_threshold_pct": 5.0,
        },
    }


def test_clean_breakout_passes_trap_risk(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_trap_risk_clean.json")
    result = evaluate_trap_risk(SymbolContext(symbol="NVDA"), bundle, _trap_risk_config())
    assert result.module_name == "trap_risk"
    assert result.outcome == DecisionOutcome.PASS
    assert result.passed is True
    assert result.flags["trap_risk_elevated"] is False


def test_overextended_breakout_returns_no_trade(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_trap_risk_extension.json")
    result = evaluate_trap_risk(SymbolContext(symbol="AAPL"), bundle, _trap_risk_config())
    assert result.outcome == DecisionOutcome.NO_TRADE
    assert result.flags["extension_risk_pass"] is False


def test_rejection_wick_returns_no_trade(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_trap_risk_rejection.json")
    result = evaluate_trap_risk(SymbolContext(symbol="MSFT"), bundle, _trap_risk_config())
    assert result.outcome == DecisionOutcome.NO_TRADE
    assert result.flags["rejection_wick_pass"] is False


def test_poor_overhead_clearance_returns_no_trade(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_trap_risk_overhead.json")
    result = evaluate_trap_risk(SymbolContext(symbol="AMD"), bundle, _trap_risk_config())
    assert result.outcome == DecisionOutcome.NO_TRADE
    assert result.flags["overhead_clearance_pass"] is False


def test_weak_post_trigger_behavior_returns_no_trade(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_trap_risk_weak_followthrough.json")
    result = evaluate_trap_risk(SymbolContext(symbol="TSLA"), bundle, _trap_risk_config())
    assert result.outcome == DecisionOutcome.NO_TRADE
    assert result.metrics["weak_followthrough_detected"] is True
    assert result.flags["followthrough_risk_pass"] is False


def test_insufficient_data_skips(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_trap_risk_insufficient.json")
    result = evaluate_trap_risk(SymbolContext(symbol="META"), bundle, _trap_risk_config())
    assert result.outcome == DecisionOutcome.SKIP
    assert "Trap-risk requires at least" in result.reasons[0]


def test_trap_risk_output_is_deterministic(fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_trap_risk_clean.json")
    config = _trap_risk_config()
    first = evaluate_trap_risk(SymbolContext(symbol="NVDA"), bundle, config)
    second = evaluate_trap_risk(SymbolContext(symbol="NVDA"), bundle, config)
    assert first.outcome == second.outcome
    assert first.passed == second.passed
    assert first.metrics == second.metrics
    assert first.reasons == second.reasons
    assert first.flags == second.flags
