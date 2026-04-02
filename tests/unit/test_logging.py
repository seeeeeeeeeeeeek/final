import json

from src.scanner.models import (
    DecisionOutcome,
    DebugPayload,
    ExplanationPayload,
    ModuleResult,
    ScanFlags,
    ScanRecord,
    ScanStatus,
    ScoreBreakdown,
)
from src.services.logging import SignalLogger


def test_logging_payload_includes_scores_metrics_and_module_summaries(tmp_path) -> None:
    record = ScanRecord(
        scan_id="scan-1",
        symbol="NVDA",
        market="US",
        direction="long",
        status=ScanStatus.REJECTED,
        timestamp_utc="2026-04-01T13:35:00Z",
        metrics={"trend_strength_score": 80.0},
        scores=ScoreBreakdown(total=65.0, trend_alignment=20.0),
        flags=ScanFlags(daily_trend_pass=True, compression_pass=False),
        explanations=ExplanationPayload(summary="Example summary", skip_reason=None, no_trade_reason=None),
        debug=DebugPayload(config_version="v1-defaults"),
        module_results={
            "trend_filter": ModuleResult(
                module_name="trend_filter",
                outcome=DecisionOutcome.PASS,
                passed=True,
                reasons=["Trend passed."],
            ),
            "compression": ModuleResult(
                module_name="compression",
                outcome=DecisionOutcome.FAIL,
                passed=False,
                reasons=["Compression failed."],
            ),
        },
    )
    logger = SignalLogger(log_path=tmp_path / "signals.log")
    payload = logger.build_payload(record)
    assert payload["scores"]["total"] == 65.0
    assert payload["metrics"]["trend_strength_score"] == 80.0
    assert payload["modules"]["trend_filter"]["outcome"] == "pass"
    assert payload["modules"]["compression"]["passed"] is False
    logger.log_signal(record)
    line = (tmp_path / "signals.log").read_text(encoding="utf-8").strip()
    serialized = json.loads(line)
    assert serialized["symbol"] == "NVDA"
    assert "modules" in serialized
