from pathlib import Path
from unittest.mock import patch

from src.services.browser_source import (
    BrowserExtractionResult,
    BrowserSourceManager,
    TradingViewChartAdapter,
    YahooFinanceQuoteAdapter,
)


class _FakeLocator:
    def __init__(
        self,
        *,
        text: str | None = None,
        attrs: dict[str, str] | None = None,
        fail_screenshot: bool = False,
    ) -> None:
        self._text = text or ""
        self._attrs = attrs or {}
        self._fail_screenshot = fail_screenshot
        self.first = self

    def wait_for(self, *, state: str, timeout: int) -> None:
        assert state == "visible"
        assert timeout > 0

    def text_content(self) -> str:
        return self._text

    def get_attribute(self, name: str) -> str | None:
        return self._attrs.get(name)

    def screenshot(self, *, path: str) -> None:
        if self._fail_screenshot:
            raise RuntimeError("screenshot failed")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"fake")


class _FakeYahooPage:
    def goto(self, url: str, *, wait_until: str, timeout: int | None = None) -> None:
        assert "finance.yahoo.com/quote/SPY" in url
        assert wait_until == "domcontentloaded"

    def locator(self, selector: str) -> _FakeLocator:
        if 'regularMarketPrice' in selector:
            return _FakeLocator(text="523.11")
        if selector == "h1":
            return _FakeLocator(text="SPY - SPDR S&P 500 ETF Trust")
        raise AssertionError(f"Unexpected selector: {selector}")

    def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        assert state == "networkidle"


class _FakeTradingViewPage:
    def __init__(self, tmp_path: Path, *, fail_region: str | None = None) -> None:
        self.tmp_path = tmp_path
        self.fail_region = fail_region

    def goto(self, url: str, *, wait_until: str, timeout: int | None = None) -> None:
        assert "tradingview.com/chart/demo/?symbol=AMEX:SPY" in url
        assert wait_until == "domcontentloaded"
        assert timeout == 15000

    def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        assert state == "networkidle"

    def wait_for_timeout(self, timeout: int) -> None:
        assert timeout == 2500

    def title(self) -> str:
        return "SPY Chart - TradingView"

    def screenshot(self, *, path: str, full_page: bool) -> None:
        assert full_page is True
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"page")

    def locator(self, selector: str) -> _FakeLocator:
        if selector == 'button span:text-is("SPY")':
            return _FakeLocator(text="SPY")
        if selector == "div[data-name='header-toolbar-intervals'] button div":
            return _FakeLocator(text="15m")
        if selector == 'canvas[data-qa-id="pane-top-canvas"]':
            return _FakeLocator(
                attrs={"width": "1727", "height": "447", "aria-label": "Chart for BATS:SPY, 15 minutes"},
                fail_screenshot=self.fail_region == "chart",
            )
        if selector == "div.price-axis canvas":
            return _FakeLocator(
                attrs={"width": "64", "height": "447"},
                fail_screenshot=self.fail_region == "price_axis",
            )
        if selector == ".time-axis > div:nth-child(1) > canvas:nth-child(2)":
            return _FakeLocator(
                attrs={"width": "1727", "height": "28"},
                fail_screenshot=self.fail_region == "time_axis",
            )
        raise RuntimeError(f"selector unavailable: {selector}")


class _FakeBrowser:
    def __init__(self, *, fail_new_page: bool = False) -> None:
        self.fail_new_page = fail_new_page

    def new_page(self):
        if self.fail_new_page:
            raise RuntimeError("page init failed")
        return object()

    def close(self) -> None:
        return None


class _FakeChromium:
    def __init__(self, *, launch_error: str | None = None, fail_new_page: bool = False) -> None:
        self.launch_error = launch_error
        self.fail_new_page = fail_new_page

    def launch(self, *, headless: bool):
        assert isinstance(headless, bool)
        if self.launch_error is not None:
            raise RuntimeError(self.launch_error)
        return _FakeBrowser(fail_new_page=self.fail_new_page)


class _FakePlaywrightRuntime:
    def __init__(self, *, launch_error: str | None = None, fail_new_page: bool = False) -> None:
        self.chromium = _FakeChromium(launch_error=launch_error, fail_new_page=fail_new_page)


class _FakePlaywrightContext:
    def __init__(self, *, launch_error: str | None = None, fail_new_page: bool = False) -> None:
        self.launch_error = launch_error
        self.fail_new_page = fail_new_page

    def __enter__(self) -> _FakePlaywrightRuntime:
        return _FakePlaywrightRuntime(launch_error=self.launch_error, fail_new_page=self.fail_new_page)

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_yahoo_finance_quote_adapter_extracts_visible_quote_fields() -> None:
    adapter = YahooFinanceQuoteAdapter()
    result = adapter.extract(_FakeYahooPage(), symbol="SPY")
    assert result.ok is True
    assert result.symbol_detected == "SPY"
    assert result.latest_visible_price == 523.11
    assert result.trust_classification == "browser_partial"
    assert "1D.bars" in result.missing_fields


def test_tradingview_adapter_returns_honest_missing_config_failure() -> None:
    adapter = TradingViewChartAdapter(chart_url_template="", exchange_prefix="AMEX")
    result = adapter.extract(object(), symbol="SPY")
    assert result.ok is False
    assert result.adapter_kind == "tradingview"
    assert result.errors == ["TradingView browser source is not configured for this page type yet."]


def test_tradingview_adapter_extracts_visible_chart_context(tmp_path: Path) -> None:
    adapter = TradingViewChartAdapter(
        chart_url_template="https://www.tradingview.com/chart/demo/?symbol={exchange_symbol}",
        exchange_prefix="AMEX",
        screenshot_dir=str(tmp_path / "artifacts"),
    )
    result = adapter.extract(_FakeTradingViewPage(tmp_path), symbol="SPY")
    assert result.ok is True
    assert result.symbol_detected == "SPY"
    assert result.visible_timeframe == "15m"
    assert result.chart_canvas_present is True
    assert result.chart_canvas_width == 1727
    assert result.chart_canvas_height == 447
    assert result.chart_aria_label == "Chart for BATS:SPY, 15 minutes"
    assert result.price_axis_present is True
    assert result.time_axis_present is True
    assert result.selector_debug["ticker"] == 'button span:text-is("SPY")'
    assert result.selector_debug["chart_canvas"] == 'canvas[data-qa-id="pane-top-canvas"]'
    assert result.screenshot_paths["page"].endswith("_page.png")
    assert "chart" in result.chart_regions_captured
    assert "price" not in result.fields_extracted
    assert "price" in result.missing_fields
    assert result.trust_classification == "browser_partial"


def test_tradingview_adapter_warns_when_region_screenshot_fails(tmp_path: Path) -> None:
    adapter = TradingViewChartAdapter(
        chart_url_template="https://www.tradingview.com/chart/demo/?symbol={exchange_symbol}",
        exchange_prefix="AMEX",
        screenshot_dir=str(tmp_path / "artifacts"),
    )
    result = adapter.extract(_FakeTradingViewPage(tmp_path, fail_region="time_axis"), symbol="SPY")
    assert result.ok is True
    assert any("time axis screenshot" in warning.lower() for warning in result.warnings)


def test_browser_source_manager_reports_missing_playwright_cleanly() -> None:
    manager = BrowserSourceManager()
    with patch.object(
        BrowserSourceManager,
        "status_payload",
        return_value={"enabled": True, "playwright_available": False, "supported_sources": [], "headless": True, "current_provider": "stock_yahoo", "tradingview": {"enabled": False, "chart_url_configured": False}},
    ):
        result = manager.extract_stock_quote("SPY")
    assert isinstance(result, BrowserExtractionResult)
    assert result.ok is False
    assert result.trust_classification == "browser_failed"
    assert result.errors == ["Browser extraction is not available because Playwright is not installed."]


def test_browser_source_manager_returns_clean_failure_when_browser_launch_fails() -> None:
    manager = BrowserSourceManager()
    with patch.object(
        BrowserSourceManager,
        "status_payload",
        return_value={"enabled": True, "playwright_available": True, "supported_sources": [], "headless": True, "current_provider": "stock_yahoo", "tradingview": {"enabled": False, "chart_url_configured": False}},
    ):
        with patch(
            "src.services.browser_source._create_sync_playwright_context",
            return_value=_FakePlaywrightContext(launch_error="Executable doesn't exist at C:\\ms-playwright\\chromium\\chrome.exe"),
        ):
            result = manager.extract_stock_quote("SPY")
    assert isinstance(result, BrowserExtractionResult)
    assert result.ok is False
    assert result.source_name == "yahoo_quote_page"
    assert result.adapter_kind == "yahoo"
    assert result.trust_classification == "browser_failed"
    assert result.extraction_status == "failed"
    assert result.extraction_completeness == "none"
    assert result.page_url_attempted == "https://finance.yahoo.com/quote/SPY"
    assert result.errors == ["Playwright browser executable is missing. Install browser binaries before using browser fallback."]
