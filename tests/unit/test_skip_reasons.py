from src.modules.skip_reasons import build_skip_or_no_trade_reason
from src.scanner.models import DecisionOutcome, ModuleResult, ScanStatus, build_empty_scan_record


def test_skip_reason_prefers_trend_module_reason() -> None:
    record = build_empty_scan_record("NVDA", scan_id="scan-1", status=ScanStatus.SKIPPED)
    record.module_results = {
        "trend_filter": ModuleResult(
            module_name="trend_filter",
            outcome=DecisionOutcome.FAIL,
            passed=False,
            reasons=["Latest close is below the configured fast moving average."],
        )
    }
    assert (
        build_skip_or_no_trade_reason(record)
        == "Skipped because the daily trend filter failed: Latest close is below the configured fast moving average."
    )


def test_rejected_reason_prefers_compression_before_breakout() -> None:
    record = build_empty_scan_record("AAPL", scan_id="scan-2", status=ScanStatus.REJECTED)
    record.module_results = {
        "compression": ModuleResult(
            module_name="compression",
            outcome=DecisionOutcome.FAIL,
            passed=False,
            reasons=["Base does not show sufficient range contraction."],
        ),
        "breakout_trigger": ModuleResult(
            module_name="breakout_trigger",
            outcome=DecisionOutcome.FAIL,
            passed=False,
            reasons=["Breakout bar did not expand enough relative to the compression base average range."],
        ),
    }
    assert (
        build_skip_or_no_trade_reason(record)
        == "Rejected because compression did not qualify: Base does not show sufficient range contraction."
    )


def test_no_trade_reason_prefers_trap_risk_reason() -> None:
    record = build_empty_scan_record("MSFT", scan_id="scan-3", status=ScanStatus.NO_TRADE)
    record.module_results = {
        "trap_risk": ModuleResult(
            module_name="trap_risk",
            outcome=DecisionOutcome.NO_TRADE,
            passed=False,
            reasons=["Breakout is too close to nearby hourly overhead resistance."],
        )
    }
    assert (
        build_skip_or_no_trade_reason(record)
        == "No-trade because trap risk was elevated: Breakout is too close to nearby hourly overhead resistance."
    )
