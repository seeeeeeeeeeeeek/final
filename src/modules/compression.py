from __future__ import annotations

from statistics import fmean

from src.scanner.models import DecisionOutcome, MarketDataBundle, ModuleResult, SymbolContext


def _average_range(bars: list[dict], *, start: int = 0, end: int | None = None) -> float | None:
    window = bars[start:end]
    if not window:
        return None
    ranges = [float(bar["high"]) - float(bar["low"]) for bar in window]
    return fmean(ranges)


def _average_volume(bars: list[dict]) -> float | None:
    volumes = [bar.get("volume") for bar in bars if bar.get("volume") is not None]
    if not volumes:
        return None
    return fmean(float(volume) for volume in volumes)


def _build_skip_result(reason: str, hourly_bar_count: int) -> ModuleResult:
    return ModuleResult(
        module_name="compression",
        outcome=DecisionOutcome.SKIP,
        passed=False,
        metrics={
            "compression_length_bars": 0,
            "compression_depth_pct": 0.0,
            "range_contraction_pct": 0.0,
            "volatility_contraction_pct": 0.0,
            "base_position_pct": 0.0,
            "prior_impulse_pct": 0.0,
            "volume_dry_up_bonus_applied": False,
            "hourly_bar_count": hourly_bar_count,
        },
        reasons=[reason],
        flags={
            "compression_pass": False,
            "compression_length_pass": False,
            "pullback_depth_pass": False,
            "range_contraction_pass": False,
            "volatility_contraction_pass": False,
            "upper_half_positioning_pass": False,
        },
        debug_notes=["Compression detector skipped due to insufficient or malformed hourly data."],
    )


def evaluate_compression(
    symbol_context: SymbolContext,
    market_data: MarketDataBundle,
    config: dict,
) -> ModuleResult:
    """Evaluate constructive hourly compression after a prior impulse using config-backed rules."""
    _ = symbol_context
    settings = config.get("compression", {})
    hourly_bars = market_data.hourly.bars
    minimum_base_bars = int(settings.get("minimum_base_bars", 5))
    maximum_base_bars = int(settings.get("maximum_base_bars", 20))

    required_bars = minimum_base_bars * 2
    if len(hourly_bars) < required_bars:
        return _build_skip_result(
            f"Insufficient hourly bars for compression detector; need at least {required_bars}.",
            len(hourly_bars),
        )

    for bar in hourly_bars:
        if bar.get("high") is None or bar.get("low") is None or bar.get("close") is None:
            return _build_skip_result(
                "Compression detector requires high, low, and close values for each hourly bar.",
                len(hourly_bars),
            )

    candidate_results: list[tuple[int, float, ModuleResult]] = []
    max_candidate = min(maximum_base_bars, len(hourly_bars) // 2)

    for length in range(minimum_base_bars, max_candidate + 1):
        base_bars = hourly_bars[-length:]
        impulse_bars = hourly_bars[-(length * 2) : -length]
        if len(impulse_bars) < length:
            continue

        base_high = max(float(bar["high"]) for bar in base_bars)
        base_low = min(float(bar["low"]) for bar in base_bars)
        latest_close = float(base_bars[-1]["close"])
        base_range = base_high - base_low
        impulse_high = max(float(bar["high"]) for bar in impulse_bars)
        impulse_low = min(float(bar["low"]) for bar in impulse_bars)
        impulse_range = impulse_high - impulse_low
        if impulse_range <= 0 or base_range <= 0:
            continue

        compression_depth_pct = round((base_range / impulse_range) * 100.0, 2)
        prior_impulse_pct = round((impulse_range / impulse_low) * 100.0, 2) if impulse_low > 0 else 0.0

        midpoint = max(1, length // 2)
        early_base_avg_range = _average_range(base_bars, end=midpoint)
        late_base_avg_range = _average_range(base_bars, start=midpoint)
        if early_base_avg_range is None or late_base_avg_range is None or early_base_avg_range <= 0:
            continue

        range_contraction_pct = round((1.0 - (late_base_avg_range / early_base_avg_range)) * 100.0, 2)
        impulse_avg_range = _average_range(impulse_bars)
        if impulse_avg_range is None or impulse_avg_range <= 0:
            continue

        volatility_contraction_pct = round((1.0 - ((base_range / length) / impulse_avg_range)) * 100.0, 2)
        base_position_pct = round(((latest_close - base_low) / base_range) * 100.0, 2)

        compression_length_pass = minimum_base_bars <= length <= maximum_base_bars
        pullback_depth_pass = compression_depth_pct <= float(settings.get("maximum_pullback_depth_pct", 100.0))
        range_contraction_pass = range_contraction_pct >= float(settings.get("minimum_range_contraction_pct", 0.0))
        volatility_contraction_pass = volatility_contraction_pct >= float(
            settings.get("minimum_volatility_contraction_pct", 0.0)
        )
        require_upper_half = bool(settings.get("require_upper_half_positioning", True))
        upper_half_positioning_pass = (base_position_pct >= 50.0) if require_upper_half else True

        volume_dry_up_bonus_applied = False
        if bool(settings.get("enable_volume_dry_up_bonus", False)):
            early_volume = _average_volume(base_bars[:midpoint])
            late_volume = _average_volume(base_bars[midpoint:])
            if early_volume is not None and late_volume is not None and late_volume < early_volume:
                volume_dry_up_bonus_applied = True

        flags = {
            "compression_pass": False,
            "compression_length_pass": compression_length_pass,
            "pullback_depth_pass": pullback_depth_pass,
            "range_contraction_pass": range_contraction_pass,
            "volatility_contraction_pass": volatility_contraction_pass,
            "upper_half_positioning_pass": upper_half_positioning_pass,
        }

        reasons: list[str] = []
        if not compression_length_pass:
            reasons.append("Compression length falls outside configured bounds.")
        if not pullback_depth_pass:
            reasons.append("Pullback depth exceeds the configured maximum relative to the prior impulse.")
        if not range_contraction_pass:
            reasons.append("Base does not show sufficient range contraction.")
        if not volatility_contraction_pass:
            reasons.append("Base does not show sufficient volatility contraction versus the prior impulse.")
        if not upper_half_positioning_pass:
            reasons.append("Latest close is not in the upper half of the base.")

        passed = all(
            (
                compression_length_pass,
                pullback_depth_pass,
                range_contraction_pass,
                volatility_contraction_pass,
                upper_half_positioning_pass,
            )
        )
        if passed:
            reasons.append("Constructive hourly compression detected after a prior impulse.")
            flags["compression_pass"] = True

        metrics = {
            "compression_length_bars": length,
            "compression_depth_pct": compression_depth_pct,
            "range_contraction_pct": range_contraction_pct,
            "volatility_contraction_pct": volatility_contraction_pct,
            "base_position_pct": base_position_pct,
            "prior_impulse_pct": prior_impulse_pct,
            "volume_dry_up_bonus_applied": volume_dry_up_bonus_applied,
            "hourly_bar_count": len(hourly_bars),
            "compression_high": round(base_high, 4),
            "compression_low": round(base_low, 4),
            "compression_start": str(base_bars[0].get("timestamp_utc")),
            "compression_end": str(base_bars[-1].get("timestamp_utc")),
        }
        score = sum(
            1
            for passed_flag in (
                compression_length_pass,
                pullback_depth_pass,
                range_contraction_pass,
                volatility_contraction_pass,
                upper_half_positioning_pass,
            )
            if passed_flag
        )
        candidate_results.append(
            (
                score,
                range_contraction_pct + volatility_contraction_pct + base_position_pct,
                ModuleResult(
                    module_name="compression",
                    outcome=DecisionOutcome.PASS if passed else DecisionOutcome.FAIL,
                    passed=passed,
                    metrics=metrics,
                    reasons=reasons,
                    flags=flags,
                    debug_notes=[
                        "Compression detector evaluated trailing hourly bars against the prior impulse window."
                    ],
                ),
            )
        )

    if not candidate_results:
        return _build_skip_result(
            "Compression detector could not compute a valid base and prior impulse window from the provided hourly bars.",
            len(hourly_bars),
        )

    _, _, best_result = max(candidate_results, key=lambda item: (item[0], item[1]))
    return best_result
