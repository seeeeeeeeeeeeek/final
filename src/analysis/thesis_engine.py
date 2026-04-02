from __future__ import annotations

from typing import Any

from src.scanner.models import DiagnosticsPayload, MarketSnapshot, ScanRecord, ScanStatus, ThesisPayload


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_price(value: Any) -> str:
    number = _safe_float(value)
    if number is None:
        return "Not available yet"
    return f"{number:.2f}"


def _daily_bias(snapshot: MarketSnapshot) -> str:
    daily = snapshot.daily or {}
    # Require at least 2 bars; a single candle open/close is insufficient for swing bias.
    if daily.get("bar_count", 0) < 2:
        return "Unavailable"
    latest = daily.get("latest_bar") or {}
    close = _safe_float(latest.get("close"))
    open_value = _safe_float(latest.get("open"))
    if close is None or open_value is None:
        return "Unavailable"
    if close > open_value:
        return "Bullish"
    if close < open_value:
        return "Bearish"
    return "Neutral"


def _hourly_bias(record: ScanRecord, snapshot: MarketSnapshot) -> str:
    latest = (snapshot.hourly or {}).get("latest_bar") or {}
    close = _safe_float(latest.get("close"))
    low = _safe_float(record.levels.compression_low)
    high = _safe_float(record.levels.compression_high)
    if record.flags.compression_pass:
        return "Constructive"
    if None not in (close, low, high) and high and high > low:
        midpoint = low + ((high - low) / 2.0)
        return "Constructive" if close >= midpoint else "Weak"
    return "Weak" if snapshot.hourly.get("bar_count", 0) else "Unavailable"


def _trigger_state(record: ScanRecord) -> str:
    if record.status == ScanStatus.NO_TRADE:
        return "Triggered but risk elevated"
    if record.flags.trigger_pass and record.status == ScanStatus.QUALIFIED:
        return "Active"
    if record.flags.trigger_pass:
        return "Triggered"
    if record.status == ScanStatus.REJECTED:
        return "Invalid"
    return "Inactive"


def build_thesis(record: ScanRecord) -> tuple[ThesisPayload, DiagnosticsPayload]:
    snapshot = record.snapshot
    confidence = round(float(record.scores.total), 2)

    short_term_bias = _trigger_state(record)
    intraday_bias = _hourly_bias(record, snapshot)
    swing_bias = _daily_bias(snapshot)

    short_term_target = _fmt_price(record.levels.nearest_overhead_resistance or record.levels.compression_high)
    intraday_target = _fmt_price(record.levels.nearest_overhead_resistance)
    swing_target = _fmt_price(record.metrics.get("daily_next_liquidity_zone"))
    invalidation = _fmt_price(record.levels.compression_low)

    strategy_match = None
    runner_up_strategy = None
    strategy_reasons: list[str] = []
    if record.flags.daily_trend_pass and record.flags.compression_pass and record.flags.trigger_pass:
        strategy_match = "Breakout Continuation"
        strategy_reasons.append("Breakout continuation fit best because trend, setup, and trigger modules aligned.")
    elif record.flags.trigger_pass and record.flags.trap_risk_elevated:
        runner_up_strategy = "Breakout Continuation"
        strategy_reasons.append("Breakout continuation aligned technically, but trap risk reduced actionability.")

    reasons = list(record.explanations.reasons)
    if not reasons:
        reasons = ["No deterministic explanation reasons were available from the current record."]

    explanation_summary = record.explanations.summary or "No explanation available yet."
    thesis = ThesisPayload(
        short_term_bias=short_term_bias,
        intraday_bias=intraday_bias,
        swing_bias=swing_bias,
        short_term_target=short_term_target,
        intraday_target=intraday_target,
        swing_target=swing_target,
        invalidation=invalidation,
        confidence_score=confidence,
        strategy_match=strategy_match,
        runner_up_strategy=runner_up_strategy,
        explanation_summary=explanation_summary,
        explanation_reasons=reasons,
        source_used=snapshot.source_used,
    )
    # diagnostics.source is intentionally left empty here.
    # The caller (runner or webhook processor) fills it from SourceManager's snapshot_result.diagnostics,
    # making SourceManager the single source of truth for source diagnostics.
    diagnostics = DiagnosticsPayload(
        source={},
        ocr={
            "fallback_activated": snapshot.source_type == "ocr",
            "capture_region": None,
            "ocr_confidence": None,
            "parsing_confidence": None,
            "allowlist_used": None,
            "extraction_errors": [],
        },
        strategy={
            "preset_evaluated": strategy_match or "No preset matched yet",
            "runner_up_preset": runner_up_strategy,
            "rules_passed": [
                name
                for name, passed in {
                    "daily_trend_pass": record.flags.daily_trend_pass,
                    "compression_pass": record.flags.compression_pass,
                    "trigger_pass": record.flags.trigger_pass,
                }.items()
                if passed
            ],
            "rules_failed": [
                name
                for name, passed in {
                    "daily_trend_pass": record.flags.daily_trend_pass,
                    "compression_pass": record.flags.compression_pass,
                    "trigger_pass": record.flags.trigger_pass,
                    "trap_risk_elevated": not record.flags.trap_risk_elevated,
                }.items()
                if not passed
            ],
            "confidence_factors": strategy_reasons,
        },
        system={
            "processing_time_ms": snapshot.latency_ms,
            "last_successful_refresh": record.timestamp_utc,
            "last_successful_webhook": record.timestamp_utc if snapshot.source_type == "webhook" else None,
            "warnings": record.debug.data_quality_warnings,
            "errors": [],
        },
    )
    return thesis, diagnostics

