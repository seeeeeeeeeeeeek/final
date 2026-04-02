from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


def _require_str(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field}' is required and must be a non-empty string.")
    return value.strip()


def _require_bool(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"Field '{field}' is required and must be a boolean.")
    return value


def _require_float(payload: dict[str, Any], field: str) -> float:
    value = payload.get(field)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Field '{field}' is required and must be numeric.") from None


def _optional_float(payload: dict[str, Any], field: str) -> float | None:
    value = payload.get(field)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Field '{field}' must be numeric when provided.") from None


def _validate_timestamp(timestamp: str) -> str:
    candidate = timestamp.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError("Field 'timestamp' must be a valid ISO-8601 timestamp.") from exc
    return timestamp


@dataclass(slots=True)
class TradingViewWebhookPayload:
    symbol: str
    exchange: str
    timeframe: str
    timestamp: str
    close: float
    trend_pass: bool
    compression_pass: bool
    breakout_pass: bool
    trap_risk_elevated: bool
    compression_high: float | None = None
    compression_low: float | None = None
    trigger_level: float | None = None
    breakout_price: float | None = None
    breakout_range_vs_base_avg: float | None = None
    relative_volume: float | None = None
    rejection_wick_pct: float | None = None
    overhead_clearance_pct: float | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TradingViewWebhookPayload":
        if not isinstance(payload, dict):
            raise ValueError("Webhook payload must be a JSON object.")
        timestamp = _validate_timestamp(_require_str(payload, "timestamp"))
        return cls(
            symbol=_require_str(payload, "symbol"),
            exchange=_require_str(payload, "exchange"),
            timeframe=_require_str(payload, "timeframe"),
            timestamp=timestamp,
            close=_require_float(payload, "close"),
            trend_pass=_require_bool(payload, "trend_pass"),
            compression_pass=_require_bool(payload, "compression_pass"),
            breakout_pass=_require_bool(payload, "breakout_pass"),
            trap_risk_elevated=_require_bool(payload, "trap_risk_elevated"),
            compression_high=_optional_float(payload, "compression_high"),
            compression_low=_optional_float(payload, "compression_low"),
            trigger_level=_optional_float(payload, "trigger_level"),
            breakout_price=_optional_float(payload, "breakout_price"),
            breakout_range_vs_base_avg=_optional_float(payload, "breakout_range_vs_base_avg"),
            relative_volume=_optional_float(payload, "relative_volume"),
            rejection_wick_pct=_optional_float(payload, "rejection_wick_pct"),
            overhead_clearance_pct=_optional_float(payload, "overhead_clearance_pct"),
        )
