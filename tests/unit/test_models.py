import json

from src.analysis.thesis_engine import build_thesis
from src.scanner.models import (
    DebugPayload,
    ExplanationPayload,
    MarketSnapshot,
    ScanFlags,
    ScanRecord,
    ScanStatus,
    ScoreBreakdown,
    SetupWindow,
    PriceLevels,
    build_empty_scan_record,
)
from src.utils.validation import validate_scan_record


def test_build_empty_scan_record_uses_stable_defaults() -> None:
    record = build_empty_scan_record("NVDA", scan_id="scan-1", status=ScanStatus.SKIPPED)
    assert record.symbol == "NVDA"
    assert record.market == "US"
    assert record.direction == "long"
    assert record.status == ScanStatus.SKIPPED
    assert record.to_dict()["symbol"] == "NVDA"


def test_scan_record_to_dict_is_stable_and_json_safe() -> None:
    record = ScanRecord(
        scan_id="scan-1",
        symbol="NVDA",
        market="US",
        direction="long",
        status=ScanStatus.QUALIFIED,
        timestamp_utc="2026-04-01T13:35:00Z",
        setup_window=SetupWindow(
            compression_start="2026-04-01T13:00:00Z",
            compression_end="2026-04-01T18:00:00Z",
            trigger_time="2026-04-01T18:30:00Z",
        ),
        levels=PriceLevels(
            compression_high=110.5,
            compression_low=108.0,
            trigger_level=110.6105,
            breakout_price=112.0,
            nearest_overhead_resistance=None,
        ),
        metrics={"trend_strength_score": 100.0},
        scores=ScoreBreakdown(total=81.4, trend_alignment=20.0, squeeze_quality=21.0, breakout_impulse=23.0, path_quality=17.4, trap_risk_penalty=0.0),
        flags=ScanFlags(daily_trend_pass=True, compression_pass=True, trigger_pass=True, trap_risk_elevated=False, volume_confirmation_used=True),
        explanations=ExplanationPayload(summary="Example summary", reasons=["Example reason."]),
        debug=DebugPayload(config_version="v1-defaults", data_quality_warnings=[]),
    )
    payload = record.to_dict()
    validate_scan_record(record)
    assert payload["status"] == "qualified"
    assert payload["setup_window"]["trigger_time"] == "2026-04-01T18:30:00Z"
    assert payload["levels"]["breakout_price"] == 112.0
    assert set(payload["snapshot"]) == {
        "symbol",
        "source_type",
        "source_confidence",
        "source_used",
        "timestamp_utc",
        "daily",
        "hourly",
        "intraday_5m",
        "intraday_1m",
        "freshness_seconds",
        "latency_ms",
        "fallback_chain",
        "missing_fields",
        "warnings",
    }
    assert set(payload["thesis"]) == {
        "short_term_bias",
        "intraday_bias",
        "swing_bias",
        "short_term_target",
        "intraday_target",
        "swing_target",
        "invalidation",
        "confidence_score",
        "strategy_match",
        "runner_up_strategy",
        "explanation_summary",
        "explanation_reasons",
        "source_used",
    }
    assert set(payload["diagnostics"]) == {"source", "ocr", "strategy", "system"}
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload


def test_scan_record_product_fields_stay_aligned_after_build_thesis() -> None:
    """After build_thesis, thesis fields must mirror their source fields in ScanRecord.

    This test guards against dual-output drift: scores.total drives thesis.confidence_score,
    explanations drives thesis explanation fields, and snapshot drives thesis.source_used.
    """
    summary = "Trend aligned and breakout confirmed."
    reasons = ["Daily trend pass.", "Compression pass.", "Breakout triggered."]
    record = ScanRecord(
        scan_id="alignment-test-1",
        symbol="NVDA",
        market="US",
        direction="long",
        status=ScanStatus.QUALIFIED,
        timestamp_utc="2026-04-01T14:00:00Z",
        scores=ScoreBreakdown(total=84.2),
        flags=ScanFlags(daily_trend_pass=True, compression_pass=True, trigger_pass=True),
        explanations=ExplanationPayload(summary=summary, reasons=reasons),
        snapshot=MarketSnapshot(
            symbol="NVDA",
            source_type="structured_live",
            source_used="twelvedata",
            daily={"bar_count": 10, "latest_bar": {"open": 880.0, "close": 900.0}},
            hourly={"bar_count": 20},
            intraday_5m={"bar_count": 40},
        ),
    )
    thesis, _ = build_thesis(record)
    # Confidence score is derived from scores.total
    assert thesis.confidence_score == round(record.scores.total, 2)
    # Explanation fields mirror the explanations payload
    assert thesis.explanation_summary == record.explanations.summary
    assert thesis.explanation_reasons == record.explanations.reasons
    # Source used mirrors the snapshot
    assert thesis.source_used == record.snapshot.source_used
