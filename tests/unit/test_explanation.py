from src.modules.explanation import build_explanations
from src.scanner.models import DecisionOutcome, ModuleResult, ScanStatus, build_empty_scan_record


def test_qualified_record_produces_grounded_summary_and_reasons() -> None:
    record = build_empty_scan_record("NVDA", scan_id="scan-1", status=ScanStatus.QUALIFIED)
    record.metrics.update(
        {
            "trend_strength_score": 100.0,
            "compression_length_bars": 6,
            "range_contraction_pct": 42.0,
            "volatility_contraction_pct": 30.0,
            "breakout_range_vs_base_avg": 2.2,
            "relative_volume": 1.8,
            "overhead_clearance_pct": 4.1,
            "rejection_wick_pct": 9.0,
        }
    )
    record.scores.total = 81.4
    record.module_results = {
        "trend_filter": ModuleResult("trend_filter", DecisionOutcome.PASS, True, reasons=["Daily trend passed."]),
        "compression": ModuleResult("compression", DecisionOutcome.PASS, True, reasons=["Compression passed."]),
        "breakout_trigger": ModuleResult("breakout_trigger", DecisionOutcome.PASS, True, reasons=["Breakout passed."]),
        "trap_risk": ModuleResult("trap_risk", DecisionOutcome.PASS, True, reasons=["Trap risk controlled."]),
    }
    payload = build_explanations(record)
    assert "Daily trend aligned" in payload.summary
    assert "Total score: 81.4." in payload.summary
    assert len(payload.reasons) == 3


def test_skipped_record_uses_primary_skip_reason() -> None:
    record = build_empty_scan_record("AAPL", scan_id="scan-2", status=ScanStatus.SKIPPED)
    record.module_results = {
        "trend_filter": ModuleResult(
            "trend_filter",
            DecisionOutcome.FAIL,
            False,
            reasons=["Latest close is below the configured slow moving average."],
        )
    }
    payload = build_explanations(record)
    assert payload.skip_reason == "Skipped because the daily trend filter failed: Latest close is below the configured slow moving average."
    assert payload.summary == payload.skip_reason


def test_rejected_record_uses_failed_setup_module_reason() -> None:
    record = build_empty_scan_record("MSFT", scan_id="scan-3", status=ScanStatus.REJECTED)
    record.scores.total = 22.5
    record.module_results = {
        "compression": ModuleResult(
            "compression",
            DecisionOutcome.FAIL,
            False,
            reasons=["Base does not show sufficient range contraction."],
        ),
        "breakout_trigger": ModuleResult(
            "breakout_trigger",
            DecisionOutcome.FAIL,
            False,
            reasons=["Breakout did not close clearly above the compression high."],
        ),
    }
    payload = build_explanations(record)
    assert "compression and breakout trigger failed" in payload.summary
    assert "Total score: 22.5." in payload.summary
    assert payload.reasons[0] == "Base does not show sufficient range contraction."


def test_no_trade_record_uses_trap_risk_reason() -> None:
    record = build_empty_scan_record("AMD", scan_id="scan-4", status=ScanStatus.NO_TRADE)
    record.scores.total = 61.2
    record.module_results = {
        "trap_risk": ModuleResult(
            "trap_risk",
            DecisionOutcome.NO_TRADE,
            False,
            reasons=["Breakout is too close to nearby hourly overhead resistance."],
        ),
        "breakout_trigger": ModuleResult(
            "breakout_trigger",
            DecisionOutcome.PASS,
            True,
            reasons=["Breakout cleared the compression high with required expansion and acceptable 5m follow-through."],
        ),
    }
    payload = build_explanations(record)
    assert payload.no_trade_reason == "No-trade because trap risk was elevated: Breakout is too close to nearby hourly overhead resistance."
    assert "Total score: 61.2." in payload.summary


def test_explanations_are_deterministic_for_identical_records() -> None:
    record = build_empty_scan_record("META", scan_id="scan-5", status=ScanStatus.SKIPPED)
    record.module_results = {
        "trend_filter": ModuleResult(
            "trend_filter",
            DecisionOutcome.FAIL,
            False,
            reasons=["Latest close is below the configured fast moving average."],
        )
    }
    first = build_explanations(record)
    second = build_explanations(record)
    assert first.summary == second.summary
    assert first.reasons == second.reasons
    assert first.skip_reason == second.skip_reason
    assert first.no_trade_reason == second.no_trade_reason
