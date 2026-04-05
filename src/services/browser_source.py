from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from src.services.config_loader import load_source_settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_filename_timestamp(value: str | None) -> str:
    text = value or _utc_now_iso()
    return text.replace(":", "-").replace(".", "-")


def _safe_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _create_sync_playwright_context() -> Any:
    from playwright.sync_api import sync_playwright

    return sync_playwright()


@dataclass(slots=True)
class BrowserExtractionResult:
    ok: bool
    source_name: str
    page_url_attempted: str
    symbol_requested: str
    symbol_detected: str | None
    timestamp_utc: str | None
    latest_visible_price: float | None
    visible_timeframe: str | None
    fields_extracted: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    latency_ms: float | None = None
    extraction_status: str = "failed"
    extraction_completeness: str = "none"
    trust_classification: str = "browser_failed"
    visible_data: dict[str, Any] = field(default_factory=dict)
    adapter_kind: str | None = None
    requested_url: str | None = None
    page_title: str | None = None
    screenshot_paths: dict[str, str] = field(default_factory=dict)
    selector_debug: dict[str, str] = field(default_factory=dict)
    chart_canvas_present: bool = False
    chart_canvas_width: int | None = None
    chart_canvas_height: int | None = None
    chart_aria_label: str | None = None
    price_axis_present: bool = False
    price_axis_canvas_width: int | None = None
    price_axis_canvas_height: int | None = None
    time_axis_present: bool = False
    time_axis_canvas_width: int | None = None
    time_axis_canvas_height: int | None = None
    visible_ticker_text: str | None = None
    visible_timeframe_text: str | None = None
    chart_regions_captured: list[str] = field(default_factory=list)


class BrowserSourceAdapter(ABC):
    source_name: str = "browser"
    display_name: str = "Browser source"
    adapter_kind: str = "browser"

    @abstractmethod
    def build_url(self, symbol: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def extract(self, page: Any, *, symbol: str) -> BrowserExtractionResult:
        raise NotImplementedError


def _browser_runtime_error_message(exc: Exception, *, phase: str) -> str:
    text = str(exc).strip()
    lowered = text.lower()
    if "executable doesn't exist" in lowered or "executable doesn't exist at" in lowered:
        return "Playwright browser executable is missing. Install browser binaries before using browser fallback."
    if "failed to launch" in lowered or phase == "launch":
        suffix = f": {text}" if text else "."
        return f"Browser launch failed during Playwright startup{suffix}"
    if phase == "page":
        suffix = f": {text}" if text else "."
        return f"Browser page creation failed{suffix}"
    suffix = f": {text}" if text else "."
    return f"Browser startup failed during Playwright initialization{suffix}"


def _browser_runtime_failure_result(
    adapter: BrowserSourceAdapter,
    *,
    symbol: str,
    attempted_url: str,
    error_text: str,
) -> BrowserExtractionResult:
    return BrowserExtractionResult(
        ok=False,
        source_name=adapter.source_name,
        page_url_attempted=attempted_url,
        requested_url=attempted_url,
        symbol_requested=symbol,
        symbol_detected=None,
        timestamp_utc=None,
        latest_visible_price=None,
        visible_timeframe=None,
        missing_fields=["symbol", "price"],
        errors=[error_text],
        extraction_status="failed",
        extraction_completeness="none",
        trust_classification="browser_failed",
        adapter_kind=adapter.adapter_kind,
    )


def _try_text(page: Any, selectors: list[str], *, timeout_ms: int = 5000) -> tuple[str | None, str | None]:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            text = (locator.text_content() or "").strip()
            if text:
                return text, selector
        except Exception:
            continue
    return None, None


def _try_locator(page: Any, selectors: list[str], *, timeout_ms: int = 5000) -> tuple[Any | None, str | None]:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator, selector
        except Exception:
            continue
    return None, None


def _maybe_float(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = text.replace(",", "").replace("$", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _locator_canvas_meta(locator: Any) -> tuple[int | None, int | None, str | None]:
    width = None
    height = None
    aria_label = None
    try:
        width = _safe_int(locator.get_attribute("width"), 0) or None
    except Exception:
        width = None
    try:
        height = _safe_int(locator.get_attribute("height"), 0) or None
    except Exception:
        height = None
    try:
        aria_label = locator.get_attribute("aria-label")
    except Exception:
        aria_label = None
    return width, height, aria_label


class YahooFinanceQuoteAdapter(BrowserSourceAdapter):
    source_name = "yahoo_quote_page"
    display_name = "Yahoo Finance quote page"
    adapter_kind = "yahoo"

    def build_url(self, symbol: str) -> str:
        return f"https://finance.yahoo.com/quote/{symbol}"

    def extract(self, page: Any, *, symbol: str) -> BrowserExtractionResult:
        url = self.build_url(symbol)
        start = perf_counter()
        try:
            page.goto(url, wait_until="domcontentloaded")
            price_locator = page.locator('fin-streamer[data-field="regularMarketPrice"]').first
            symbol_locator = page.locator("h1").first
            page.wait_for_load_state("networkidle")
            price_locator.wait_for(state="visible", timeout=8000)
            symbol_locator.wait_for(state="visible", timeout=8000)
            price_text = price_locator.text_content() or ""
            symbol_heading = symbol_locator.text_content() or ""
        except Exception as exc:
            return BrowserExtractionResult(
                ok=False,
                source_name=self.source_name,
                page_url_attempted=url,
                requested_url=url,
                symbol_requested=symbol,
                symbol_detected=None,
                timestamp_utc=None,
                latest_visible_price=None,
                visible_timeframe=None,
                missing_fields=["symbol", "price"],
                errors=[f"Supported page loaded, but expected quote fields were not available: {exc}"],
                latency_ms=round((perf_counter() - start) * 1000.0, 2),
                extraction_status="failed",
                extraction_completeness="none",
                trust_classification="browser_failed",
                adapter_kind=self.adapter_kind,
            )

        symbol_detected = symbol if symbol.upper() in symbol_heading.upper() else None
        latest_price = _maybe_float(price_text)

        fields_extracted: list[str] = []
        if symbol_detected:
            fields_extracted.append("symbol")
        if latest_price is not None:
            fields_extracted.append("latest_visible_price")

        missing_fields: list[str] = []
        if symbol_detected is None:
            missing_fields.append("symbol")
        if latest_price is None:
            missing_fields.append("price")
        missing_fields.extend(["1D.bars", "1H.bars", "5m.bars"])

        warnings: list[str] = []
        if symbol_detected is None:
            warnings.append("The page did not clearly show the requested symbol in the expected quote heading.")
        warnings.append("Browser extraction found visible quote data only. Higher timeframe context is missing.")

        ok = latest_price is not None and symbol_detected is not None
        return BrowserExtractionResult(
            ok=ok,
            source_name=self.source_name,
            page_url_attempted=url,
            requested_url=url,
            symbol_requested=symbol,
            symbol_detected=symbol_detected,
            timestamp_utc=_utc_now_iso(),
            latest_visible_price=latest_price,
            visible_timeframe=None,
            fields_extracted=fields_extracted,
            missing_fields=missing_fields,
            warnings=warnings,
            errors=[] if ok else ["Supported page loaded, but no symbol data was found."],
            latency_ms=round((perf_counter() - start) * 1000.0, 2),
            extraction_status="partial" if ok else "failed",
            extraction_completeness="partial" if ok else "none",
            trust_classification="browser_partial" if ok else "browser_failed",
            visible_data={"quote_heading": symbol_heading, "price_text": price_text},
            adapter_kind=self.adapter_kind,
            page_title=f"{symbol_heading} - Yahoo Finance",
        )


class TradingViewChartAdapter(BrowserSourceAdapter):
    source_name = "tradingview_chart_page"
    display_name = "TradingView live chart page"
    adapter_kind = "tradingview"

    def __init__(
        self,
        *,
        chart_url_template: str,
        exchange_prefix: str = "",
        page_load_timeout_ms: int = 15000,
        settle_wait_ms: int = 2500,
        persist_screenshots: bool = True,
        screenshot_dir: str = "out/browser_artifacts",
    ) -> None:
        self.chart_url_template = chart_url_template
        self.exchange_prefix = exchange_prefix
        self.page_load_timeout_ms = page_load_timeout_ms
        self.settle_wait_ms = settle_wait_ms
        self.persist_screenshots = persist_screenshots
        self.screenshot_dir = screenshot_dir

    def build_url(self, symbol: str) -> str:
        if not self.chart_url_template:
            return ""
        exchange_symbol = f"{self.exchange_prefix}:{symbol}" if self.exchange_prefix else symbol
        return (
            self.chart_url_template.replace("{symbol}", symbol)
            .replace("{exchange_symbol}", exchange_symbol)
        )

    def _wait_for_tradingview_chart_ready(self, page: Any) -> tuple[Any | None, str | None]:
        page.wait_for_load_state("networkidle", timeout=self.page_load_timeout_ms)
        chart_locator, selector = _try_locator(
            page,
            selectors=[
                'canvas[data-qa-id="pane-top-canvas"]',
                'xpath=/html/body/div[2]/div/div[5]/div[1]/div[1]/div/div[2]/div[1]/div[2]/div/canvas[2]',
            ],
            timeout_ms=self.page_load_timeout_ms,
        )
        if chart_locator is not None and self.settle_wait_ms > 0:
            try:
                page.wait_for_timeout(self.settle_wait_ms)
            except Exception:
                pass
        return chart_locator, selector

    def _extract_tradingview_ticker(self, page: Any, symbol: str) -> tuple[str | None, str | None]:
        return _try_text(
            page,
            selectors=[
                f'button span:text-is("{symbol}")',
                'xpath=/html/body/div[2]/div/div[3]/div/div/div[3]/div[1]/div/div/div/div/div[2]/div/button[1]/span',
                'span[class*="value-"]',
            ],
            timeout_ms=4000,
        )

    def _extract_tradingview_timeframe(self, page: Any) -> tuple[str | None, str | None]:
        return _try_text(
            page,
            selectors=[
                "div[data-name='header-toolbar-intervals'] button div",
                'xpath=/html/body/div[2]/div/div[3]/div/div/div[3]/div[1]/div/div/div/div/div[4]/div/button/div/div',
                "div[class*='value-']",
            ],
            timeout_ms=4000,
        )

    def _extract_chart_canvas_meta(self, page: Any) -> tuple[dict[str, Any], str | None]:
        locator, selector = _try_locator(
            page,
            selectors=[
                'canvas[data-qa-id="pane-top-canvas"]',
                'xpath=/html/body/div[2]/div/div[5]/div[1]/div[1]/div/div[2]/div[1]/div[2]/div/canvas[2]',
            ],
            timeout_ms=4000,
        )
        if locator is None:
            return {"present": False, "width": None, "height": None, "aria_label": None, "locator": None}, selector
        width, height, aria_label = _locator_canvas_meta(locator)
        return {"present": True, "width": width, "height": height, "aria_label": aria_label, "locator": locator}, selector

    def _extract_price_axis_meta(self, page: Any) -> tuple[dict[str, Any], str | None]:
        locator, selector = _try_locator(
            page,
            selectors=[
                "div.price-axis canvas",
                'xpath=/html/body/div[2]/div/div[5]/div[1]/div[1]/div/div[2]/div[1]/div[3]/div',
            ],
            timeout_ms=3000,
        )
        if locator is None:
            return {"present": False, "width": None, "height": None, "locator": None}, selector
        width, height, _ = _locator_canvas_meta(locator)
        return {"present": True, "width": width, "height": height, "locator": locator}, selector

    def _extract_time_axis_meta(self, page: Any) -> tuple[dict[str, Any], str | None]:
        locator, selector = _try_locator(
            page,
            selectors=[
                ".time-axis > div:nth-child(1) > canvas:nth-child(2)",
                "div.chart-markup-table.time-axis div canvas:nth-child(2)",
                'xpath=/html/body/div[2]/div/div[5]/div[1]/div[1]/div/div[2]/div[4]/div[2]/div/canvas[2]',
            ],
            timeout_ms=3000,
        )
        if locator is None:
            return {"present": False, "width": None, "height": None, "locator": None}, selector
        width, height, _ = _locator_canvas_meta(locator)
        return {"present": True, "width": width, "height": height, "locator": locator}, selector

    def _capture_tradingview_artifacts(
        self,
        page: Any,
        *,
        symbol: str,
        timestamp_utc: str,
        chart_locator: Any | None,
        price_axis_locator: Any | None,
        time_axis_locator: Any | None,
    ) -> tuple[dict[str, str], list[str], list[str]]:
        screenshot_paths: dict[str, str] = {}
        captured: list[str] = []
        warnings: list[str] = []
        if not self.persist_screenshots:
            return screenshot_paths, captured, warnings

        base_dir = Path(self.screenshot_dir) / "tradingview"
        base_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{symbol}_{_safe_filename_timestamp(timestamp_utc)}_{self.adapter_kind}"

        try:
            page_path = base_dir / f"{stem}_page.png"
            page.screenshot(path=str(page_path), full_page=True)
            screenshot_paths["page"] = str(page_path)
            captured.append("page")
        except Exception as exc:
            warnings.append(f"Could not save full page screenshot: {exc}")

        for region_name, locator in (
            ("chart", chart_locator),
            ("price_axis", price_axis_locator),
            ("time_axis", time_axis_locator),
        ):
            if locator is None:
                continue
            try:
                region_path = base_dir / f"{stem}_{region_name}.png"
                locator.screenshot(path=str(region_path))
                screenshot_paths[region_name] = str(region_path)
                captured.append(region_name)
            except Exception as exc:
                warnings.append(f"Could not save {region_name.replace('_', ' ')} screenshot: {exc}")
        return screenshot_paths, captured, warnings

    def extract(self, page: Any, *, symbol: str) -> BrowserExtractionResult:
        requested_url = self.build_url(symbol)
        start = perf_counter()
        if not requested_url:
            return BrowserExtractionResult(
                ok=False,
                source_name=self.source_name,
                page_url_attempted="",
                requested_url="",
                symbol_requested=symbol,
                symbol_detected=None,
                timestamp_utc=None,
                latest_visible_price=None,
                visible_timeframe=None,
                missing_fields=["symbol", "timeframe", "chart_canvas"],
                errors=["TradingView browser source is not configured for this page type yet."],
                extraction_status="failed",
                extraction_completeness="none",
                trust_classification="browser_failed",
                adapter_kind=self.adapter_kind,
            )

        try:
            page.goto(requested_url, wait_until="domcontentloaded", timeout=self.page_load_timeout_ms)
            chart_locator, chart_selector = self._wait_for_tradingview_chart_ready(page)
        except Exception as exc:
            return BrowserExtractionResult(
                ok=False,
                source_name=self.source_name,
                page_url_attempted=requested_url,
                requested_url=requested_url,
                symbol_requested=symbol,
                symbol_detected=None,
                timestamp_utc=None,
                latest_visible_price=None,
                visible_timeframe=None,
                missing_fields=["symbol", "timeframe", "chart_canvas"],
                errors=[f"Supported TradingView page could not be loaded: {exc}"],
                latency_ms=round((perf_counter() - start) * 1000.0, 2),
                extraction_status="failed",
                extraction_completeness="none",
                trust_classification="browser_failed",
                adapter_kind=self.adapter_kind,
            )

        timestamp_utc = _utc_now_iso()
        warnings: list[str] = []
        page_title = None
        try:
            page_title = page.title()
        except Exception:
            page_title = None

        visible_ticker_text, ticker_selector = self._extract_tradingview_ticker(page, symbol)
        visible_timeframe_text, timeframe_selector = self._extract_tradingview_timeframe(page)
        chart_meta, chart_selector = self._extract_chart_canvas_meta(page)
        price_axis_meta, price_selector = self._extract_price_axis_meta(page)
        time_axis_meta, time_selector = self._extract_time_axis_meta(page)

        screenshot_paths, chart_regions_captured, screenshot_warnings = self._capture_tradingview_artifacts(
            page,
            symbol=symbol,
            timestamp_utc=timestamp_utc,
            chart_locator=chart_meta.get("locator"),
            price_axis_locator=price_axis_meta.get("locator"),
            time_axis_locator=time_axis_meta.get("locator"),
        )
        warnings.extend(screenshot_warnings)

        symbol_detected = None
        if visible_ticker_text and symbol.upper() in visible_ticker_text.upper():
            symbol_detected = symbol

        fields_extracted: list[str] = []
        if symbol_detected:
            fields_extracted.append("symbol")
        if visible_timeframe_text:
            fields_extracted.append("timeframe")
        if chart_meta["present"]:
            fields_extracted.append("chart_canvas")
        if price_axis_meta["present"]:
            fields_extracted.append("price_axis")
        if time_axis_meta["present"]:
            fields_extracted.append("time_axis")

        missing_fields: list[str] = []
        if not symbol_detected:
            missing_fields.append("symbol")
            warnings.append("The TradingView page did not clearly show the requested symbol in the expected visible area.")
        if not visible_timeframe_text:
            missing_fields.append("timeframe")
            warnings.append("The visible top-toolbar timeframe could not be extracted from the TradingView page.")
        if not chart_meta["present"]:
            missing_fields.append("chart_canvas")
            warnings.append("The main TradingView chart canvas was not found.")
        missing_fields.append("price")
        missing_fields.extend(["1D.bars", "1H.bars", "5m.bars"])

        if not price_axis_meta["present"]:
            warnings.append("The TradingView price-axis canvas was not found.")
        if not time_axis_meta["present"]:
            warnings.append("The TradingView bottom time-axis canvas was not found.")
        if chart_meta["present"]:
            warnings.append("TradingView browser extraction captured visible chart context only. Structured OHLCV bars remain unavailable.")

        selector_debug = {
            "ticker": ticker_selector or "",
            "timeframe": timeframe_selector or "",
            "chart_canvas": chart_selector or "",
            "price_axis": price_selector or "",
            "time_axis": time_selector or "",
        }

        ok = bool(symbol_detected and chart_meta["present"])
        errors = [] if ok else ["Supported page loaded, but no symbol data was found."]
        if not chart_meta["present"] and "chart_canvas" in missing_fields:
            errors = ["Page structure changed and expected chart fields were missing."]

        return BrowserExtractionResult(
            ok=ok,
            source_name=self.source_name,
            page_url_attempted=requested_url,
            requested_url=requested_url,
            symbol_requested=symbol,
            symbol_detected=symbol_detected,
            timestamp_utc=timestamp_utc,
            latest_visible_price=None,
            visible_timeframe=visible_timeframe_text,
            fields_extracted=fields_extracted,
            missing_fields=missing_fields,
            warnings=warnings,
            errors=errors,
            latency_ms=round((perf_counter() - start) * 1000.0, 2),
            extraction_status="partial" if ok else "failed",
            extraction_completeness="partial" if ok else "none",
            trust_classification="browser_partial" if ok else "browser_failed",
            visible_data={
                "ticker": visible_ticker_text,
                "timeframe": visible_timeframe_text,
                "chart_aria_label": chart_meta["aria_label"],
            },
            adapter_kind=self.adapter_kind,
            page_title=page_title,
            screenshot_paths=screenshot_paths,
            selector_debug=selector_debug,
            chart_canvas_present=bool(chart_meta["present"]),
            chart_canvas_width=chart_meta["width"],
            chart_canvas_height=chart_meta["height"],
            chart_aria_label=chart_meta["aria_label"],
            price_axis_present=bool(price_axis_meta["present"]),
            price_axis_canvas_width=price_axis_meta["width"],
            price_axis_canvas_height=price_axis_meta["height"],
            time_axis_present=bool(time_axis_meta["present"]),
            time_axis_canvas_width=time_axis_meta["width"],
            time_axis_canvas_height=time_axis_meta["height"],
            visible_ticker_text=visible_ticker_text,
            visible_timeframe_text=visible_timeframe_text,
            chart_regions_captured=chart_regions_captured,
        )


class ThinkorswimWebAdapter(BrowserSourceAdapter):
    source_name = "thinkorswim_web"
    display_name = "thinkorswim web"
    adapter_kind = "thinkorswim"

    def __init__(
        self,
        *,
        base_url: str = "https://trade.thinkorswim.com/",
        page_load_timeout_ms: int = 20000,
        settle_wait_ms: int = 2000,
        persist_screenshots: bool = True,
        screenshot_dir: str = "out/browser_artifacts",
    ) -> None:
        self.base_url = base_url
        self.page_load_timeout_ms = page_load_timeout_ms
        self.settle_wait_ms = settle_wait_ms
        self.persist_screenshots = persist_screenshots
        self.screenshot_dir = screenshot_dir

    def build_url(self, symbol: str) -> str:
        return self.base_url

    def _capture_artifacts(self, page: Any, *, symbol: str, timestamp_utc: str) -> tuple[dict[str, str], list[str], list[str]]:
        screenshot_paths: dict[str, str] = {}
        captured: list[str] = []
        warnings: list[str] = []
        if not self.persist_screenshots:
            return screenshot_paths, captured, warnings

        base_dir = Path(self.screenshot_dir) / "thinkorswim"
        base_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{symbol}_{_safe_filename_timestamp(timestamp_utc)}_{self.adapter_kind}"
        try:
            page_path = base_dir / f"{stem}_page.png"
            page.screenshot(path=str(page_path), full_page=True)
            screenshot_paths["page"] = str(page_path)
            captured.append("page")
        except Exception as exc:
            warnings.append(f"Could not save thinkorswim page screenshot: {exc}")
        return screenshot_paths, captured, warnings

    def _search_symbol(self, page: Any, symbol: str) -> tuple[bool, str | None]:
        selectors = [
            'input[placeholder*="Find a Symbol"]',
            'input[placeholder*="Symbol"]',
            'input[type="search"]',
        ]
        locator, selector = _try_locator(page, selectors, timeout_ms=3000)
        if locator is None:
            return False, None
        try:
            locator.click()
            locator.fill(symbol)
            locator.press("Enter")
            if self.settle_wait_ms > 0:
                page.wait_for_timeout(self.settle_wait_ms)
            return True, selector
        except Exception:
            return False, selector

    def _extract_symbol_text(self, page: Any, symbol: str) -> tuple[str | None, str | None]:
        return _try_text(
            page,
            selectors=[
                f'text="{symbol}"',
                'input[placeholder*="Find a Symbol"]',
                'input[placeholder*="Symbol"]',
                "h1",
                "h2",
            ],
            timeout_ms=3000,
        )

    def _extract_price_text(self, page: Any) -> tuple[str | None, str | None]:
        return _try_text(
            page,
            selectors=[
                '[data-testid*="last"]',
                '[data-testid*="price"]',
                'div[class*="price"]',
                'span[class*="price"]',
            ],
            timeout_ms=2500,
        )

    def extract(self, page: Any, *, symbol: str) -> BrowserExtractionResult:
        start = perf_counter()
        requested_url = self.build_url(symbol)
        timestamp_utc = _utc_now_iso()
        warnings: list[str] = []
        selector_debug: dict[str, str] = {}
        try:
            current_url = ""
            try:
                current_url = page.url
            except Exception:
                current_url = ""
            if not current_url:
                page.goto(requested_url, wait_until="domcontentloaded", timeout=self.page_load_timeout_ms)
            if self.settle_wait_ms > 0:
                page.wait_for_timeout(self.settle_wait_ms)
        except Exception as exc:
            return BrowserExtractionResult(
                ok=False,
                source_name=self.source_name,
                page_url_attempted=requested_url,
                requested_url=requested_url,
                symbol_requested=symbol,
                symbol_detected=None,
                timestamp_utc=None,
                latest_visible_price=None,
                visible_timeframe=None,
                missing_fields=["symbol", "price"],
                errors=[f"thinkorswim web page could not be opened in the persistent browser: {exc}"],
                latency_ms=round((perf_counter() - start) * 1000.0, 2),
                extraction_status="failed",
                extraction_completeness="none",
                trust_classification="browser_failed",
                adapter_kind=self.adapter_kind,
            )

        search_attempted, search_selector = self._search_symbol(page, symbol)
        if search_selector:
            selector_debug["symbol_search"] = search_selector
        if search_attempted:
            warnings.append("The persistent thinkorswim browser attempted to focus the visible symbol search box.")
        else:
            warnings.append("No visible thinkorswim symbol search box was found, so the app relied on the current page state.")

        page_title = None
        try:
            page_title = page.title()
        except Exception:
            page_title = None

        visible_ticker_text, ticker_selector = self._extract_symbol_text(page, symbol)
        if ticker_selector:
            selector_debug["ticker"] = ticker_selector
        price_text, price_selector = self._extract_price_text(page)
        if price_selector:
            selector_debug["price"] = price_selector

        latest_price = _maybe_float(price_text)
        symbol_detected = symbol if visible_ticker_text and symbol.upper() in visible_ticker_text.upper() else None

        screenshot_paths, chart_regions_captured, screenshot_warnings = self._capture_artifacts(
            page,
            symbol=symbol,
            timestamp_utc=timestamp_utc,
        )
        warnings.extend(screenshot_warnings)

        fields_extracted: list[str] = []
        if symbol_detected:
            fields_extracted.append("symbol")
        if latest_price is not None:
            fields_extracted.append("latest_visible_price")

        missing_fields: list[str] = []
        if symbol_detected is None:
            missing_fields.append("symbol")
            warnings.append("The requested symbol was not clearly visible after the thinkorswim page interaction.")
        if latest_price is None:
            missing_fields.append("price")
            warnings.append("No visible quote price was extracted from the current thinkorswim page.")
        missing_fields.extend(["1D.bars", "1H.bars", "5m.bars"])
        warnings.append("thinkorswim web extraction currently uses only visible page context from the persistent browser session.")

        ok = symbol_detected is not None
        return BrowserExtractionResult(
            ok=ok,
            source_name=self.source_name,
            page_url_attempted=requested_url,
            requested_url=requested_url,
            symbol_requested=symbol,
            symbol_detected=symbol_detected,
            timestamp_utc=timestamp_utc,
            latest_visible_price=latest_price,
            visible_timeframe=None,
            fields_extracted=fields_extracted,
            missing_fields=missing_fields,
            warnings=warnings,
            errors=[] if ok else ["thinkorswim web did not show the requested symbol clearly enough to analyze."],
            latency_ms=round((perf_counter() - start) * 1000.0, 2),
            extraction_status="partial" if ok else "failed",
            extraction_completeness="partial" if ok else "none",
            trust_classification="browser_partial" if ok else "browser_failed",
            visible_data={"ticker": visible_ticker_text, "price_text": price_text},
            adapter_kind=self.adapter_kind,
            page_title=page_title,
            screenshot_paths=screenshot_paths,
            selector_debug=selector_debug,
            visible_ticker_text=visible_ticker_text,
            chart_regions_captured=chart_regions_captured,
        )


class BrowserSourceManager:
    """Bounded Playwright browser extraction manager with explicit site adapters."""

    def __init__(self, *, settings_path: str | Path | None = None, headless: bool | None = None) -> None:
        self.settings_path = Path(settings_path) if settings_path is not None else None
        self._headless_override = headless
        self._persistent_playwright = None
        self._persistent_context = None
        self._persistent_page = None

    def _browser_settings(self) -> dict[str, Any]:
        settings = load_source_settings(self.settings_path) if self.settings_path is not None else load_source_settings("config/gui_sources.yaml")
        return dict(settings.get("browser", {}))

    def _build_adapters(self) -> dict[str, BrowserSourceAdapter]:
        browser_settings = self._browser_settings()
        tradingview_settings = dict(browser_settings.get("tradingview", {}))
        thinkorswim_settings = dict(browser_settings.get("thinkorswim", {}))
        return {
            "stock_yahoo": YahooFinanceQuoteAdapter(),
            "stock_tradingview": TradingViewChartAdapter(
                chart_url_template=str(tradingview_settings.get("chart_url_template", "") or ""),
                exchange_prefix=str(tradingview_settings.get("exchange_prefix", "") or ""),
                page_load_timeout_ms=_safe_int(tradingview_settings.get("page_load_timeout_ms"), 15000),
                settle_wait_ms=_safe_int(tradingview_settings.get("settle_wait_ms"), 2500),
                persist_screenshots=_safe_bool(browser_settings.get("persist_screenshots"), True),
                screenshot_dir=str(browser_settings.get("screenshot_dir", "out/browser_artifacts") or "out/browser_artifacts"),
            ),
            "stock_thinkorswim": ThinkorswimWebAdapter(
                base_url=str(thinkorswim_settings.get("base_url", "https://trade.thinkorswim.com/") or "https://trade.thinkorswim.com/"),
                page_load_timeout_ms=_safe_int(thinkorswim_settings.get("page_load_timeout_ms"), 20000),
                settle_wait_ms=_safe_int(thinkorswim_settings.get("settle_wait_ms"), 2000),
                persist_screenshots=_safe_bool(browser_settings.get("persist_screenshots"), True),
                screenshot_dir=str(browser_settings.get("screenshot_dir", "out/browser_artifacts") or "out/browser_artifacts"),
            ),
        }

    def _current_provider(self) -> str:
        browser_settings = self._browser_settings()
        provider = str(browser_settings.get("provider", "yahoo") or "yahoo").strip().lower()
        if provider == "thinkorswim":
            return "stock_thinkorswim"
        return "stock_tradingview" if provider == "tradingview" else "stock_yahoo"

    def _headless(self) -> bool:
        if self._headless_override is not None:
            return self._headless_override
        return _safe_bool(self._browser_settings().get("headless"), True)

    def _thinkorswim_settings(self) -> dict[str, Any]:
        return dict(self._browser_settings().get("thinkorswim", {}))

    def start_thinkorswim_browser(self) -> dict[str, Any]:
        settings = self._thinkorswim_settings()
        if not _safe_bool(settings.get("enabled"), True):
            return {"ok": False, "status": "disabled", "message": "thinkorswim web source is disabled in settings."}
        if self._persistent_context is not None and self._persistent_page is not None:
            return {"ok": True, "status": "running", "message": "thinkorswim web browser is already running."}
        try:
            playwright = _create_sync_playwright_context().start()
            profile_dir = Path(str(settings.get("profile_dir", "data/browser_profiles/thinkorswim_web") or "data/browser_profiles/thinkorswim_web"))
            profile_dir.mkdir(parents=True, exist_ok=True)
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
            )
            page = context.pages[0] if context.pages else context.new_page()
            base_url = str(settings.get("base_url", "https://trade.thinkorswim.com/") or "https://trade.thinkorswim.com/")
            page.goto(base_url, wait_until="domcontentloaded", timeout=_safe_int(settings.get("page_load_timeout_ms"), 20000))
            settle_wait_ms = _safe_int(settings.get("settle_wait_ms"), 2000)
            if settle_wait_ms > 0:
                page.wait_for_timeout(settle_wait_ms)
            self._persistent_playwright = playwright
            self._persistent_context = context
            self._persistent_page = page
            return {"ok": True, "status": "running", "message": "thinkorswim web browser started. Log in manually once and keep this window open."}
        except Exception as exc:
            self.stop_thinkorswim_browser()
            return {"ok": False, "status": "failed", "message": _browser_runtime_error_message(exc, phase="launch")}

    def stop_thinkorswim_browser(self) -> dict[str, Any]:
        if self._persistent_context is not None:
            try:
                self._persistent_context.close()
            except Exception:
                pass
        if self._persistent_playwright is not None:
            try:
                self._persistent_playwright.stop()
            except Exception:
                pass
        self._persistent_context = None
        self._persistent_page = None
        self._persistent_playwright = None
        return {"ok": True, "status": "stopped", "message": "thinkorswim web browser stopped."}

    def thinkorswim_browser_status(self) -> dict[str, Any]:
        settings = self._thinkorswim_settings()
        current_url = None
        page_title = None
        if self._persistent_page is not None:
            try:
                current_url = self._persistent_page.url
            except Exception:
                current_url = None
            try:
                page_title = self._persistent_page.title()
            except Exception:
                page_title = None
        return {
            "enabled": _safe_bool(settings.get("enabled"), True),
            "running": self._persistent_context is not None and self._persistent_page is not None,
            "profile_dir": str(settings.get("profile_dir", "data/browser_profiles/thinkorswim_web") or "data/browser_profiles/thinkorswim_web"),
            "base_url": str(settings.get("base_url", "https://trade.thinkorswim.com/") or "https://trade.thinkorswim.com/"),
            "keep_browser_open": _safe_bool(settings.get("keep_browser_open"), True),
            "launch_on_startup": _safe_bool(settings.get("launch_on_startup"), False),
            "current_url": current_url,
            "page_title": page_title,
        }

    def status_payload(self) -> dict[str, Any]:
        try:
            import playwright.sync_api  # noqa: F401

            playwright_available = True
        except Exception:
            playwright_available = False
        browser_settings = self._browser_settings()
        adapters = self._build_adapters()
        tradingview_settings = dict(browser_settings.get("tradingview", {}))
        thinkorswim_settings = self._thinkorswim_settings()
        current_provider = self._current_provider()
        current_adapter = adapters[current_provider]
        return {
            "enabled": True,
            "playwright_available": playwright_available,
            "supported_sources": [
                {
                    "source_name": adapter.source_name,
                    "display_name": adapter.display_name,
                    "page_type": name,
                    "adapter_kind": adapter.adapter_kind,
                }
                for name, adapter in adapters.items()
            ],
            "headless": self._headless(),
            "current_provider": current_provider,
            "current_provider_label": current_adapter.display_name,
            "persist_screenshots": _safe_bool(browser_settings.get("persist_screenshots"), True),
            "screenshot_dir": str(browser_settings.get("screenshot_dir", "out/browser_artifacts") or "out/browser_artifacts"),
            "tradingview": {
                "enabled": _safe_bool(tradingview_settings.get("enabled"), False),
                "chart_url_configured": bool(str(tradingview_settings.get("chart_url_template", "") or "").strip()),
                "exchange_prefix": str(tradingview_settings.get("exchange_prefix", "") or ""),
                "page_load_timeout_ms": _safe_int(tradingview_settings.get("page_load_timeout_ms"), 15000),
                "settle_wait_ms": _safe_int(tradingview_settings.get("settle_wait_ms"), 2500),
            },
            "thinkorswim": {
                "enabled": _safe_bool(thinkorswim_settings.get("enabled"), True),
                "base_url": str(thinkorswim_settings.get("base_url", "https://trade.thinkorswim.com/") or "https://trade.thinkorswim.com/"),
                "profile_dir": str(thinkorswim_settings.get("profile_dir", "data/browser_profiles/thinkorswim_web") or "data/browser_profiles/thinkorswim_web"),
                "page_load_timeout_ms": _safe_int(thinkorswim_settings.get("page_load_timeout_ms"), 20000),
                "settle_wait_ms": _safe_int(thinkorswim_settings.get("settle_wait_ms"), 2000),
                "keep_browser_open": _safe_bool(thinkorswim_settings.get("keep_browser_open"), True),
                "launch_on_startup": _safe_bool(thinkorswim_settings.get("launch_on_startup"), False),
                "running": self._persistent_context is not None and self._persistent_page is not None,
            },
        }

    def extract_stock_quote(self, symbol: str, *, provider: str = "yahoo") -> BrowserExtractionResult:
        adapters = self._build_adapters()
        adapter_key = "stock_tradingview" if provider == "tradingview" else "stock_yahoo"
        return self._extract_with_adapter(symbol, adapters[adapter_key])

    def extract_tradingview_chart(self, symbol: str) -> BrowserExtractionResult:
        adapters = self._build_adapters()
        tradingview_settings = self.status_payload()["tradingview"]
        if not tradingview_settings["enabled"]:
            return BrowserExtractionResult(
                ok=False,
                source_name="tradingview_chart_page",
                page_url_attempted="",
                requested_url="",
                symbol_requested=symbol,
                symbol_detected=None,
                timestamp_utc=None,
                latest_visible_price=None,
                visible_timeframe=None,
                missing_fields=["symbol", "timeframe", "chart_canvas"],
                errors=["TradingView browser source is not configured for this page type yet."],
                extraction_status="failed",
                extraction_completeness="none",
                trust_classification="browser_failed",
                adapter_kind="tradingview",
            )
        return self._extract_with_adapter(symbol, adapters["stock_tradingview"])

    def extract_thinkorswim_symbol(self, symbol: str) -> BrowserExtractionResult:
        adapters = self._build_adapters()
        if self._persistent_page is None:
            return BrowserExtractionResult(
                ok=False,
                source_name="thinkorswim_web",
                page_url_attempted=str(self._thinkorswim_settings().get("base_url", "https://trade.thinkorswim.com/") or "https://trade.thinkorswim.com/"),
                requested_url=str(self._thinkorswim_settings().get("base_url", "https://trade.thinkorswim.com/") or "https://trade.thinkorswim.com/"),
                symbol_requested=symbol,
                symbol_detected=None,
                timestamp_utc=None,
                latest_visible_price=None,
                visible_timeframe=None,
                missing_fields=["symbol", "price"],
                errors=["thinkorswim web browser is not running. Start the persistent browser first."],
                extraction_status="failed",
                extraction_completeness="none",
                trust_classification="browser_failed",
                adapter_kind="thinkorswim",
            )
        return adapters["stock_thinkorswim"].extract(self._persistent_page, symbol=symbol)

    def extract_symbol(self, symbol: str) -> BrowserExtractionResult:
        provider = self._current_provider()
        if provider == "stock_thinkorswim":
            return self.extract_thinkorswim_symbol(symbol)
        if provider == "stock_tradingview":
            return self.extract_tradingview_chart(symbol)
        return self.extract_stock_quote(symbol, provider="yahoo")

    def _extract_with_adapter(self, symbol: str, adapter: BrowserSourceAdapter) -> BrowserExtractionResult:
        attempted_url = adapter.build_url(symbol)
        status = self.status_payload()
        if not status["playwright_available"]:
            return _browser_runtime_failure_result(
                adapter,
                symbol=symbol,
                attempted_url=attempted_url,
                error_text="Browser extraction is not available because Playwright is not installed.",
            )
        try:
            playwright_context = _create_sync_playwright_context()
        except Exception as exc:
            return _browser_runtime_failure_result(
                adapter,
                symbol=symbol,
                attempted_url=attempted_url,
                error_text=_browser_runtime_error_message(exc, phase="startup"),
            )

        browser = None
        try:
            with playwright_context as playwright:
                try:
                    browser = playwright.chromium.launch(headless=self._headless())
                except Exception as exc:
                    return _browser_runtime_failure_result(
                        adapter,
                        symbol=symbol,
                        attempted_url=attempted_url,
                        error_text=_browser_runtime_error_message(exc, phase="launch"),
                    )
                try:
                    page = browser.new_page()
                except Exception as exc:
                    return _browser_runtime_failure_result(
                        adapter,
                        symbol=symbol,
                        attempted_url=attempted_url,
                        error_text=_browser_runtime_error_message(exc, phase="page"),
                    )
                return adapter.extract(page, symbol=symbol)
        except Exception as exc:
            return _browser_runtime_failure_result(
                adapter,
                symbol=symbol,
                attempted_url=attempted_url,
                error_text=_browser_runtime_error_message(exc, phase="startup"),
            )
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
