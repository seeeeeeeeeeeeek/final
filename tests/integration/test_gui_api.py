import json
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from src.scanner.models import MarketDataBundle, MarketDataSlice
from src.services.browser_source import BrowserExtractionResult, BrowserSourceManager
from src.services.config_loader import load_optional_yaml
from src.services.gui_api import create_gui_server
from src.services.market_data import TwelveDataMarketDataProvider, YahooFinanceMarketDataProvider


def _request_json(url: str, *, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _valid_payload(symbol: str = "NVDA", *, timestamp: str | None = None) -> dict:
    return {
        "symbol": symbol,
        "exchange": "NASDAQ",
        "timeframe": "5m",
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "close": 944.2,
        "trend_pass": True,
        "compression_pass": True,
        "breakout_pass": True,
        "trap_risk_elevated": False,
        "compression_high": 942.1,
        "compression_low": 910.4,
        "trigger_level": 942.15,
        "breakout_price": 944.2,
        "breakout_range_vs_base_avg": 2.2,
        "relative_volume": 1.8,
        "rejection_wick_pct": 9.0,
        "overhead_clearance_pct": 4.0,
    }


def _start_server(tmp_path):
    server = create_gui_server(
        host="127.0.0.1",
        port=0,
        config_dir="config",
        log_path=tmp_path / "gui.log",
        override_path=tmp_path / "gui_user.yaml",
        demo_override_path="config/demo.yaml",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _complete_bundle(close: float = 101.0) -> MarketDataBundle:
    bar = {"timestamp_utc": "2026-04-01T13:35:00Z", "open": close - 1, "high": close + 1, "low": close - 2, "close": close, "volume": 1000}
    return MarketDataBundle(
        daily=MarketDataSlice(timeframe="1D", bars=[bar]),
        hourly=MarketDataSlice(timeframe="1H", bars=[bar]),
        intraday_5m=MarketDataSlice(timeframe="5m", bars=[bar]),
        warnings=[],
    )


def _empty_bundle(warning: str) -> MarketDataBundle:
    return MarketDataBundle(
        daily=MarketDataSlice(timeframe="1D", bars=[]),
        hourly=MarketDataSlice(timeframe="1H", bars=[]),
        intraday_5m=MarketDataSlice(timeframe="5m", bars=[]),
        warnings=[warning],
    )


def test_gui_api_health_endpoint_reports_running_state(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        status, payload = _request_json(f"http://127.0.0.1:{server.server_port}/api/health")
        assert status == 200
        assert payload["ok"] is True
        assert payload["webhook_status"] == "listening"
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_public_index_hides_replay_lab_navigation(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        request = Request(f"http://127.0.0.1:{server.server_port}/", method="GET")
        with urlopen(request, timeout=10) as response:
            html = response.read().decode("utf-8")
        assert 'data-page="replay"' not in html
        assert "Replay Lab" not in html
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_replay_inserts_record_into_history_and_detail(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        status, replay = _request_json(
            f"http://127.0.0.1:{server.server_port}/api/replay",
            method="POST",
            body=_valid_payload(),
        )
        assert status == 200
        scan_id = replay["record"]["scan_id"]
        assert replay["result"]["simple_summary"]["setup_status"] == "Ready / Valid setup"
        assert replay["result"]["simple_summary"]["bias"].startswith("Upward bias")
        assert replay["result"]["simple_summary"]["confidence"]
        assert replay["result"]["simple_summary"]["best_action"] == "Consider Long"
        assert replay["result"]["simple_summary"]["why_it_matters"]
        assert replay["result"]["simple_summary"]["trust_signals"]
        assert replay["result"]["simple_summary"]["source_class_label"] == "Replay/demo"
        assert "raw_result" in replay["result"]

        _, history = _request_json(f"http://127.0.0.1:{server.server_port}/api/records")
        assert history["records"][0]["scan_id"] == scan_id
        assert history["records"][0]["confidence_label"]
        assert history["records"][0]["setup_status_label"] == "Ready / Valid setup"
        assert history["records"][0]["bias"].startswith("Upward bias")
        assert history["records"][0]["best_action"] == "Consider Long"
        assert history["records"][0]["trust_signals"]
        assert history["records"][0]["why_it_matters"]
        assert history["records"][0]["source_class_label"] == "Replay/demo"

        _, detail = _request_json(f"http://127.0.0.1:{server.server_port}/api/records/{scan_id}")
        assert detail["display"]["setup_status"] == "Ready / Valid setup"
        assert detail["display"]["bias"].startswith("Upward bias")
        assert detail["display"]["confidence"]
        assert detail["display"]["best_action"] == "Consider Long"
        assert detail["display"]["confidence_explanation"]
        assert detail["display"]["why_it_matters"]
        assert detail["display"]["short_term_target"]
        assert detail["display"]["invalidation"]
        assert detail["display"]["helper_copy"]["target"]
        assert detail["display"]["trust_signals"]
        assert detail["display"]["source_class_label"] == "Replay/demo"
        assert detail["display"]["one_sentence_summary"]
        assert detail["display"]["reason_bullets"]
        assert "timeframe_interpretation" in detail["display"]
        assert detail["display"]["timeframe_story"]
        assert detail["display"]["timeframe_interpretation"]["trigger_5m"]
        assert "action_card" in detail["sections"]
        assert "detailed_analysis" in detail["sections"]
        assert "advanced" in detail["sections"]
        assert "raw_json" in detail["sections"]["advanced"]
        assert detail["sections"]["detailed_analysis"]["levels_summary"]
        assert detail["sections"]["detailed_analysis"]["score_summary"]
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_analyze_thinkorswim_requires_running_browser(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        with patch.object(BrowserSourceManager, "thinkorswim_browser_status", return_value={"running": False, "profile_dir": "data/browser_profiles/thinkorswim_web"}):
            with patch.object(BrowserSourceManager, "status_payload", return_value={"playwright_available": True}):
                status, payload = _request_json(
                    f"http://127.0.0.1:{server.server_port}/api/analyze",
                    method="POST",
                    body={"symbol": "SPY", "source_mode": "thinkorswim_web"},
                )
        assert status == 400
        assert "browser is not running" in payload["error"].lower()
        assert payload["run_state"]["source_mode_requested"] == "thinkorswim_web"
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_analyze_thinkorswim_uses_running_persistent_browser(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        browser_result = BrowserExtractionResult(
            ok=True,
            source_name="thinkorswim_web",
            adapter_kind="thinkorswim",
            page_url_attempted="https://trade.thinkorswim.com/",
            requested_url="https://trade.thinkorswim.com/",
            symbol_requested="SPY",
            symbol_detected="SPY",
            timestamp_utc="2026-04-05T22:00:00Z",
            latest_visible_price=655.87,
            visible_timeframe=None,
            fields_extracted=["symbol", "latest_visible_price"],
            missing_fields=["1D.bars", "1H.bars", "5m.bars"],
            warnings=["thinkorswim web extraction currently uses only visible page context from the persistent browser session."],
            errors=[],
            extraction_status="partial",
            extraction_completeness="partial",
            trust_classification="browser_partial",
            visible_data={"ticker": "SPY", "price_text": "655.87"},
            visible_ticker_text="SPY",
        )
        with patch.object(BrowserSourceManager, "thinkorswim_browser_status", return_value={"running": True, "profile_dir": "data/browser_profiles/thinkorswim_web"}):
            with patch.object(BrowserSourceManager, "extract_symbol", return_value=browser_result):
                status, payload = _request_json(
                    f"http://127.0.0.1:{server.server_port}/api/analyze",
                    method="POST",
                    body={"symbol": "SPY", "source_mode": "thinkorswim_web"},
                )
        assert status == 200
        assert payload["record"]["symbol"] == "SPY"
        assert payload["record"]["source_class_label"] == "Browser extracted"
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_settings_expose_only_public_source_modes_and_ocr_status(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        _, settings = _request_json(f"http://127.0.0.1:{server.server_port}/api/settings")
        assert [mode["value"] for mode in settings["analyze_modes"]] == ["thinkorswim_web"]
        assert settings["source_program"]["active"] is True
        assert settings["source_program"]["mode"] == "thinkorswim_web"
        assert settings["source_program"]["browser_status"]["running"] is False
        assert settings["source_program"]["manual_session_status"]["helper_running"] is False
        assert settings["source_program"]["manual_session_extension"]["path"] == "extensions/stocknogs_thinkorswim_bridge"
        assert settings["source_settings"]["twelvedata"]["configured"] is False
        assert settings["source_settings"]["program"]["active"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_source_browser_start_stop_endpoints(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        with patch.object(BrowserSourceManager, "start_thinkorswim_browser", return_value={"ok": True, "status": "running", "message": "started"}):
            with patch.object(BrowserSourceManager, "thinkorswim_browser_status", return_value={"running": True, "profile_dir": "data/browser_profiles/thinkorswim_web"}):
                status, payload = _request_json(
                    f"http://127.0.0.1:{server.server_port}/api/source-program/start-browser",
                    method="POST",
                    body={},
                )
        assert status == 200
        assert payload["status"] == "running"
        assert payload["browser_status"]["running"] is True

        with patch.object(BrowserSourceManager, "stop_thinkorswim_browser", return_value={"ok": True, "status": "stopped", "message": "stopped"}):
            with patch.object(BrowserSourceManager, "thinkorswim_browser_status", return_value={"running": False, "profile_dir": "data/browser_profiles/thinkorswim_web"}):
                status, payload = _request_json(
                    f"http://127.0.0.1:{server.server_port}/api/source-program/stop-browser",
                    method="POST",
                    body={},
                )
        assert status == 200
        assert payload["status"] == "stopped"
        assert payload["browser_status"]["running"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_manual_session_analyze_creates_record(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        status, payload = _request_json(
            f"http://127.0.0.1:{server.server_port}/api/manual-session/analyze",
            method="POST",
            body={
                "symbol": "SPY",
                "visible_ticker_text": "SPY",
                "latest_visible_price": 655.87,
                "visible_timeframe": "5m",
                "page_title": "Individual Positions | thinkorswim",
                "page_url": "https://trade.thinkorswim.com/",
                "selector_debug": {"symbol": 'input[placeholder*="Find a Symbol"]'},
            },
        )
        assert status == 200
        assert payload["record"]["symbol"] == "SPY"
        assert payload["record"]["source_class_label"] == "Browser extracted"
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_manual_session_report_creates_record_and_clears_queue(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        _request_json(
            f"http://127.0.0.1:{server.server_port}/api/analyze",
            method="POST",
            body={"symbol": "SPY", "source_mode": "thinkorswim_web"},
        )
        status, payload = _request_json(
            f"http://127.0.0.1:{server.server_port}/api/manual-session/report",
            method="POST",
            body={
                "symbol": "SPY",
                "visible_ticker_text": "SPY",
                "latest_visible_price": 655.87,
                "visible_timeframe": "5m",
                "page_title": "Individual Positions | thinkorswim",
                "page_url": "https://trade.thinkorswim.com/",
            },
        )
        assert status == 200
        assert payload["record"]["symbol"] == "SPY"
        _, next_payload = _request_json(f"http://127.0.0.1:{server.server_port}/api/manual-session/next-command")
        assert next_payload["command"] is None
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_manual_session_debug_updates_helper_status(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        status, payload = _request_json(
            f"http://127.0.0.1:{server.server_port}/api/manual-session/debug",
            method="POST",
            body={
                "event": "switch_started",
                "symbol": "SPY",
                "message": "Helper received SPY and is trying to switch the live tab.",
            },
        )
        assert status == 200
        assert payload["helper_status"]["last_symbol"] == "SPY"
        helper_status_code, helper_payload = _request_json(
            f"http://127.0.0.1:{server.server_port}/api/manual-session/status"
        )
        assert helper_status_code == 200
        assert helper_payload["helper_status"]["last_event"] == "Helper received SPY and is trying to switch the live tab."
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_analyze_falls_back_to_manual_helper_when_browser_extract_fails(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        _request_json(
            f"http://127.0.0.1:{server.server_port}/api/manual-session/debug",
            method="POST",
            body={
                "event": "helper_started",
                "message": "Extension bridge is polling stocknogs.",
            },
        )
        browser_result = BrowserExtractionResult(
            ok=False,
            source_name="thinkorswim_web",
            adapter_kind="thinkorswim",
            page_url_attempted="https://trade.thinkorswim.com/",
            requested_url="https://trade.thinkorswim.com/",
            symbol_requested="NVDA",
            symbol_detected=None,
            timestamp_utc="2026-04-05T22:00:00Z",
            latest_visible_price=None,
            visible_timeframe=None,
            missing_fields=["symbol", "price"],
            warnings=["No visible thinkorswim symbol search box was found."],
            errors=["thinkorswim web did not show the requested symbol clearly enough to analyze."],
            extraction_status="failed",
            extraction_completeness="none",
            trust_classification="browser_failed",
        )
        with patch.object(BrowserSourceManager, "thinkorswim_browser_status", return_value={"running": True, "profile_dir": "data/browser_profiles/thinkorswim_web"}):
            with patch.object(BrowserSourceManager, "extract_symbol", return_value=browser_result):
                status, payload = _request_json(
                    f"http://127.0.0.1:{server.server_port}/api/analyze",
                    method="POST",
                    body={"symbol": "NVDA", "source_mode": "thinkorswim_web"},
                )
        assert status == 200
        assert payload["status"] == "queued"
        assert payload["symbol"] == "NVDA"
        assert "browser extension/manual helper bridge" in payload["message"]
        assert payload["fallback_reason"] == "thinkorswim web did not show the requested symbol clearly enough to analyze."
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
def test_gui_api_analyze_new_ticker_becomes_latest_record(tmp_path) -> None:
    pass


@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
def test_gui_api_analyze_returns_readable_failure_for_missing_webhook_source(tmp_path) -> None:
    pass


@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
def test_gui_api_analyze_ocr_returns_honest_unconfigured_failure(tmp_path) -> None:
    pass


@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
def test_gui_api_analyze_browser_returns_honest_partial_record(tmp_path) -> None:
    pass


@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
def test_gui_api_analyze_browser_returns_readable_failure(tmp_path) -> None:
    pass


@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
def test_gui_api_analyze_browser_runtime_failure_returns_json_instead_of_crashing(tmp_path) -> None:
    pass


@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
def test_gui_api_analyze_browser_accepts_tradingview_shaped_result(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        with patch("src.services.browser_source.BrowserSourceManager.extract_symbol") as extract:
            extract.return_value = BrowserExtractionResult(
                ok=True,
                source_name="tradingview_chart_page",
                adapter_kind="tradingview",
                page_url_attempted="https://www.tradingview.com/chart/demo/?symbol=AMEX:SPY",
                requested_url="https://www.tradingview.com/chart/demo/?symbol=AMEX:SPY",
                symbol_requested="SPY",
                symbol_detected="SPY",
                visible_ticker_text="SPY",
                timestamp_utc="2026-04-03T08:30:24Z",
                latest_visible_price=None,
                visible_timeframe="15m",
                visible_timeframe_text="15m",
                page_title="SPY Chart - TradingView",
                chart_canvas_present=True,
                chart_canvas_width=1727,
                chart_canvas_height=447,
                chart_aria_label="Chart for BATS:SPY, 15 minutes",
                price_axis_present=True,
                price_axis_canvas_width=64,
                price_axis_canvas_height=447,
                time_axis_present=True,
                time_axis_canvas_width=1727,
                time_axis_canvas_height=28,
                screenshot_paths={
                    "page": "out/browser_artifacts/tradingview/SPY_page.png",
                    "chart": "out/browser_artifacts/tradingview/SPY_chart.png",
                },
                selector_debug={
                    "ticker": 'button span:text-is("SPY")',
                    "timeframe": "div[data-name='header-toolbar-intervals'] button div",
                    "chart_canvas": 'canvas[data-qa-id="pane-top-canvas"]',
                },
                chart_regions_captured=["page", "chart"],
                fields_extracted=["symbol", "timeframe", "chart_canvas"],
                missing_fields=["price", "1D.bars", "1H.bars", "5m.bars"],
                warnings=[],
                errors=[],
                latency_ms=1400.0,
                extraction_status="partial",
                extraction_completeness="partial",
                trust_classification="browser_partial",
            )
            status, payload = _request_json(
                f"http://127.0.0.1:{server.server_port}/api/analyze",
                method="POST",
                body={"symbol": "SPY", "source_mode": "browser"},
            )
        assert status == 200
        assert payload["record"]["source_class_label"] == "Browser extracted"
        assert payload["result"]["simple_summary"]["confidence_explanation"].startswith("Low confidence because TradingView browser extraction")
        scan_id = payload["record"]["scan_id"]
        _, detail = _request_json(f"http://127.0.0.1:{server.server_port}/api/records/{scan_id}")
        assert detail["sections"]["advanced"]["metrics"]["browser_adapter_kind"] == "tradingview"
        assert detail["sections"]["advanced"]["metrics"]["browser_chart_canvas_present"] is True
        assert detail["sections"]["advanced"]["diagnostics"]["source"]["chart_aria_label"] == "Chart for BATS:SPY, 15 minutes"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
def test_gui_api_auto_can_fall_back_to_browser_with_honest_source_path(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        with patch.object(TwelveDataMarketDataProvider, "get_symbol_data", return_value=_empty_bundle("Twelve Data unavailable.")):
            with patch.object(YahooFinanceMarketDataProvider, "get_symbol_data", return_value=_empty_bundle("Yahoo unavailable.")):
                with patch("src.services.browser_source.BrowserSourceManager.status_payload") as status_payload:
                    with patch("src.services.browser_source.BrowserSourceManager.extract_symbol") as extract:
                        status_payload.return_value = {
                            "enabled": True,
                            "playwright_available": True,
                            "supported_sources": [{"source_name": "yahoo_quote_page", "display_name": "Yahoo Finance quote page", "page_type": "stock_yahoo"}],
                            "headless": True,
                            "current_provider": "stock_yahoo",
                            "tradingview": {"enabled": False, "chart_url_configured": False},
                        }
                        extract.return_value = BrowserExtractionResult(
                            ok=True,
                            source_name="yahoo_quote_page",
                            page_url_attempted="https://finance.yahoo.com/quote/SPY",
                            symbol_requested="SPY",
                            symbol_detected="SPY",
                            timestamp_utc="2026-04-02T12:00:00Z",
                            latest_visible_price=523.11,
                            visible_timeframe=None,
                            fields_extracted=["symbol", "latest_visible_price"],
                            missing_fields=["1D.bars", "1H.bars", "5m.bars"],
                            warnings=["Browser extraction found visible quote data only. Higher timeframe context is missing."],
                            errors=[],
                            latency_ms=1200.0,
                            extraction_status="partial",
                            extraction_completeness="partial",
                            trust_classification="browser_partial",
                        )
                        status, payload = _request_json(
                            f"http://127.0.0.1:{server.server_port}/api/analyze",
                            method="POST",
                            body={"symbol": "SPY", "source_mode": "auto"},
                        )
        assert status == 200
        assert payload["record"]["source_class_label"] == "Browser extracted"
        assert payload["run_state"]["source_used"] == "yahoo_quote_page"
        assert payload["run_state"]["fallback_chain"] == ["twelvedata", "yahoo", "browser"]
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
def test_gui_api_can_test_twelvedata_connection_with_posted_key(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        with patch.object(TwelveDataMarketDataProvider, "get_symbol_data", return_value=_complete_bundle(502.0)):
            status, payload = _request_json(
                f"http://127.0.0.1:{server.server_port}/api/source-settings/test-twelvedata",
                method="POST",
                body={"api_key": "test_key_1234"},
            )
        assert status == 200
        assert payload["status"] == "connected"
        assert payload["message"] == "Twelve Data connection is working."
        assert payload["coverage"]["1D"] is True
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
def test_gui_api_analyze_webhook_reuses_only_fresh_webhook_records(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        webhook_status, _ = _request_json(
            f"http://127.0.0.1:{server.server_port}/webhook",
            method="POST",
            body=_valid_payload("SPY"),
        )
        assert webhook_status == 200

        status, payload = _request_json(
            f"http://127.0.0.1:{server.server_port}/api/analyze",
            method="POST",
            body={"symbol": "SPY", "source_mode": "webhook"},
        )
        assert status == 200
        assert payload["record"]["symbol"] == "SPY"
        assert payload["record"]["source_class_label"] == "Fresh webhook"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
def test_gui_api_analyze_webhook_rejects_stale_webhook_records(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        stale_timestamp = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
        _request_json(
            f"http://127.0.0.1:{server.server_port}/webhook",
            method="POST",
            body=_valid_payload("SPY", timestamp=stale_timestamp),
        )
        status, payload = _request_json(
            f"http://127.0.0.1:{server.server_port}/api/analyze",
            method="POST",
            body={"symbol": "SPY", "source_mode": "webhook"},
        )
        assert status == 400
        assert payload["error"] == "No fresh webhook payload available for requested symbol."
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skip(reason="Archived source-path integration coverage is intentionally paused until the new single source is chosen.")
def test_gui_api_auto_does_not_reuse_replay_demo_records_as_fallback(tmp_path) -> None:
    class _FakeChromium:
        def launch(self, *, headless: bool):
            raise RuntimeError("Executable doesn't exist at C:\\ms-playwright\\chromium\\chrome.exe")

    class _FakePlaywright:
        chromium = _FakeChromium()

    class _FakePlaywrightContext:
        def __enter__(self):
            return _FakePlaywright()

        def __exit__(self, exc_type, exc, tb):
            return False

    server = _start_server(tmp_path)
    try:
        _request_json(
            f"http://127.0.0.1:{server.server_port}/api/replay",
            method="POST",
            body=_valid_payload("SPY"),
        )
        with patch.object(TwelveDataMarketDataProvider, "get_symbol_data", return_value=_empty_bundle("Twelve Data unavailable.")):
            with patch.object(YahooFinanceMarketDataProvider, "get_symbol_data", return_value=_empty_bundle("Yahoo unavailable.")):
                with patch("src.services.browser_source._create_sync_playwright_context", return_value=_FakePlaywrightContext()):
                    with patch.object(
                        BrowserSourceManager,
                        "status_payload",
                        return_value={
                            "enabled": True,
                            "playwright_available": True,
                            "supported_sources": [{"source_name": "yahoo_quote_page", "display_name": "Yahoo Finance quote page", "page_type": "stock_yahoo", "adapter_kind": "yahoo"}],
                            "headless": True,
                            "current_provider": "stock_yahoo",
                            "tradingview": {"enabled": False, "chart_url_configured": False},
                        },
                    ):
                        status, payload = _request_json(
                            f"http://127.0.0.1:{server.server_port}/api/analyze",
                            method="POST",
                            body={"symbol": "SPY", "source_mode": "auto"},
                        )
        assert status == 400
        assert payload["error"] == "Playwright browser executable is missing. Install browser binaries before using browser fallback."
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_exposes_diagnostics_endpoint(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        _request_json(
            f"http://127.0.0.1:{server.server_port}/api/replay",
            method="POST",
            body=_valid_payload(),
        )
        _, diagnostics = _request_json(f"http://127.0.0.1:{server.server_port}/api/diagnostics")
        assert diagnostics["ok"] is True
        assert diagnostics["source"]["source_selected"]
        assert "timeframe_coverage" in diagnostics["source"]
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_loads_history_from_existing_log_on_startup(tmp_path) -> None:
    log_path = tmp_path / "gui.log"
    server = _start_server(tmp_path)
    try:
        _request_json(
            f"http://127.0.0.1:{server.server_port}/api/replay",
            method="POST",
            body=_valid_payload("AAPL"),
        )
    finally:
        server.shutdown()
        server.server_close()

    server = create_gui_server(
        host="127.0.0.1",
        port=0,
        config_dir="config",
        log_path=log_path,
        override_path=tmp_path / "gui_user.yaml",
        demo_override_path="config/demo.yaml",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _, history = _request_json(f"http://127.0.0.1:{server.server_port}/api/records")
        assert history["records"]
        assert history["records"][0]["symbol"] == "AAPL"
        assert history["records"][0]["source_class_label"] == "Replay/demo"
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_can_delete_and_clear_history_records(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        _, first = _request_json(
            f"http://127.0.0.1:{server.server_port}/api/replay",
            method="POST",
            body=_valid_payload("NVDA"),
        )
        _, second = _request_json(
            f"http://127.0.0.1:{server.server_port}/api/replay",
            method="POST",
            body=_valid_payload("QQQ"),
        )
        first_id = first["record"]["scan_id"]

        delete_request = Request(f"http://127.0.0.1:{server.server_port}/api/records/{first_id}", method="DELETE")
        with urlopen(delete_request, timeout=10) as response:
            assert response.status == 200
            deleted = json.loads(response.read().decode("utf-8"))
        assert deleted["ok"] is True

        _, history = _request_json(f"http://127.0.0.1:{server.server_port}/api/records")
        assert all(record["scan_id"] != first_id for record in history["records"])
        assert any(record["scan_id"] == second["record"]["scan_id"] for record in history["records"])

        _, cleared = _request_json(
            f"http://127.0.0.1:{server.server_port}/api/records/clear",
            method="POST",
            body={"symbol": "QQQ"},
        )
        assert cleared["ok"] is True
        assert cleared["deleted_count"] == 1

        _, filtered = _request_json(f"http://127.0.0.1:{server.server_port}/api/records?symbol=QQQ")
        assert filtered["records"] == []
    finally:
        server.shutdown()
        server.server_close()


def test_gui_api_settings_can_save_reset_and_load_demo(tmp_path) -> None:
    server = _start_server(tmp_path)
    try:
        _, initial = _request_json(f"http://127.0.0.1:{server.server_port}/api/settings")
        assert initial["editable_settings"]["trend_filter"]["minimum_trend_strength_score"] == 60.0
        assert initial["source_settings"]["twelvedata"]["configured"] is False

        _, saved = _request_json(
            f"http://127.0.0.1:{server.server_port}/api/settings/save",
            method="POST",
            body={
                "public_webhook_url": "https://example.test/webhook",
                "source_settings": {
                    "source_preferences": {
                        "default_mode": "thinkorswim_web",
                    },
                    "browser": {
                        "provider": "thinkorswim",
                        "persist_screenshots": True,
                        "screenshot_dir": "out/browser_artifacts",
                        "thinkorswim": {
                            "enabled": True,
                            "base_url": "https://trade.thinkorswim.com/",
                            "profile_dir": "data/browser_profiles/thinkorswim_web",
                            "page_load_timeout_ms": 21000,
                            "settle_wait_ms": 2500,
                            "keep_browser_open": True,
                            "launch_on_startup": False,
                        },
                    },
                },
                "editable_settings": {
                    "trend_filter": {
                        "minimum_trend_strength_score": "72",
                        "minimum_slope_pct": "0.5",
                    },
                    "compression": {
                        "maximum_pullback_depth_pct": "30",
                        "minimum_range_contraction_pct": "24",
                        "minimum_volatility_contraction_pct": "18",
                    },
                    "breakout_trigger": {
                        "breakout_buffer_pct": "0.2",
                        "minimum_breakout_range_vs_base_avg": "1.8",
                        "minimum_relative_volume": "1.4",
                    },
                    "trap_risk": {
                        "maximum_distance_from_trend_ref_pct": "7",
                        "maximum_rejection_wick_pct": "20",
                        "minimum_overhead_clearance_pct": "3",
                    },
                    "scoring": {
                        "trend_alignment": "22",
                        "squeeze_quality": "24",
                        "breakout_impulse": "26",
                        "path_quality": "18",
                        "trap_risk_penalty": "10",
                    },
                },
            },
        )
        assert saved["ok"] is True
        assert saved["settings"]["public_webhook_url"] == "https://example.test/webhook"
        assert saved["settings"]["editable_settings"]["trend_filter"]["minimum_trend_strength_score"] == 72.0
        assert saved["settings"]["source_program"]["active"] is True
        assert saved["settings"]["source_settings"]["program"]["active"] is True

        source_settings_file = tmp_path / "gui_sources.yaml"
        stored_source_settings = load_optional_yaml(source_settings_file)
        assert stored_source_settings["twelvedata"]["api_key"] == ""
        assert stored_source_settings["source_preferences"]["default_mode"] == "thinkorswim_web"
        assert stored_source_settings["browser"]["provider"] == "thinkorswim"
        assert stored_source_settings["browser"]["thinkorswim"]["profile_dir"] == "data/browser_profiles/thinkorswim_web"

        _, demo = _request_json(f"http://127.0.0.1:{server.server_port}/api/settings/load-demo", method="POST")
        assert demo["ok"] is True
        assert demo["settings"]["editable_settings"]["trend_filter"]["minimum_trend_strength_score"] == 60.0

        _, reset = _request_json(f"http://127.0.0.1:{server.server_port}/api/settings/reset", method="POST")
        assert reset["ok"] is True
        assert reset["settings"]["editable_settings"]["trend_filter"]["minimum_trend_strength_score"] == 60.0
        assert reset["settings"]["source_settings"]["twelvedata"]["configured"] is False
        assert not source_settings_file.exists()
    finally:
        server.shutdown()
        server.server_close()
