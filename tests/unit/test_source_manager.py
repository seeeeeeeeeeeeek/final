from src.analysis.source_manager import SourceManager
from src.scanner.models import MarketDataBundle, MarketDataSlice, SymbolContext
from src.services.webhook_models import TradingViewWebhookPayload


def test_source_manager_builds_structured_live_snapshot_with_coverage_and_warnings() -> None:
    manager = SourceManager()
    bundle = MarketDataBundle(
        daily=MarketDataSlice(timeframe="1D", bars=[{"timestamp_utc": "2026-04-01T20:00:00Z", "open": 100, "high": 101, "low": 99, "close": 101, "volume": 1000}]),
        hourly=MarketDataSlice(timeframe="1H", bars=[{"timestamp_utc": "2026-04-01T20:00:00Z", "open": 100, "high": 101, "low": 99, "close": 101, "volume": 1000}]),
        intraday_5m=MarketDataSlice(timeframe="5m", bars=[]),
        warnings=["5m data lagging."],
    )
    result = manager.from_market_data(SymbolContext(symbol="QQQ"), bundle, provider_name="twelvedata", fallback_chain=["yahoo"])
    assert result.snapshot.source_type == "structured_live"
    assert result.snapshot.source_used == "twelvedata"
    assert result.diagnostics["timeframe_coverage"]["1D"] is True
    assert result.diagnostics["timeframe_coverage"]["5m"] is False
    assert "5m.bars" in result.snapshot.missing_fields
    assert result.snapshot.warnings == ["5m data lagging."]


def test_source_manager_builds_webhook_snapshot_without_inventing_missing_fields() -> None:
    manager = SourceManager()
    payload = TradingViewWebhookPayload.from_dict(
        {
            "symbol": "QQQ",
            "exchange": "NASDAQ",
            "timeframe": "5m",
            "timestamp": "2026-04-01T13:35:00Z",
            "close": 500.25,
            "trend_pass": True,
            "compression_pass": True,
            "breakout_pass": True,
            "trap_risk_elevated": False,
        }
    )
    result = manager.from_webhook(payload)
    assert result.snapshot.source_type == "webhook"
    assert result.snapshot.intraday_5m["latest_bar"]["close"] == 500.25
    assert result.diagnostics["source_selected"] == "tradingview_webhook"
    assert "5m.compression_high" in result.snapshot.missing_fields
