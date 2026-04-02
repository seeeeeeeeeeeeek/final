from __future__ import annotations

from statistics import fmean

from src.modules.compression import evaluate_compression
from src.scanner.models import DecisionOutcome, MarketDataBundle, ModuleResult, SymbolContext


def _build_skip_result(reason: str, hourly_bar_count: int, intraday_bar_count: int) -> ModuleResult:
    return ModuleResult(
        module_name="breakout_trigger",
        outcome=DecisionOutcome.SKIP,
        passed=False,
        metrics={
            "compression_high": 0.0,
            "trigger_level": 0.0,
            "breakout_price": 0.0,
            "breakout_range_vs_base_avg": 0.0,
            "relative_volume": 0.0,
            "follow_through_pass": False,
            "confirmation_bar_count_used": 0,
            "breakout_timestamp_utc": None,
            "hourly_bar_count": hourly_bar_count,
            "intraday_bar_count": intraday_bar_count,
        },
        reasons=[reason],
        flags={
            "trigger_pass": False,
            "breakout_above_level_pass": False,
            "breakout_buffer_pass": False,
            "breakout_expansion_pass": False,
            "volume_confirmation_pass": False,
            "follow_through_pass": False,
        },
        debug_notes=["Breakout trigger skipped due to insufficient or malformed hourly/5m data."],
    )


def evaluate_breakout_trigger(
    symbol_context: SymbolContext,
    market_data: MarketDataBundle,
    config: dict,
) -> ModuleResult:
    """Evaluate a bullish breakout above the selected compression high with simple 5m confirmation."""
    _ = symbol_context
    settings = config.get("breakout_trigger", {})
    hourly_bars = market_data.hourly.bars
    intraday_bars = market_data.intraday_5m.bars
    confirmation_count = int(settings.get("confirmation_bar_count", 2))

    if len(hourly_bars) == 0:
        return _build_skip_result("Breakout trigger requires hourly bars to derive compression reference levels.", 0, len(intraday_bars))
    required_intraday_bars = confirmation_count + 1
    if len(intraday_bars) < required_intraday_bars:
        return _build_skip_result(
            f"Insufficient 5m bars for breakout confirmation; need at least {required_intraday_bars}.",
            len(hourly_bars),
            len(intraday_bars),
        )

    required_intraday_fields = ["high", "low", "close", "timestamp_utc"]
    if bool(settings.get("use_volume_confirmation", False)):
        required_intraday_fields.append("volume")
    for bar in intraday_bars:
        if any(bar.get(field) is None for field in required_intraday_fields):
            return _build_skip_result(
                "Breakout trigger requires high, low, close, timestamp_utc, and any enabled confirmation fields for each 5m bar.",
                len(hourly_bars),
                len(intraday_bars),
            )

    compression_result = evaluate_compression(symbol_context, market_data, config)
    if compression_result.outcome == DecisionOutcome.SKIP:
        return _build_skip_result(
            f"Breakout trigger could not evaluate compression reference: {compression_result.reasons[0]}",
            len(hourly_bars),
            len(intraday_bars),
        )
    if not compression_result.metrics.get("compression_high") or not compression_result.metrics.get("compression_length_bars"):
        return _build_skip_result(
            "Breakout trigger did not receive usable compression reference metrics.",
            len(hourly_bars),
            len(intraday_bars),
        )

    compression_high = float(compression_result.metrics["compression_high"])
    compression_length = int(compression_result.metrics["compression_length_bars"])
    base_bars = hourly_bars[-compression_length:]
    base_ranges = [float(bar["high"]) - float(bar["low"]) for bar in base_bars]
    if not base_ranges or any(base_range <= 0 for base_range in base_ranges):
        return _build_skip_result(
            "Breakout trigger could not compute average base range from compression bars.",
            len(hourly_bars),
            len(intraday_bars),
        )
    base_avg_range = fmean(base_ranges)
    base_volumes = [float(bar["volume"]) for bar in base_bars if bar.get("volume") is not None]
    base_avg_volume = fmean(base_volumes) if base_volumes else 0.0

    buffer_pct = float(settings.get("breakout_buffer_pct", 0.0))
    trigger_level = compression_high * (1.0 + (buffer_pct / 100.0))
    breakout_bar = intraday_bars[0]
    breakout_high = float(breakout_bar["high"])
    breakout_low = float(breakout_bar["low"])
    breakout_close = float(breakout_bar["close"])
    breakout_range = breakout_high - breakout_low
    breakout_timestamp = breakout_bar["timestamp_utc"]

    breakout_above_level_pass = breakout_high > compression_high and breakout_close > compression_high
    breakout_buffer_pass = breakout_close >= trigger_level
    breakout_range_vs_base_avg = round((breakout_range / base_avg_range), 4) if base_avg_range > 0 else 0.0
    breakout_expansion_pass = breakout_range_vs_base_avg >= float(
        settings.get("minimum_breakout_range_vs_base_avg", 0.0)
    )

    use_volume_confirmation = bool(settings.get("use_volume_confirmation", False))
    relative_volume = (
        round((float(breakout_bar["volume"]) / base_avg_volume), 4)
        if use_volume_confirmation and base_avg_volume > 0
        else 0.0
    )
    volume_confirmation_pass = True
    if use_volume_confirmation:
        volume_confirmation_pass = relative_volume >= float(settings.get("minimum_relative_volume", 0.0))

    confirmation_bars = intraday_bars[1 : 1 + confirmation_count]
    follow_through_pass = all(
        float(bar["close"]) >= compression_high and float(bar["low"]) >= compression_high
        for bar in confirmation_bars
    )

    reasons: list[str] = []
    if not breakout_above_level_pass:
        reasons.append("Breakout did not close clearly above the compression high.")
    if not breakout_buffer_pass:
        reasons.append("Breakout close did not clear the configured trigger buffer above the compression high.")
    if not breakout_expansion_pass:
        reasons.append("Breakout bar did not expand enough relative to the compression base average range.")
    if use_volume_confirmation and not volume_confirmation_pass:
        reasons.append("Breakout did not meet the configured relative volume threshold.")
    if not follow_through_pass:
        reasons.append("Immediate 5m follow-through failed because price fell back into the base.")

    passed = all(
        (
            breakout_above_level_pass,
            breakout_buffer_pass,
            breakout_expansion_pass,
            volume_confirmation_pass,
            follow_through_pass,
        )
    )
    if passed:
        reasons.append("Breakout cleared the compression high with required expansion and acceptable 5m follow-through.")

    return ModuleResult(
        module_name="breakout_trigger",
        outcome=DecisionOutcome.PASS if passed else DecisionOutcome.FAIL,
        passed=passed,
        metrics={
            "compression_high": round(compression_high, 4),
            "trigger_level": round(trigger_level, 4),
            "breakout_price": round(breakout_close, 4),
            "breakout_range_vs_base_avg": breakout_range_vs_base_avg,
            "relative_volume": relative_volume,
            "follow_through_pass": follow_through_pass,
            "confirmation_bar_count_used": confirmation_count,
            "breakout_timestamp_utc": breakout_timestamp,
        },
        reasons=reasons,
        flags={
            "trigger_pass": passed,
            "breakout_above_level_pass": breakout_above_level_pass,
            "breakout_buffer_pass": breakout_buffer_pass,
            "breakout_expansion_pass": breakout_expansion_pass,
            "volume_confirmation_pass": volume_confirmation_pass,
            "follow_through_pass": follow_through_pass,
        },
        debug_notes=[
            "Breakout trigger evaluated the first available 5m breakout bar against compression reference levels."
        ],
    )
