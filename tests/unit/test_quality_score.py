from src.modules.quality_score import evaluate_quality_score
from src.scanner.models import DecisionOutcome, ModuleResult, SymbolContext


def _scoring_config() -> dict:
    return {
        "scoring": {
            "total_score_max": 100.0,
            "weights": {
                "trend_alignment": 20.0,
                "squeeze_quality": 25.0,
                "breakout_impulse": 25.0,
                "path_quality": 20.0,
                "trap_risk_penalty": 10.0,
            },
            "normalization": {
                "clamp_min": 0.0,
                "clamp_max": 100.0,
            },
        }
    }


def _trend_result(*, passed: bool = True, outcome: DecisionOutcome = DecisionOutcome.PASS, trend_strength: float = 100.0) -> ModuleResult:
    return ModuleResult(
        module_name="trend_filter",
        outcome=outcome,
        passed=passed,
        metrics={"trend_strength_score": trend_strength},
        flags={"daily_trend_pass": passed},
    )


def _compression_result(
    *,
    passed: bool = True,
    outcome: DecisionOutcome = DecisionOutcome.PASS,
    range_contraction: float = 45.0,
    volatility_contraction: float = 35.0,
    depth: float = 18.0,
    base_position: float = 82.0,
    dry_up_bonus: bool = True,
) -> ModuleResult:
    return ModuleResult(
        module_name="compression",
        outcome=outcome,
        passed=passed,
        metrics={
            "range_contraction_pct": range_contraction,
            "volatility_contraction_pct": volatility_contraction,
            "compression_depth_pct": depth,
            "base_position_pct": base_position,
            "volume_dry_up_bonus_applied": dry_up_bonus,
        },
        flags={"compression_pass": passed},
    )


def _breakout_result(
    *,
    passed: bool = True,
    outcome: DecisionOutcome = DecisionOutcome.PASS,
    expansion: float = 2.4,
    relative_volume: float = 1.8,
    breakout_price: float = 112.0,
    trigger_level: float = 110.5,
    followthrough: bool = True,
) -> ModuleResult:
    return ModuleResult(
        module_name="breakout_trigger",
        outcome=outcome,
        passed=passed,
        metrics={
            "breakout_range_vs_base_avg": expansion,
            "relative_volume": relative_volume,
            "breakout_price": breakout_price,
            "trigger_level": trigger_level,
        },
        flags={"follow_through_pass": followthrough, "trigger_pass": passed},
    )


def _trap_risk_result(
    *,
    passed: bool = True,
    outcome: DecisionOutcome = DecisionOutcome.PASS,
    overhead_clearance: float | None = 4.0,
    distance_from_ref: float = 3.0,
    rejection_wick: float = 8.0,
    abnormal_gap: float = 1.0,
    weak_followthrough: bool = False,
    penalty_count: float = 0.0,
) -> ModuleResult:
    return ModuleResult(
        module_name="trap_risk",
        outcome=outcome,
        passed=passed,
        metrics={
            "overhead_clearance_pct": overhead_clearance,
            "distance_from_trend_ref_pct": distance_from_ref,
            "rejection_wick_pct": rejection_wick,
            "abnormal_gap_pct": abnormal_gap,
            "weak_followthrough_detected": weak_followthrough,
            "trap_risk_penalty": penalty_count,
        },
        flags={"trap_risk_elevated": penalty_count > 0 or outcome == DecisionOutcome.NO_TRADE},
    )


def test_strong_setup_scores_higher_than_weak_setup() -> None:
    strong = evaluate_quality_score(
        SymbolContext(symbol="NVDA"),
        _scoring_config(),
        _trend_result(trend_strength=100.0),
        _compression_result(range_contraction=55.0, volatility_contraction=45.0, depth=12.0, base_position=90.0),
        _breakout_result(expansion=2.8, relative_volume=1.9, breakout_price=113.0, trigger_level=110.5),
        _trap_risk_result(overhead_clearance=5.0, distance_from_ref=2.5, rejection_wick=6.0),
    )
    weak = evaluate_quality_score(
        SymbolContext(symbol="AAPL"),
        _scoring_config(),
        _trend_result(trend_strength=70.0),
        _compression_result(range_contraction=20.0, volatility_contraction=15.0, depth=35.0, base_position=55.0, dry_up_bonus=False),
        _breakout_result(expansion=1.5, relative_volume=1.0, breakout_price=111.0, trigger_level=110.8),
        _trap_risk_result(overhead_clearance=2.0, distance_from_ref=7.5, rejection_wick=20.0),
    )
    assert strong.metrics["total"] > weak.metrics["total"]


def test_elevated_trap_risk_reduces_total_score() -> None:
    clean = evaluate_quality_score(
        SymbolContext(symbol="MSFT"),
        _scoring_config(),
        _trend_result(),
        _compression_result(),
        _breakout_result(),
        _trap_risk_result(penalty_count=0.0, outcome=DecisionOutcome.PASS, passed=True),
    )
    risky = evaluate_quality_score(
        SymbolContext(symbol="MSFT"),
        _scoring_config(),
        _trend_result(),
        _compression_result(),
        _breakout_result(),
        _trap_risk_result(
            penalty_count=3.0,
            outcome=DecisionOutcome.NO_TRADE,
            passed=False,
            overhead_clearance=1.0,
            distance_from_ref=9.0,
            rejection_wick=30.0,
            weak_followthrough=True,
        ),
    )
    assert risky.metrics["trap_risk_penalty"] < 0.0
    assert risky.metrics["total"] < clean.metrics["total"]


def test_failed_or_missing_upstream_modules_produce_stable_low_confidence_score() -> None:
    result = evaluate_quality_score(
        SymbolContext(symbol="TSLA"),
        _scoring_config(),
        _trend_result(passed=False, outcome=DecisionOutcome.FAIL, trend_strength=40.0),
        _compression_result(passed=False, outcome=DecisionOutcome.FAIL, range_contraction=10.0, volatility_contraction=8.0, depth=60.0, base_position=40.0),
        _breakout_result(passed=False, outcome=DecisionOutcome.SKIP, expansion=0.0, breakout_price=112.0, trigger_level=110.5, followthrough=False),
        _trap_risk_result(passed=False, outcome=DecisionOutcome.SKIP, overhead_clearance=None, penalty_count=0.0),
    )
    assert result.metrics["total"] >= 0.0
    assert result.metrics["total"] < 30.0
    assert result.flags["low_confidence_score"] is True


def test_quality_score_is_deterministic_for_identical_inputs() -> None:
    config = _scoring_config()
    inputs = (
        _trend_result(),
        _compression_result(),
        _breakout_result(),
        _trap_risk_result(),
    )
    first = evaluate_quality_score(SymbolContext(symbol="NVDA"), config, *inputs)
    second = evaluate_quality_score(SymbolContext(symbol="NVDA"), config, *inputs)
    assert first.outcome == second.outcome
    assert first.passed == second.passed
    assert first.metrics == second.metrics
    assert first.reasons == second.reasons
    assert first.flags == second.flags


def test_final_score_is_clamped_within_configured_bounds() -> None:
    result = evaluate_quality_score(
        SymbolContext(symbol="META"),
        {
            "scoring": {
                "weights": {
                    "trend_alignment": 80.0,
                    "squeeze_quality": 80.0,
                    "breakout_impulse": 80.0,
                    "path_quality": 80.0,
                    "trap_risk_penalty": 0.0,
                },
                "normalization": {"clamp_min": 0.0, "clamp_max": 100.0},
            }
        },
        _trend_result(),
        _compression_result(),
        _breakout_result(),
        _trap_risk_result(),
    )
    assert 0.0 <= result.metrics["total"] <= 100.0
    assert result.metrics["total"] == 100.0
