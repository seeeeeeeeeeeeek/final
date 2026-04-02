from __future__ import annotations

from src.modules.skip_reasons import build_skip_or_no_trade_reason
from src.scanner.models import ExplanationPayload, ModuleResult, ScanRecord, ScanStatus


def _first_reason(module_result: ModuleResult | None) -> str | None:
    if module_result and module_result.reasons:
        return module_result.reasons[0]
    return None


def _append_reason(reasons: list[str], reason: str | None) -> None:
    if reason and reason not in reasons:
        reasons.append(reason)


def _fmt_score(total: float) -> str:
    return f"{total:.2f}".rstrip("0").rstrip(".")


def build_explanations(record: ScanRecord) -> ExplanationPayload:
    """Build deterministic user-facing explanations directly from record/module outputs."""
    trend = record.module_results.get("trend_filter")
    compression = record.module_results.get("compression")
    breakout = record.module_results.get("breakout_trigger")
    trap = record.module_results.get("trap_risk")

    reasons: list[str] = []
    skip_reason: str | None = None
    no_trade_reason: str | None = None

    if record.status == ScanStatus.QUALIFIED:
        trend_strength = record.metrics.get("trend_strength_score")
        compression_length = record.metrics.get("compression_length_bars")
        breakout_expansion = record.metrics.get("breakout_range_vs_base_avg")
        total_score = record.scores.total

        summary_parts = [
            "Daily trend aligned",
            f"hourly base contracted cleanly over {compression_length} bars" if compression_length else "hourly base qualified",
            (
                f"5m breakout triggered with {breakout_expansion}x range expansion and acceptable follow-through"
                if breakout_expansion is not None
                else "5m breakout triggered with acceptable follow-through"
            ),
            "trap risk remained controlled",
        ]
        summary = ", ".join(summary_parts[:-1]) + f". {summary_parts[-1].capitalize()}. Total score: {_fmt_score(total_score)}."

        _append_reason(
            reasons,
            (
                f"Daily trend passed with trend strength score {trend_strength}."
                if trend_strength is not None
                else _first_reason(trend)
            ),
        )
        _append_reason(
            reasons,
            (
                f"Compression qualified with {record.metrics.get('range_contraction_pct')}% range contraction and {record.metrics.get('volatility_contraction_pct')}% volatility contraction."
                if record.metrics.get("range_contraction_pct") is not None and record.metrics.get("volatility_contraction_pct") is not None
                else _first_reason(compression)
            ),
        )
        _append_reason(
            reasons,
            (
                f"Breakout cleared the trigger with {breakout_expansion}x range expansion and relative volume {record.metrics.get('relative_volume')}."
                if breakout_expansion is not None and record.metrics.get("relative_volume") is not None
                else _first_reason(breakout)
            ),
        )
        _append_reason(
            reasons,
            (
                f"Trap-risk checks passed with overhead clearance {record.metrics.get('overhead_clearance_pct')}% and rejection wick {record.metrics.get('rejection_wick_pct')}%."
                if record.metrics.get("rejection_wick_pct") is not None
                else _first_reason(trap)
            ),
        )
        return ExplanationPayload(summary=summary, reasons=reasons[:3], skip_reason=None, no_trade_reason=None)

    if record.status == ScanStatus.SKIPPED:
        skip_reason = build_skip_or_no_trade_reason(record)
        summary = skip_reason
        if record.scores.total > 0:
            summary = f"{summary} Total score: {_fmt_score(record.scores.total)}."
        _append_reason(reasons, _first_reason(trend))
        _append_reason(reasons, _first_reason(compression))
        _append_reason(reasons, _first_reason(breakout))
        return ExplanationPayload(summary=summary, reasons=reasons[:3], skip_reason=skip_reason, no_trade_reason=None)

    if record.status == ScanStatus.REJECTED:
        failed_modules: list[str] = []
        if compression and not compression.passed:
            failed_modules.append("compression")
            _append_reason(reasons, _first_reason(compression))
        if breakout and not breakout.passed:
            failed_modules.append("breakout trigger")
            _append_reason(reasons, _first_reason(breakout))
        modules_text = " and ".join(failed_modules) if failed_modules else "setup conditions"
        summary = f"Setup conditions did not qualify because {modules_text} failed."
        if record.scores.total > 0:
            summary = f"{summary} Total score: {_fmt_score(record.scores.total)}."
        return ExplanationPayload(summary=summary, reasons=reasons[:3], skip_reason=None, no_trade_reason=None)

    if record.status == ScanStatus.NO_TRADE:
        no_trade_reason = build_skip_or_no_trade_reason(record)
        summary = no_trade_reason
        if record.scores.total > 0:
            summary = f"{summary} Total score: {_fmt_score(record.scores.total)}."
        _append_reason(reasons, _first_reason(trap))
        _append_reason(reasons, _first_reason(breakout))
        _append_reason(reasons, _first_reason(compression))
        return ExplanationPayload(summary=summary, reasons=reasons[:3], skip_reason=None, no_trade_reason=no_trade_reason)

    return ExplanationPayload(summary="No explanation available.", reasons=[])
