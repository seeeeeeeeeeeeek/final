from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from src.scanner.models import MarketDataBundle, MarketSnapshot, SymbolContext
from src.services.webhook_models import TradingViewWebhookPayload


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _freshness_seconds(timestamp_utc: str | None) -> float | None:
    parsed = _parse_timestamp(timestamp_utc)
    if parsed is None:
        return None
    return round((_now_utc() - parsed).total_seconds(), 2)


def _slice_payload(bars: list[dict[str, Any]], timeframe: str) -> dict[str, Any]:
    latest = bars[-1] if bars else None
    return {
        "timeframe": timeframe,
        "bar_count": len(bars),
        "latest_bar": latest,
        "indicators": {},
        "visible_overlays": [],
    }


@dataclass(slots=True)
class SnapshotResult:
    snapshot: MarketSnapshot
    diagnostics: dict[str, Any]


@dataclass(slots=True)
class ProviderSelectionResult:
    selected_name: str
    bundle: MarketDataBundle | None
    fallback_chain: list[str]
    warnings_by_provider: dict[str, list[str]]
    failure_reason: str | None = None


class SourceManager:
    """Resolve source priority and normalize source-specific inputs into a canonical snapshot."""

    def from_market_data(
        self,
        symbol_context: SymbolContext,
        bundle: MarketDataBundle,
        *,
        provider_name: str,
        fallback_chain: list[str] | None = None,
        latency_ms: float | None = None,
    ) -> SnapshotResult:
        missing_fields: list[str] = []
        coverage = {
            "1D": bool(bundle.daily.bars),
            "1H": bool(bundle.hourly.bars),
            "5m": bool(bundle.intraday_5m.bars),
            "1m": False,
        }
        for timeframe, available in coverage.items():
            if not available and timeframe != "1m":
                missing_fields.append(f"{timeframe}.bars")

        last_timestamp = None
        for bars in (bundle.intraday_5m.bars, bundle.hourly.bars, bundle.daily.bars):
            if bars:
                last_timestamp = bars[-1].get("timestamp_utc")
                break

        snapshot = MarketSnapshot(
            symbol=symbol_context.symbol,
            source_type="structured_live",
            source_confidence=0.95 if all(coverage[key] for key in ("1D", "1H", "5m")) else 0.7,
            source_used=provider_name,
            timestamp_utc=last_timestamp,
            daily=_slice_payload(bundle.daily.bars, "1D"),
            hourly=_slice_payload(bundle.hourly.bars, "1H"),
            intraday_5m=_slice_payload(bundle.intraday_5m.bars, "5m"),
            intraday_1m={"timeframe": "1m", "bar_count": 0, "latest_bar": None, "indicators": {}, "visible_overlays": []},
            freshness_seconds=_freshness_seconds(last_timestamp),
            latency_ms=latency_ms,
            fallback_chain=list(fallback_chain or []),
            missing_fields=missing_fields,
            warnings=list(bundle.warnings),
        )
        diagnostics = {
            "source_selected": provider_name,
            "source_type": "structured_live",
            "fallback_chain": list(fallback_chain or []),
            "symbol_detected": symbol_context.symbol,
            "timeframe_coverage": coverage,
            "freshness_seconds": snapshot.freshness_seconds,
            "missing_fields": missing_fields,
            "latency_ms": latency_ms,
            "warnings": list(bundle.warnings),
        }
        return SnapshotResult(snapshot=snapshot, diagnostics=diagnostics)

    def from_webhook(self, payload: TradingViewWebhookPayload) -> SnapshotResult:
        missing_fields: list[str] = []
        if payload.compression_high is None:
            missing_fields.append("5m.compression_high")
        if payload.compression_low is None:
            missing_fields.append("5m.compression_low")

        bar = {
            "timestamp_utc": payload.timestamp,
            "open": None,
            "high": None,
            "low": None,
            "close": payload.close,
            "volume": None,
        }
        snapshot = MarketSnapshot(
            symbol=payload.symbol,
            source_type="webhook",
            source_confidence=0.8,
            source_used="tradingview_webhook",
            timestamp_utc=payload.timestamp,
            daily={"timeframe": "1D", "bar_count": 0, "latest_bar": None, "indicators": {}, "visible_overlays": []},
            hourly={"timeframe": "1H", "bar_count": 0, "latest_bar": None, "indicators": {}, "visible_overlays": []},
            intraday_5m={
                "timeframe": payload.timeframe,
                "bar_count": 1,
                "latest_bar": bar,
                "indicators": {
                    "relative_volume": payload.relative_volume,
                    "rejection_wick_pct": payload.rejection_wick_pct,
                    "overhead_clearance_pct": payload.overhead_clearance_pct,
                },
                "visible_overlays": [],
            },
            intraday_1m={"timeframe": "1m", "bar_count": 0, "latest_bar": None, "indicators": {}, "visible_overlays": []},
            freshness_seconds=_freshness_seconds(payload.timestamp),
            latency_ms=None,
            fallback_chain=[],
            missing_fields=missing_fields,
            warnings=[],
        )
        diagnostics = {
            "source_selected": "tradingview_webhook",
            "source_type": "webhook",
            "fallback_chain": [],
            "symbol_detected": payload.symbol,
            "timeframe_coverage": {"1D": False, "1H": False, "5m": True, "1m": False},
            "freshness_seconds": snapshot.freshness_seconds,
            "missing_fields": missing_fields,
            "latency_ms": None,
            "warnings": [],
        }
        return SnapshotResult(snapshot=snapshot, diagnostics=diagnostics)

    def acquire_from_provider(
        self,
        symbol_context: SymbolContext,
        provider: Any,
        *,
        provider_name: str,
        fallback_chain: list[str] | None = None,
    ) -> tuple[MarketDataBundle, SnapshotResult]:
        start = perf_counter()
        bundle = provider.get_symbol_data(symbol_context)
        elapsed_ms = round((perf_counter() - start) * 1000.0, 2)
        snapshot_result = self.from_market_data(
            symbol_context,
            bundle,
            provider_name=provider_name,
            fallback_chain=fallback_chain,
            latency_ms=elapsed_ms,
        )
        return bundle, snapshot_result

    def select_provider(
        self,
        symbol_context: SymbolContext,
        providers: list[tuple[str, Any]],
    ) -> ProviderSelectionResult:
        fallback_chain: list[str] = []
        warnings_by_provider: dict[str, list[str]] = {}
        for provider_name, provider in providers:
            bundle = provider.get_symbol_data(symbol_context)
            warnings_by_provider[provider_name] = list(bundle.warnings)
            if bundle.daily.bars and bundle.hourly.bars and bundle.intraday_5m.bars:
                return ProviderSelectionResult(
                    selected_name=provider_name,
                    bundle=bundle,
                    fallback_chain=fallback_chain,
                    warnings_by_provider=warnings_by_provider,
                )
            fallback_chain.append(provider_name)

        return ProviderSelectionResult(
            selected_name="auto_failed",
            bundle=None,
            fallback_chain=fallback_chain,
            warnings_by_provider=warnings_by_provider,
            failure_reason="No real provider returned complete daily, hourly, and 5m data.",
        )
