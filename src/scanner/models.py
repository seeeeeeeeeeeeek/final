from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class ScanStatus(StrEnum):
    QUALIFIED = "qualified"
    SKIPPED = "skipped"
    REJECTED = "rejected"
    NO_TRADE = "no_trade"


class DecisionOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    NO_TRADE = "no_trade"


@dataclass(slots=True)
class TimeframeConfig:
    trend: str = "1D"
    setup: str = "1H"
    trigger: str = "5m"


@dataclass(slots=True)
class SetupWindow:
    compression_start: str | None = None
    compression_end: str | None = None
    trigger_time: str | None = None


@dataclass(slots=True)
class PriceLevels:
    compression_high: float | None = None
    compression_low: float | None = None
    trigger_level: float | None = None
    breakout_price: float | None = None
    nearest_overhead_resistance: float | None = None


@dataclass(slots=True)
class ScoreBreakdown:
    total: float = 0.0
    trend_alignment: float = 0.0
    squeeze_quality: float = 0.0
    breakout_impulse: float = 0.0
    path_quality: float = 0.0
    trap_risk_penalty: float = 0.0


@dataclass(slots=True)
class ScanFlags:
    daily_trend_pass: bool = False
    compression_pass: bool = False
    trigger_pass: bool = False
    trap_risk_elevated: bool = False
    volume_confirmation_used: bool = False


@dataclass(slots=True)
class ExplanationPayload:
    summary: str = ""
    reasons: list[str] = field(default_factory=list)
    skip_reason: str | None = None
    no_trade_reason: str | None = None


@dataclass(slots=True)
class DebugPayload:
    config_version: str = "v1-defaults"
    data_quality_warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MarketSnapshot:
    symbol: str = ""
    source_type: str = "unknown"
    source_confidence: float = 0.0
    source_used: str | None = None
    timestamp_utc: str | None = None
    daily: dict[str, Any] = field(default_factory=dict)
    hourly: dict[str, Any] = field(default_factory=dict)
    intraday_5m: dict[str, Any] = field(default_factory=dict)
    intraday_1m: dict[str, Any] = field(default_factory=dict)
    freshness_seconds: float | None = None
    latency_ms: float | None = None
    fallback_chain: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ThesisPayload:
    short_term_bias: str | None = None
    intraday_bias: str | None = None
    swing_bias: str | None = None
    short_term_target: str | None = None
    intraday_target: str | None = None
    swing_target: str | None = None
    invalidation: str | None = None
    confidence_score: float = 0.0
    strategy_match: str | None = None
    runner_up_strategy: str | None = None
    explanation_summary: str = ""
    explanation_reasons: list[str] = field(default_factory=list)
    source_used: str | None = None


@dataclass(slots=True)
class DiagnosticsPayload:
    source: dict[str, Any] = field(default_factory=dict)
    ocr: dict[str, Any] = field(default_factory=dict)
    strategy: dict[str, Any] = field(default_factory=dict)
    system: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ModuleResult:
    module_name: str
    outcome: DecisionOutcome
    passed: bool
    metrics: dict[str, float | int | bool | str | None] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    flags: dict[str, bool] = field(default_factory=dict)
    debug_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SymbolContext:
    symbol: str
    market: str = "US"
    direction: str = "long"
    as_of_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MarketDataSlice:
    timeframe: str
    bars: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class MarketDataBundle:
    daily: MarketDataSlice = field(default_factory=lambda: MarketDataSlice(timeframe="1D"))
    hourly: MarketDataSlice = field(default_factory=lambda: MarketDataSlice(timeframe="1H"))
    intraday_5m: MarketDataSlice = field(default_factory=lambda: MarketDataSlice(timeframe="5m"))
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScanRecord:
    scan_id: str
    symbol: str
    market: str
    direction: str
    status: ScanStatus
    timestamp_utc: str
    timeframes: TimeframeConfig = field(default_factory=TimeframeConfig)
    setup_window: SetupWindow = field(default_factory=SetupWindow)
    levels: PriceLevels = field(default_factory=PriceLevels)
    metrics: dict[str, float | int | bool | str | None] = field(default_factory=dict)
    scores: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    flags: ScanFlags = field(default_factory=ScanFlags)
    explanations: ExplanationPayload = field(default_factory=ExplanationPayload)
    debug: DebugPayload = field(default_factory=DebugPayload)
    snapshot: MarketSnapshot = field(default_factory=MarketSnapshot)
    thesis: ThesisPayload = field(default_factory=ThesisPayload)
    diagnostics: DiagnosticsPayload = field(default_factory=DiagnosticsPayload)
    module_results: dict[str, ModuleResult] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = _json_safe(asdict(self))
        payload.pop("module_results", None)
        return payload


@dataclass(slots=True)
class ScanConfig:
    defaults: dict[str, Any]
    scoring: dict[str, Any]
    universe: dict[str, Any]


def build_empty_scan_record(
    symbol: str,
    *,
    scan_id: str,
    config_version: str = "v1-defaults",
    status: ScanStatus = ScanStatus.SKIPPED,
) -> ScanRecord:
    return ScanRecord(
        scan_id=scan_id,
        symbol=symbol,
        market="US",
        direction="long",
        status=status,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        debug=DebugPayload(config_version=config_version),
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
