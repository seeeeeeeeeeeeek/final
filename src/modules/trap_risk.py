from __future__ import annotations

from src.modules.breakout_trigger import evaluate_breakout_trigger
from src.modules.compression import evaluate_compression
from src.scanner.models import DecisionOutcome, MarketDataBundle, ModuleResult, SymbolContext


def _round_metric(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def _build_skip_result(
    reason: str,
    *,
    distance_from_trend_ref_pct: float | None = None,
    rejection_wick_pct: float | None = None,
    overhead_clearance_pct: float | None = None,
    weak_followthrough_detected: bool = False,
    abnormal_gap_pct: float | None = None,
) -> ModuleResult:
    return ModuleResult(
        module_name="trap_risk",
        outcome=DecisionOutcome.SKIP,
        passed=False,
        metrics={
            "distance_from_trend_ref_pct": _round_metric(distance_from_trend_ref_pct),
            "rejection_wick_pct": _round_metric(rejection_wick_pct),
            "overhead_clearance_pct": _round_metric(overhead_clearance_pct),
            "weak_followthrough_detected": weak_followthrough_detected,
            "abnormal_gap_pct": _round_metric(abnormal_gap_pct),
            "trap_risk_penalty": 0,
        },
        reasons=[reason],
        flags={
            "trap_risk_elevated": False,
            "extension_risk_pass": False,
            "rejection_wick_pass": False,
            "overhead_clearance_pass": False,
            "followthrough_risk_pass": False,
            "abnormal_gap_pass": False,
        },
        debug_notes=["Trap-risk detector skipped because a required risk input could not be evaluated cleanly."],
    )


def _pct_distance(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return (numerator / denominator) * 100.0


def _nearest_overhead_resistance(hourly_bars: list[dict], breakout_price: float) -> float | None:
    overhead_candidates = []
    for bar in hourly_bars:
        high = bar.get("high")
        if high is None:
            return None
        high_value = float(high)
        if high_value > breakout_price:
            overhead_candidates.append(high_value)
    if not overhead_candidates:
        return None
    return min(overhead_candidates)


def evaluate_trap_risk(
    symbol_context: SymbolContext,
    market_data: MarketDataBundle,
    config: dict,
) -> ModuleResult:
    """Flag technically valid breakouts whose immediate structure is too risky to treat as clean."""
    _ = symbol_context
    settings = config.get("trap_risk", {})
    breakout_settings = config.get("breakout_trigger", {})

    compression_result = evaluate_compression(symbol_context, market_data, config)
    if compression_result.outcome == DecisionOutcome.SKIP or not compression_result.passed:
        primary_reason = compression_result.reasons[0] if compression_result.reasons else "Compression reference unavailable."
        return _build_skip_result(f"Trap-risk requires a valid compression reference: {primary_reason}")

    breakout_result = evaluate_breakout_trigger(symbol_context, market_data, config)
    if breakout_result.outcome == DecisionOutcome.SKIP:
        primary_reason = breakout_result.reasons[0] if breakout_result.reasons else "Breakout trigger reference unavailable."
        return _build_skip_result(f"Trap-risk requires a valid breakout trigger reference: {primary_reason}")
    if not breakout_result.passed:
        primary_reason = breakout_result.reasons[0] if breakout_result.reasons else "Breakout trigger did not pass."
        return _build_skip_result(f"Trap-risk only evaluates otherwise valid breakouts: {primary_reason}")

    hourly_bars = market_data.hourly.bars
    intraday_bars = market_data.intraday_5m.bars

    compression_high = compression_result.metrics.get("compression_high")
    compression_low = compression_result.metrics.get("compression_low")
    compression_length = compression_result.metrics.get("compression_length_bars")
    breakout_price = breakout_result.metrics.get("breakout_price")
    trigger_level = breakout_result.metrics.get("trigger_level")

    if any(value is None for value in (compression_high, compression_low, compression_length, breakout_price, trigger_level)):
        return _build_skip_result("Trap-risk requires compression high/low, compression length, trigger level, and breakout price.")

    compression_high = float(compression_high)
    compression_low = float(compression_low)
    compression_length = int(compression_length)
    breakout_price = float(breakout_price)
    trigger_level = float(trigger_level)

    breakout_bar = intraday_bars[0] if intraday_bars else None
    if breakout_bar is None:
        return _build_skip_result("Trap-risk requires the breakout 5m bar.")
    for field in ("open", "high", "low", "close"):
        if breakout_bar.get(field) is None:
            return _build_skip_result(f"Trap-risk requires breakout bar field '{field}'.")

    if len(hourly_bars) <= compression_length:
        return _build_skip_result("Trap-risk could not estimate overhead resistance because no hourly bars exist before the active compression base.")

    confirmation_count = int(breakout_settings.get("confirmation_bar_count", 2))
    post_trigger_window = int(settings.get("maximum_failed_follow_through_bars", 2))
    required_intraday_bars = 1 + confirmation_count + post_trigger_window
    if len(intraday_bars) < required_intraday_bars:
        return _build_skip_result(
            f"Trap-risk requires at least {required_intraday_bars} 5m bars to evaluate immediate post-trigger behavior.",
        )

    trend_reference = (compression_high + compression_low) / 2.0
    distance_from_trend_ref_pct = _pct_distance(breakout_price - trend_reference, trend_reference)
    if distance_from_trend_ref_pct is None:
        return _build_skip_result("Trap-risk could not compute distance from the compression midpoint reference.")

    breakout_high = float(breakout_bar["high"])
    breakout_low = float(breakout_bar["low"])
    breakout_open = float(breakout_bar["open"])
    breakout_close = float(breakout_bar["close"])
    breakout_range = breakout_high - breakout_low
    if breakout_range <= 0:
        return _build_skip_result("Trap-risk requires a breakout bar with non-zero range.", distance_from_trend_ref_pct=distance_from_trend_ref_pct)

    rejection_wick_pct = _pct_distance(breakout_high - max(breakout_open, breakout_close), breakout_range)
    if rejection_wick_pct is None:
        return _build_skip_result(
            "Trap-risk could not compute breakout rejection wick percentage.",
            distance_from_trend_ref_pct=distance_from_trend_ref_pct,
        )

    prior_hourly_bars = hourly_bars[:-compression_length]
    nearest_overhead = _nearest_overhead_resistance(prior_hourly_bars, breakout_price)
    if nearest_overhead is None and not prior_hourly_bars:
        return _build_skip_result(
            "Trap-risk could not estimate nearby overhead resistance from prior hourly highs.",
            distance_from_trend_ref_pct=distance_from_trend_ref_pct,
            rejection_wick_pct=rejection_wick_pct,
        )
    overhead_clearance_pct = None
    if nearest_overhead is not None:
        overhead_clearance_pct = _pct_distance(nearest_overhead - breakout_price, breakout_price)
        if overhead_clearance_pct is None:
            return _build_skip_result(
                "Trap-risk could not compute overhead clearance percentage.",
                distance_from_trend_ref_pct=distance_from_trend_ref_pct,
                rejection_wick_pct=rejection_wick_pct,
            )

    post_trigger_bars = intraday_bars[1 + confirmation_count : 1 + confirmation_count + post_trigger_window]
    for bar in post_trigger_bars:
        if bar.get("low") is None or bar.get("close") is None:
            return _build_skip_result(
                "Trap-risk requires low and close values for immediate post-trigger 5m bars.",
                distance_from_trend_ref_pct=distance_from_trend_ref_pct,
                rejection_wick_pct=rejection_wick_pct,
                overhead_clearance_pct=overhead_clearance_pct,
            )

    weak_followthrough_detected = any(
        float(bar["low"]) < trigger_level or float(bar["close"]) < trigger_level for bar in post_trigger_bars
    )

    abnormal_gap_pct = 0.0
    abnormal_gap_pass = True
    prior_session_close = hourly_bars[-1].get("close") if hourly_bars else None
    if prior_session_close is not None:
        abnormal_gap_pct_value = _pct_distance(abs(breakout_open - float(prior_session_close)), float(prior_session_close))
        if abnormal_gap_pct_value is not None:
            abnormal_gap_pct = abnormal_gap_pct_value
            abnormal_gap_pass = abnormal_gap_pct <= float(settings.get("abnormal_gap_threshold_pct", 100.0))

    extension_risk_pass = distance_from_trend_ref_pct <= float(settings.get("maximum_distance_from_trend_ref_pct", 100.0))
    rejection_wick_pass = rejection_wick_pct <= float(settings.get("maximum_rejection_wick_pct", 100.0))
    overhead_clearance_pass = True
    minimum_clearance = float(settings.get("minimum_overhead_clearance_pct", 0.0))
    if overhead_clearance_pct is not None:
        overhead_clearance_pass = overhead_clearance_pct >= minimum_clearance
    followthrough_risk_pass = not weak_followthrough_detected

    failed_checks = [
        not extension_risk_pass,
        not rejection_wick_pass,
        not overhead_clearance_pass,
        not followthrough_risk_pass,
        not abnormal_gap_pass,
    ]
    trap_risk_penalty = sum(1 for failed in failed_checks if failed)

    reasons: list[str] = []
    if not extension_risk_pass:
        reasons.append("Breakout is too extended from the compression midpoint reference.")
    if not rejection_wick_pass:
        reasons.append("Breakout bar shows excessive upper-wick rejection.")
    if not overhead_clearance_pass:
        reasons.append("Breakout is too close to nearby hourly overhead resistance.")
    if not followthrough_risk_pass:
        reasons.append("Immediate post-trigger 5m action fell back below the trigger level.")
    if not abnormal_gap_pass:
        reasons.append("Breakout opened with an abnormal gap beyond the configured threshold.")
    if trap_risk_penalty == 0:
        reasons.append("Trap-risk checks passed with acceptable extension, rejection, overhead clearance, and post-trigger behavior.")

    return ModuleResult(
        module_name="trap_risk",
        outcome=DecisionOutcome.PASS if trap_risk_penalty == 0 else DecisionOutcome.NO_TRADE,
        passed=trap_risk_penalty == 0,
        metrics={
            "distance_from_trend_ref_pct": _round_metric(distance_from_trend_ref_pct),
            "rejection_wick_pct": _round_metric(rejection_wick_pct),
            "overhead_clearance_pct": _round_metric(overhead_clearance_pct),
            "weak_followthrough_detected": weak_followthrough_detected,
            "abnormal_gap_pct": _round_metric(abnormal_gap_pct),
            "trap_risk_penalty": trap_risk_penalty,
        },
        reasons=reasons,
        flags={
            "trap_risk_elevated": trap_risk_penalty > 0,
            "extension_risk_pass": extension_risk_pass,
            "rejection_wick_pass": rejection_wick_pass,
            "overhead_clearance_pass": overhead_clearance_pass,
            "followthrough_risk_pass": followthrough_risk_pass,
            "abnormal_gap_pass": abnormal_gap_pass,
        },
        debug_notes=[
            "Trap-risk used compression midpoint, breakout bar structure, prior hourly highs, and post-confirmation 5m behavior.",
        ],
    )
