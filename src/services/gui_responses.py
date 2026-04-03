from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.scanner.models import ScanRecord

if TYPE_CHECKING:
    from src.services.gui_state import GUIState


def _clean_reasons(reasons: list[str]) -> list[str]:
    return [reason for reason in reasons if reason][:4]


def _format_level(value: Any) -> str:
    if value in (None, ""):
        return "Not available yet"
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    return str(value)


def _label_value_rows(entries: list[tuple[str, Any]]) -> list[dict[str, str]]:
    return [{"label": label, "value": _format_level(value)} for label, value in entries]


def _summary_payload(record: ScanRecord, state: "GUIState") -> dict[str, Any]:
    timeframe_summary = state.timeframe_summary(record)
    helper_copy = state.helper_copy()
    reasons = _clean_reasons(record.thesis.explanation_reasons or record.explanations.reasons)
    source_path = state.source_path(record, {})
    return {
        "symbol": record.symbol,
        "setup_status": state.setup_status_label(record),
        "bias": state.bias_label(record),
        "confidence": state.confidence_label(record),
        "best_action": state.best_action_label(record),
        "confidence_explanation": state.confidence_explanation(record),
        "short_term_target": record.thesis.short_term_target or "Not available yet",
        "invalidation": record.thesis.invalidation or "Not available yet",
        "why_it_matters": record.thesis.explanation_summary or record.explanations.summary or "No explanation available yet.",
        "reason_bullets": reasons,
        "one_sentence_summary": (record.thesis.explanation_summary or record.explanations.summary or "No explanation available yet."),
        "trust_signals": state.trust_signals(record),
        "helper_copy": helper_copy,
        "source_class_label": source_path["source_class_label"],
        "freshness_state": source_path["freshness_state"],
        "freshness_seconds": source_path["freshness_seconds"],
        "timeframe_interpretation": {
            "daily_context": timeframe_summary["daily_context"],
            "hourly_setup": timeframe_summary["hourly_setup"],
            "trigger_5m": timeframe_summary["trigger_5m"],
            "execution_1m": timeframe_summary["execution_1m"],
        },
        "timeframe_story": state.timeframe_story(record),
    }


def build_detail_payload(record: ScanRecord, raw_payload: dict[str, Any], state: "GUIState") -> dict[str, Any]:
    payload = record.to_dict()
    simple_summary = _summary_payload(record, state)
    source_path = state.source_path(record, raw_payload)
    detailed_analysis = {
        "strategy_match": record.thesis.strategy_match or "Not matched yet",
        "passed_summary": _clean_reasons(record.explanations.reasons),
        "levels_summary": _label_value_rows(
            [
                ("Breakout price", record.levels.breakout_price),
                ("Compression high", record.levels.compression_high),
                ("Compression low", record.levels.compression_low),
                ("Trigger level", record.levels.trigger_level),
                ("Overhead resistance", record.levels.nearest_overhead_resistance),
            ]
        ),
        "timeframe_summary": simple_summary["timeframe_story"],
        "score_summary": _label_value_rows(
            [
                ("Total confidence score", record.scores.total),
                ("Trend alignment", record.scores.trend_alignment),
                ("Setup quality", record.scores.squeeze_quality),
                ("Breakout impulse", record.scores.breakout_impulse),
                ("Path quality", record.scores.path_quality),
                ("Trap-risk penalty", record.scores.trap_risk_penalty),
            ]
        ),
        "source_path": {
            "requested": source_path["requested"],
            "used": source_path["used"],
            "mode_kind": source_path["mode_kind"],
            "source_class": source_path["source_class_label"],
            "fallback_chain": source_path["fallback_chain"] or ["None"],
            "coverage": source_path["coverage_text"],
            "missing_context": source_path["missing_context_text"],
            "freshness": (
                f"{int(source_path['freshness_seconds'])} seconds old"
                if source_path["freshness_seconds"] is not None
                else "Not available"
            ),
        },
    }
    return {
        "ok": True,
        "record": payload,
        "raw_payload": raw_payload,
        "display": {
            **simple_summary,
            "source_used": record.thesis.source_used or record.snapshot.source_used or "unknown",
            "source_path": source_path,
        },
        "sections": {
            "action_card": simple_summary,
            "detailed_analysis": detailed_analysis,
            "advanced": {
                "flags": payload.get("flags", {}),
                "metrics": payload.get("metrics", {}),
                "diagnostics": payload.get("diagnostics", {}),
                "snapshot": payload.get("snapshot", {}),
                "raw_json": payload,
            },
        },
    }


def build_replay_result_payload(record: ScanRecord, state: "GUIState") -> dict[str, Any]:
    return {
        "simple_summary": {
            **_summary_payload(record, state),
            "source_path": state.source_path(record, {}),
        },
        "raw_result": record.to_dict(),
    }


def sample_payloads() -> dict[str, dict[str, Any]]:
    return {
        "qualified": {
            "symbol": "DEMO",
            "exchange": "NASDAQ",
            "timeframe": "5m",
            "timestamp": "2026-04-01T13:35:00Z",
            "close": 123.4,
            "trend_pass": True,
            "compression_pass": True,
            "breakout_pass": True,
            "trap_risk_elevated": False,
            "compression_high": 122.8,
            "compression_low": 118.6,
            "trigger_level": 122.85,
            "breakout_price": 123.4,
            "breakout_range_vs_base_avg": 2.2,
            "relative_volume": 1.8,
            "rejection_wick_pct": 9.0,
            "overhead_clearance_pct": 4.0,
        },
        "no_trade": {
            "symbol": "DEMO2",
            "exchange": "NASDAQ",
            "timeframe": "5m",
            "timestamp": "2026-04-01T13:40:00Z",
            "close": 201.4,
            "trend_pass": True,
            "compression_pass": True,
            "breakout_pass": True,
            "trap_risk_elevated": True,
            "compression_high": 200.8,
            "compression_low": 196.2,
            "trigger_level": 200.9,
            "breakout_price": 201.4,
            "breakout_range_vs_base_avg": 1.7,
            "relative_volume": 1.1,
            "rejection_wick_pct": 28.0,
            "overhead_clearance_pct": 0.9,
        },
        "skipped": {
            "symbol": "DEMO3",
            "exchange": "NASDAQ",
            "timeframe": "5m",
            "timestamp": "2026-04-01T13:45:00Z",
            "close": 420.0,
            "trend_pass": False,
            "compression_pass": True,
            "breakout_pass": True,
            "trap_risk_elevated": False,
        },
    }
