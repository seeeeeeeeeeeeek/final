from __future__ import annotations

from src.scanner.models import DecisionOutcome, ModuleResult, SymbolContext


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _round_score(value: float) -> float:
    return round(value, 2)


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _module_usable(result: ModuleResult) -> bool:
    return result.outcome == DecisionOutcome.PASS and result.passed


def _normalized_ratio(value: float | None, cap: float) -> float:
    if value is None or cap <= 0:
        return 0.0
    return _clamp(value / cap, 0.0, 1.0)


def _trend_alignment_score(result: ModuleResult, weight: float, reasons: list[str], debug_notes: list[str]) -> float:
    trend_strength = _safe_float(result.metrics.get("trend_strength_score"))
    if trend_strength is None:
        reasons.append("Trend alignment score defaulted to zero because trend_strength_score was unavailable.")
        return 0.0
    if result.outcome == DecisionOutcome.SKIP:
        reasons.append("Trend alignment score was reduced to zero because the trend filter skipped.")
        return 0.0
    normalized = _clamp(trend_strength / 100.0, 0.0, 1.0)
    if not _module_usable(result):
        debug_notes.append("Trend filter failed; trend alignment score is discounted to avoid overstating a weak setup.")
        normalized *= 0.25
    return weight * normalized


def _squeeze_quality_score(result: ModuleResult, weight: float, reasons: list[str], debug_notes: list[str]) -> float:
    if result.outcome == DecisionOutcome.SKIP:
        reasons.append("Squeeze quality score defaulted to zero because compression skipped.")
        return 0.0

    range_contraction = _safe_float(result.metrics.get("range_contraction_pct"))
    volatility_contraction = _safe_float(result.metrics.get("volatility_contraction_pct"))
    compression_depth = _safe_float(result.metrics.get("compression_depth_pct"))
    base_position = _safe_float(result.metrics.get("base_position_pct"))
    if None in (range_contraction, volatility_contraction, compression_depth, base_position):
        reasons.append("Squeeze quality score defaulted to zero because compression metrics were incomplete.")
        return 0.0

    range_quality = _normalized_ratio(range_contraction, 100.0)
    volatility_quality = _normalized_ratio(volatility_contraction, 100.0)
    shallow_depth_quality = 1.0 - _normalized_ratio(compression_depth, 100.0)
    position_quality = _normalized_ratio(base_position, 100.0)
    bonus = 0.05 if bool(result.metrics.get("volume_dry_up_bonus_applied")) else 0.0

    normalized = _clamp(
        (range_quality + volatility_quality + shallow_depth_quality + position_quality) / 4.0 + bonus,
        0.0,
        1.0,
    )
    if not _module_usable(result):
        debug_notes.append("Compression failed; squeeze quality score is discounted.")
        normalized *= 0.25
    return weight * normalized


def _breakout_impulse_score(result: ModuleResult, weight: float, reasons: list[str], debug_notes: list[str]) -> float:
    if result.outcome == DecisionOutcome.SKIP:
        reasons.append("Breakout impulse score defaulted to zero because breakout trigger skipped.")
        return 0.0

    breakout_range_vs_base = _safe_float(result.metrics.get("breakout_range_vs_base_avg"))
    relative_volume = _safe_float(result.metrics.get("relative_volume"))
    breakout_price = _safe_float(result.metrics.get("breakout_price"))
    trigger_level = _safe_float(result.metrics.get("trigger_level"))
    if None in (breakout_range_vs_base, breakout_price, trigger_level):
        reasons.append("Breakout impulse score defaulted to zero because breakout metrics were incomplete.")
        return 0.0

    range_quality = _normalized_ratio(breakout_range_vs_base, 3.0)
    volume_quality = _normalized_ratio(relative_volume if relative_volume is not None else 0.0, 2.0)
    buffer_clearance = 0.0
    if trigger_level > 0:
        buffer_clearance = _clamp((breakout_price - trigger_level) / trigger_level, 0.0, 0.02)
    buffer_quality = _normalized_ratio(buffer_clearance, 0.02)
    followthrough_quality = 1.0 if bool(result.flags.get("follow_through_pass")) else 0.0

    normalized = (range_quality + volume_quality + buffer_quality + followthrough_quality) / 4.0
    if not _module_usable(result):
        debug_notes.append("Breakout trigger failed; breakout impulse score is discounted.")
        normalized *= 0.25
    return weight * normalized


def _path_quality_score(result: ModuleResult, weight: float, reasons: list[str], debug_notes: list[str]) -> float:
    if result.outcome == DecisionOutcome.SKIP:
        reasons.append("Path quality score defaulted to zero because trap-risk skipped.")
        return 0.0

    overhead_clearance = _safe_float(result.metrics.get("overhead_clearance_pct"))
    distance_from_trend_ref = _safe_float(result.metrics.get("distance_from_trend_ref_pct"))
    rejection_wick_pct = _safe_float(result.metrics.get("rejection_wick_pct"))
    abnormal_gap_pct = _safe_float(result.metrics.get("abnormal_gap_pct"))
    weak_followthrough = bool(result.metrics.get("weak_followthrough_detected"))

    if None in (distance_from_trend_ref, rejection_wick_pct, abnormal_gap_pct):
        reasons.append("Path quality score defaulted to zero because trap-risk metrics were incomplete.")
        return 0.0

    clearance_quality = 0.5 if overhead_clearance is None else _normalized_ratio(overhead_clearance, 10.0)
    extension_quality = 1.0 - _normalized_ratio(distance_from_trend_ref, 10.0)
    rejection_quality = 1.0 - _normalized_ratio(rejection_wick_pct, 50.0)
    gap_quality = 1.0 - _normalized_ratio(abnormal_gap_pct, 10.0)
    followthrough_quality = 0.0 if weak_followthrough else 1.0

    normalized = (clearance_quality + extension_quality + rejection_quality + gap_quality + followthrough_quality) / 5.0
    if result.outcome == DecisionOutcome.NO_TRADE or bool(result.flags.get("trap_risk_elevated")):
        debug_notes.append("Trap-risk was elevated; path quality score is discounted.")
        normalized *= 0.5
    return weight * normalized


def _trap_risk_penalty_score(result: ModuleResult, weight: float, reasons: list[str]) -> float:
    if result.outcome == DecisionOutcome.SKIP:
        reasons.append("Trap-risk penalty was not applied because trap-risk skipped.")
        return 0.0

    penalty_count = _safe_float(result.metrics.get("trap_risk_penalty"))
    if penalty_count is None:
        reasons.append("Trap-risk penalty defaulted to zero because the penalty metric was unavailable.")
        return 0.0

    penalty_fraction = _clamp(penalty_count / 5.0, 0.0, 1.0)
    return -(weight * penalty_fraction)


def evaluate_quality_score(
    symbol_context: SymbolContext,
    scoring_config: dict,
    trend_result: ModuleResult,
    compression_result: ModuleResult,
    breakout_result: ModuleResult,
    trap_risk_result: ModuleResult,
) -> ModuleResult:
    """Build a deterministic 0-100 ranking score from existing module outputs."""
    _ = symbol_context
    scoring_settings = scoring_config.get("scoring", {})
    weights = scoring_settings.get("weights", {})
    normalization = scoring_settings.get("normalization", {})
    clamp_min = float(normalization.get("clamp_min", 0.0))
    clamp_max = float(normalization.get("clamp_max", 100.0))

    reasons: list[str] = []
    debug_notes: list[str] = []

    trend_alignment = _trend_alignment_score(
        trend_result,
        float(weights.get("trend_alignment", 0.0)),
        reasons,
        debug_notes,
    )
    squeeze_quality = _squeeze_quality_score(
        compression_result,
        float(weights.get("squeeze_quality", 0.0)),
        reasons,
        debug_notes,
    )
    breakout_impulse = _breakout_impulse_score(
        breakout_result,
        float(weights.get("breakout_impulse", 0.0)),
        reasons,
        debug_notes,
    )
    path_quality = _path_quality_score(
        trap_risk_result,
        float(weights.get("path_quality", 0.0)),
        reasons,
        debug_notes,
    )
    trap_risk_penalty = _trap_risk_penalty_score(
        trap_risk_result,
        float(weights.get("trap_risk_penalty", 0.0)),
        reasons,
    )

    raw_total = trend_alignment + squeeze_quality + breakout_impulse + path_quality + trap_risk_penalty
    total = _clamp(raw_total, clamp_min, clamp_max)

    if not reasons:
        reasons.append("Quality score combined trend, squeeze, breakout, path quality, and trap-risk penalty into a ranking score.")
    if raw_total != total:
        debug_notes.append("Final score was clamped to configured normalization bounds.")

    return ModuleResult(
        module_name="quality_score",
        outcome=DecisionOutcome.PASS,
        passed=True,
        metrics={
            "total": _round_score(total),
            "trend_alignment": _round_score(trend_alignment),
            "squeeze_quality": _round_score(squeeze_quality),
            "breakout_impulse": _round_score(breakout_impulse),
            "path_quality": _round_score(path_quality),
            "trap_risk_penalty": _round_score(trap_risk_penalty),
        },
        reasons=reasons,
        flags={
            "score_available": True,
            "low_confidence_score": any(
                result.outcome == DecisionOutcome.SKIP or not result.passed
                for result in (trend_result, compression_result, breakout_result, trap_risk_result)
            ),
            "trap_risk_penalty_applied": trap_risk_penalty < 0.0,
        },
        debug_notes=debug_notes,
    )
