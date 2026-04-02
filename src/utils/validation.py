from __future__ import annotations

import json

from src.scanner.models import ScanRecord
from src.utils.timeframes import is_supported_timeframe


def validate_scan_record(record: ScanRecord) -> None:
    if not record.symbol:
        raise ValueError("ScanRecord.symbol is required")
    if not is_supported_timeframe(record.timeframes.trend):
        raise ValueError("Unsupported trend timeframe")
    if not is_supported_timeframe(record.timeframes.setup):
        raise ValueError("Unsupported setup timeframe")
    if not is_supported_timeframe(record.timeframes.trigger):
        raise ValueError("Unsupported trigger timeframe")
    if not record.scan_id:
        raise ValueError("ScanRecord.scan_id is required")
    if not record.market:
        raise ValueError("ScanRecord.market is required")
    if not record.direction:
        raise ValueError("ScanRecord.direction is required")
    if not record.timestamp_utc:
        raise ValueError("ScanRecord.timestamp_utc is required")

    payload = record.to_dict()
    required_top_level = {
        "scan_id",
        "symbol",
        "market",
        "direction",
        "status",
        "timestamp_utc",
        "timeframes",
        "setup_window",
        "levels",
        "metrics",
        "scores",
        "flags",
        "explanations",
        "debug",
        "snapshot",
        "thesis",
        "diagnostics",
    }
    missing_keys = required_top_level.difference(payload)
    if missing_keys:
        raise ValueError(f"ScanRecord serialization missing keys: {sorted(missing_keys)}")

    if payload["status"] not in {"qualified", "skipped", "rejected", "no_trade"}:
        raise ValueError("Unsupported scan status")
    if not isinstance(payload["metrics"], dict):
        raise ValueError("ScanRecord.metrics must serialize as a dict")

    for nested_key, nested_fields in {
        "setup_window": {"compression_start", "compression_end", "trigger_time"},
        "levels": {
            "compression_high",
            "compression_low",
            "trigger_level",
            "breakout_price",
            "nearest_overhead_resistance",
        },
        "scores": {
            "total",
            "trend_alignment",
            "squeeze_quality",
            "breakout_impulse",
            "path_quality",
            "trap_risk_penalty",
        },
        "flags": {
            "daily_trend_pass",
            "compression_pass",
            "trigger_pass",
            "trap_risk_elevated",
            "volume_confirmation_used",
        },
        "explanations": {"summary", "reasons", "skip_reason", "no_trade_reason"},
        "debug": {"config_version", "data_quality_warnings"},
        "snapshot": {
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
        },
        "thesis": {
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
        },
        "diagnostics": {"source", "ocr", "strategy", "system"},
    }.items():
        value = payload.get(nested_key)
        if not isinstance(value, dict):
            raise ValueError(f"ScanRecord.{nested_key} must serialize as a dict")
        missing_nested = nested_fields.difference(value)
        if missing_nested:
            raise ValueError(f"ScanRecord.{nested_key} missing keys: {sorted(missing_nested)}")

    json.dumps(payload, sort_keys=True)
