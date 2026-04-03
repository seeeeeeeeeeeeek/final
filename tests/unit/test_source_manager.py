from src.analysis.source_manager import SourceManager
from src.scanner.models import MarketDataBundle, MarketDataSlice, SymbolContext
from src.services.browser_source import BrowserExtractionResult
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


def test_source_manager_builds_browser_snapshot_without_faking_timeframes() -> None:
    manager = SourceManager()
    result = manager.from_browser(
        BrowserExtractionResult(
            ok=True,
            source_name="yahoo_quote_page",
            adapter_kind="yahoo",
            page_url_attempted="https://finance.yahoo.com/quote/SPY",
            symbol_requested="SPY",
            symbol_detected="SPY",
            timestamp_utc="2026-04-02T12:00:00Z",
            latest_visible_price=523.11,
            visible_timeframe=None,
            fields_extracted=["symbol", "latest_visible_price"],
            missing_fields=["1D.bars", "1H.bars", "5m.bars"],
            warnings=["Browser extraction found visible quote data only."],
            errors=[],
            latency_ms=1200.0,
            extraction_status="partial",
            extraction_completeness="partial",
            trust_classification="browser_partial",
            screenshot_paths={"page": "out/browser_artifacts/yahoo/SPY_page.png"},
        )
    )
    assert result.snapshot.source_type == "browser"
    assert result.snapshot.source_used == "yahoo_quote_page"
    assert result.snapshot.intraday_5m["latest_bar"]["close"] == 523.11
    assert result.diagnostics["source_class"] == "browser_partial"
    assert result.diagnostics["adapter_kind"] == "yahoo"
    assert result.diagnostics["browser_source_name"] == "yahoo_quote_page"
    assert result.diagnostics["timeframe_coverage"]["1D"] is False
    assert "1D.bars" in result.snapshot.missing_fields
