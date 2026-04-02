from src.analysis.thesis_engine import build_thesis
from src.scanner.models import (
    DebugPayload,
    ExplanationPayload,
    MarketSnapshot,
    PriceLevels,
    ScanFlags,
    ScanRecord,
    ScanStatus,
    ScoreBreakdown,
)


def test_thesis_engine_returns_multitimeframe_output_and_diagnostics() -> None:
    record = ScanRecord(
        scan_id="scan-1",
        symbol="QQQ",
        market="US",
        direction="long",
        status=ScanStatus.QUALIFIED,
        timestamp_utc="2026-04-01T13:35:00Z",
        levels=PriceLevels(compression_high=501.5, compression_low=495.2, nearest_overhead_resistance=505.0),
        scores=ScoreBreakdown(total=82.4),
        flags=ScanFlags(daily_trend_pass=True, compression_pass=True, trigger_pass=True, trap_risk_elevated=False),
        explanations=ExplanationPayload(summary="Daily trend aligned and breakout triggered.", reasons=["Trend aligned.", "Breakout triggered."]),
        snapshot=MarketSnapshot(
            symbol="QQQ",
            source_type="structured_live",
            source_confidence=0.95,
            source_used="twelvedata",
            timestamp_utc="2026-04-01T13:35:00Z",
            daily={"bar_count": 10, "latest_bar": {"open": 498.0, "close": 500.0}},
            hourly={"bar_count": 20, "latest_bar": {"close": 500.5}},
            intraday_5m={"bar_count": 40, "latest_bar": {"close": 500.8}},
        ),
    )
    thesis, diagnostics = build_thesis(record)
    assert thesis.short_term_bias == "Active"
    assert thesis.intraday_bias == "Constructive"
    assert thesis.swing_bias == "Bullish"
    assert thesis.short_term_target == "505.00"
    assert thesis.invalidation == "495.20"
    assert thesis.strategy_match == "Breakout Continuation"
    # diagnostics.source is intentionally empty - filled by the caller from SourceManager
    assert diagnostics.source == {}
    assert "daily_trend_pass" in diagnostics.strategy["rules_passed"]
    assert diagnostics.system["warnings"] == []


def test_thesis_confidence_score_mirrors_scores_total() -> None:
    """thesis.confidence_score must stay aligned with scores.total (source of truth)."""
    record = ScanRecord(
        scan_id="scan-2",
        symbol="AAPL",
        market="US",
        direction="long",
        status=ScanStatus.QUALIFIED,
        timestamp_utc="2026-04-01T14:00:00Z",
        scores=ScoreBreakdown(total=73.5),
        flags=ScanFlags(daily_trend_pass=True, compression_pass=True, trigger_pass=True),
        explanations=ExplanationPayload(summary="Aligned.", reasons=["Trend.", "Breakout."]),
        snapshot=MarketSnapshot(symbol="AAPL", source_used="yahoo"),
    )
    thesis, _ = build_thesis(record)
    assert thesis.confidence_score == round(record.scores.total, 2), (
        "thesis.confidence_score must equal round(scores.total, 2) - drift detected"
    )


def test_thesis_explanation_fields_mirror_explanations_payload() -> None:
    """thesis.explanation_summary and reasons must mirror explanations payload."""
    summary = "Daily trend aligned and breakout triggered."
    reasons = ["Trend aligned.", "Breakout triggered."]
    record = ScanRecord(
        scan_id="scan-3",
        symbol="MSFT",
        market="US",
        direction="long",
        status=ScanStatus.QUALIFIED,
        timestamp_utc="2026-04-01T14:00:00Z",
        scores=ScoreBreakdown(total=80.0),
        flags=ScanFlags(daily_trend_pass=True, compression_pass=True, trigger_pass=True),
        explanations=ExplanationPayload(summary=summary, reasons=reasons),
        snapshot=MarketSnapshot(symbol="MSFT", source_used="twelvedata"),
    )
    thesis, _ = build_thesis(record)
    assert thesis.explanation_summary == summary, "thesis.explanation_summary must mirror explanations.summary"
    assert thesis.explanation_reasons == reasons, "thesis.explanation_reasons must mirror explanations.reasons"


def test_thesis_source_used_mirrors_snapshot_source_used() -> None:
    """thesis.source_used must mirror snapshot.source_used."""
    record = ScanRecord(
        scan_id="scan-4",
        symbol="SPY",
        market="US",
        direction="long",
        status=ScanStatus.SKIPPED,
        timestamp_utc="2026-04-01T14:00:00Z",
        scores=ScoreBreakdown(total=0.0),
        flags=ScanFlags(),
        explanations=ExplanationPayload(summary="No setup.", reasons=[]),
        snapshot=MarketSnapshot(symbol="SPY", source_used="fixture"),
    )
    thesis, _ = build_thesis(record)
    assert thesis.source_used == record.snapshot.source_used, (
        "thesis.source_used must mirror snapshot.source_used - drift detected"
    )


def test_thesis_diagnostics_source_is_empty_for_caller_to_fill() -> None:
    """build_thesis must return diagnostics.source == {} so the caller owns it via SourceManager."""
    record = ScanRecord(
        scan_id="scan-5",
        symbol="QQQ",
        market="US",
        direction="long",
        status=ScanStatus.QUALIFIED,
        timestamp_utc="2026-04-01T14:00:00Z",
        scores=ScoreBreakdown(total=78.0),
        flags=ScanFlags(daily_trend_pass=True, compression_pass=True, trigger_pass=True),
        explanations=ExplanationPayload(summary="Aligned.", reasons=["Trend.", "Breakout."]),
        snapshot=MarketSnapshot(
            symbol="QQQ",
            source_type="structured_live",
            source_used="yahoo",
            daily={"bar_count": 10, "latest_bar": {"open": 498.0, "close": 500.0}},
            hourly={"bar_count": 20},
            intraday_5m={"bar_count": 40},
        ),
    )
    _, diagnostics = build_thesis(record)
    assert diagnostics.source == {}, (
        "build_thesis must leave diagnostics.source empty - caller fills it from SourceManager"
    )


def test_daily_bias_returns_unavailable_for_single_bar() -> None:
    """A single daily bar is insufficient for swing bias - must return Unavailable."""
    record = ScanRecord(
        scan_id="scan-6",
        symbol="NVDA",
        market="US",
        direction="long",
        status=ScanStatus.QUALIFIED,
        timestamp_utc="2026-04-01T14:00:00Z",
        scores=ScoreBreakdown(total=75.0),
        flags=ScanFlags(daily_trend_pass=True, compression_pass=True, trigger_pass=True),
        explanations=ExplanationPayload(summary="Aligned.", reasons=["Trend."]),
        snapshot=MarketSnapshot(
            symbol="NVDA",
            source_used="twelvedata",
            # bar_count=1 - single bar is insufficient for swing bias
            daily={"bar_count": 1, "latest_bar": {"open": 498.0, "close": 502.0}},
        ),
    )
    thesis, _ = build_thesis(record)
    assert thesis.swing_bias == "Unavailable", (
        "swing_bias must be Unavailable when daily bar_count < 2 - single bar is not swing evidence"
    )

