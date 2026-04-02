from __future__ import annotations

from statistics import fmean

from src.scanner.models import DecisionOutcome, MarketDataBundle, ModuleResult, SymbolContext


def _simple_moving_average(values: list[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    return fmean(values[-period:])


def _moving_average_slope(values: list[float], period: int) -> float | None:
    if period <= 0 or len(values) < period + 1:
        return None
    current = _simple_moving_average(values, period)
    previous = _simple_moving_average(values[:-1], period)
    if current is None or previous is None or previous == 0:
        return None
    return ((current - previous) / previous) * 100.0


def _compute_structure_flags(closes: list[float], lows: list[float], lookback: int = 3) -> tuple[bool | None, bool | None]:
    if len(closes) < lookback + 1 or len(lows) < lookback + 1:
        return None, None
    recent_closes = closes[-lookback:]
    prior_closes = closes[-(lookback + 1) : -1]
    recent_lows = lows[-lookback:]
    prior_lows = lows[-(lookback + 1) : -1]
    higher_highs = all(current > previous for current, previous in zip(recent_closes, prior_closes))
    higher_lows = all(current > previous for current, previous in zip(recent_lows, prior_lows))
    return higher_highs, higher_lows


def evaluate_trend_filter(
    symbol_context: SymbolContext,
    market_data: MarketDataBundle,
    config: dict,
) -> ModuleResult:
    """Evaluate a simple daily bullish trend using configurable moving-average checks."""
    _ = symbol_context
    settings = config.get("trend_filter", {})
    daily_bars = market_data.daily.bars
    fast_period = int(settings.get("moving_average_periods", {}).get("fast", 20))
    slow_period = int(settings.get("moving_average_periods", {}).get("slow", 50))
    min_bars = max(fast_period, slow_period) + 1

    if len(daily_bars) < min_bars:
        return ModuleResult(
            module_name="trend_filter",
            outcome=DecisionOutcome.SKIP,
            passed=False,
            metrics={"trend_strength_score": 0.0, "daily_bar_count": len(daily_bars)},
            reasons=[f"Insufficient daily bars for trend filter; need at least {min_bars}."],
            flags={"daily_trend_pass": False, "insufficient_daily_data": True},
            debug_notes=["Trend filter skipped due to insufficient daily history."],
        )

    closes: list[float] = []
    lows: list[float] = []
    for bar in daily_bars:
        close = bar.get("close")
        low = bar.get("low")
        if close is None or low is None:
            return ModuleResult(
                module_name="trend_filter",
                outcome=DecisionOutcome.SKIP,
                passed=False,
                metrics={"trend_strength_score": 0.0, "daily_bar_count": len(daily_bars)},
                reasons=["Daily trend filter requires close and low values for each bar."],
                flags={"daily_trend_pass": False, "insufficient_daily_data": True},
                debug_notes=["Trend filter skipped because required daily fields were missing."],
            )
        closes.append(float(close))
        lows.append(float(low))

    latest_close = closes[-1]
    fast_ma = _simple_moving_average(closes, fast_period)
    slow_ma = _simple_moving_average(closes, slow_period)
    fast_slope_pct = _moving_average_slope(closes, fast_period)

    if fast_ma is None or slow_ma is None:
        return ModuleResult(
            module_name="trend_filter",
            outcome=DecisionOutcome.SKIP,
            passed=False,
            metrics={"trend_strength_score": 0.0, "daily_bar_count": len(daily_bars)},
            reasons=["Unable to compute moving averages from provided daily bars."],
            flags={"daily_trend_pass": False, "insufficient_daily_data": True},
            debug_notes=["Trend filter skipped because moving averages could not be computed."],
        )

    require_fast = bool(settings.get("require_price_above_fast_ma", True))
    require_slow = bool(settings.get("require_price_above_slow_ma", True))
    require_structure = bool(settings.get("require_higher_high_higher_low_structure", True))
    min_slope_pct = float(settings.get("minimum_slope_pct", 0.0))

    checks: list[tuple[str, bool]] = []
    reasons: list[str] = []

    price_above_fast = latest_close > fast_ma if require_fast else True
    checks.append(("price_above_fast_ma", price_above_fast))
    if not price_above_fast:
        reasons.append("Latest close is below the configured fast moving average.")

    price_above_slow = latest_close > slow_ma if require_slow else True
    checks.append(("price_above_slow_ma", price_above_slow))
    if not price_above_slow:
        reasons.append("Latest close is below the configured slow moving average.")

    bullish_alignment = fast_ma >= slow_ma
    checks.append(("fast_ma_above_or_equal_slow_ma", bullish_alignment))
    if not bullish_alignment:
        reasons.append("Fast moving average is below the slow moving average.")

    slope_pass = True
    if min_slope_pct > 0.0:
        slope_pass = fast_slope_pct is not None and fast_slope_pct >= min_slope_pct
        checks.append(("fast_ma_slope_pass", slope_pass))
        if not slope_pass:
            reasons.append("Fast moving average slope is below the configured minimum.")

    higher_highs = True
    higher_lows = True
    if require_structure:
        higher_high_value, higher_low_value = _compute_structure_flags(closes, lows)
        if higher_high_value is None or higher_low_value is None:
            return ModuleResult(
                module_name="trend_filter",
                outcome=DecisionOutcome.SKIP,
                passed=False,
                metrics={"trend_strength_score": 0.0, "daily_bar_count": len(daily_bars)},
                reasons=["Not enough daily bars to evaluate higher-high / higher-low structure."],
                flags={"daily_trend_pass": False, "insufficient_daily_data": True},
                debug_notes=["Trend filter skipped because structure lookback could not be computed."],
            )
        higher_highs = higher_high_value
        higher_lows = higher_low_value
        structure_pass = higher_highs and higher_lows
        checks.append(("higher_high_higher_low_structure", structure_pass))
        if not structure_pass:
            reasons.append("Daily structure does not show the configured higher-high / higher-low pattern.")

    passed_checks = sum(1 for _, passed in checks if passed)
    total_checks = len(checks)
    trend_strength_score = round((passed_checks / total_checks) * 100.0, 2) if total_checks else 0.0
    min_score = float(settings.get("minimum_trend_strength_score", 0.0))
    score_pass = trend_strength_score >= min_score
    if not score_pass:
        reasons.append("Trend strength score is below the configured minimum threshold.")

    passed = all(passed for _, passed in checks) and score_pass
    if passed and not reasons:
        reasons.append("Daily trend passed configured moving-average and structure checks.")

    return ModuleResult(
        module_name="trend_filter",
        outcome=DecisionOutcome.PASS if passed else DecisionOutcome.FAIL,
        passed=passed,
        metrics={
            "trend_strength_score": trend_strength_score,
            "daily_bar_count": len(daily_bars),
            "latest_close": round(latest_close, 4),
            "fast_ma": round(fast_ma, 4),
            "slow_ma": round(slow_ma, 4),
            "fast_ma_slope_pct": round(fast_slope_pct or 0.0, 4),
            "price_above_fast_ma": price_above_fast,
            "price_above_slow_ma": price_above_slow,
            "fast_ma_gte_slow_ma": bullish_alignment,
            "higher_highs": higher_highs,
            "higher_lows": higher_lows,
        },
        reasons=reasons,
        flags={
            "daily_trend_pass": passed,
            "price_above_fast_ma": price_above_fast,
            "price_above_slow_ma": price_above_slow,
            "fast_ma_gte_slow_ma": bullish_alignment,
            "higher_high_higher_low_structure": higher_highs and higher_lows,
        },
        debug_notes=["Daily trend filter evaluated using configurable moving-average and structure checks."],
    )
