from __future__ import annotations

from src.scanner.models import ModuleResult, ScanRecord, ScanStatus


def _prefixed_reason(prefix: str, reason: str | None, fallback: str) -> str:
    if not reason:
        return fallback
    return f"{prefix}{reason}"


def _first_reason(module_result: ModuleResult | None) -> str | None:
    if module_result and module_result.reasons:
        return module_result.reasons[0]
    return None


def build_skip_or_no_trade_reason(record: ScanRecord) -> str:
    """Select the primary user-facing reason for skipped, rejected, and no-trade records."""
    trend = record.module_results.get("trend_filter")
    compression = record.module_results.get("compression")
    breakout = record.module_results.get("breakout_trigger")
    trap = record.module_results.get("trap_risk")

    if record.status == ScanStatus.SKIPPED:
        if trend and not trend.passed:
            return _prefixed_reason(
                "Skipped because the daily trend filter failed: ",
                _first_reason(trend),
                "Skipped because the daily trend filter did not qualify the symbol.",
            )
        if compression and compression.outcome.name.lower() == "skip":
            return _prefixed_reason(
                "Skipped because compression could not be evaluated: ",
                _first_reason(compression),
                "Skipped because compression could not be evaluated.",
            )
        if breakout and breakout.outcome.name.lower() == "skip":
            return _prefixed_reason(
                "Skipped because breakout trigger inputs were incomplete: ",
                _first_reason(breakout),
                "Skipped because breakout trigger inputs were incomplete.",
            )
        return "Skipped because required setup inputs were not available."

    if record.status == ScanStatus.NO_TRADE:
        return _prefixed_reason(
            "No-trade because trap risk was elevated: ",
            _first_reason(trap),
            "No-trade because trap risk was elevated.",
        )

    if record.status == ScanStatus.REJECTED:
        if compression and not compression.passed:
            return _prefixed_reason(
                "Rejected because compression did not qualify: ",
                _first_reason(compression),
                "Rejected because compression did not qualify.",
            )
        if breakout and not breakout.passed:
            return _prefixed_reason(
                "Rejected because breakout trigger conditions were not met: ",
                _first_reason(breakout),
                "Rejected because breakout trigger conditions were not met.",
            )
        return "Rejected because one or more setup modules did not qualify."

    return ""
