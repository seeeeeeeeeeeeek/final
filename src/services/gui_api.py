from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.analysis.source_manager import SourceManager
from src.analysis.thesis_engine import build_thesis
from src.scanner.models import ExplanationPayload, ScanConfig, ScanStatus, SymbolContext, build_empty_scan_record
from src.scanner.runner import ScanRunner
from src.services.config_loader import (
    load_optional_yaml,
    load_scan_config,
    load_source_settings,
    reset_yaml,
    save_source_settings,
    save_yaml,
)
from src.services.browser_source import BrowserExtractionResult, BrowserSourceManager
from src.services.gui_html import build_index_html
from src.services.gui_responses import build_detail_payload, build_replay_result_payload
from src.services.gui_state import GUIState
from src.services.logging import SignalLogger
from src.services.market_data import TwelveDataMarketDataProvider, YahooFinanceMarketDataProvider
from src.services.ocr_screen import OCRScreenService
from src.services.webhook_models import TradingViewWebhookPayload
from src.services.webhook_server import WebhookProcessor
from src.utils.validation import validate_scan_record

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")
_FRESH_WEBHOOK_MAX_AGE_SECONDS = 15 * 60
_SOURCE_PROGRAM_MODE = "thinkorswim_web"
_SOURCE_PROGRAM_LABEL = "thinkorswim web"
_SOURCE_PROGRAM_MESSAGE = "Use your real logged-in thinkorswim web tab with the helper script running inside it. Request a ticker in stocknogs, let the tab switch there, and then read the selectors back into the app."


def _manual_session_payload_to_browser_result(payload: dict[str, Any]) -> BrowserExtractionResult:
    symbol = str(payload.get("symbol", "") or "").strip().upper()
    latest_price = _float_or_none(payload.get("latest_visible_price"))
    visible_timeframe = str(payload.get("visible_timeframe", "") or "").strip() or None
    page_url = str(payload.get("page_url", "https://trade.thinkorswim.com/") or "https://trade.thinkorswim.com/").strip()
    page_title = str(payload.get("page_title", "") or "").strip() or None
    visible_ticker_text = str(payload.get("visible_ticker_text", symbol) or symbol).strip() or None
    selector_debug = dict(payload.get("selector_debug", {}))
    screenshot_paths = dict(payload.get("screenshot_paths", {}))
    chart_regions_captured = list(payload.get("chart_regions_captured", []))
    timestamp_utc = _utc_now_iso()
    warnings = list(payload.get("warnings", []))
    warnings.append("This result came from selector-based extraction on a manually opened thinkorswim web session.")
    missing_fields: list[str] = []
    fields_extracted: list[str] = []
    if symbol:
        fields_extracted.append("symbol")
    else:
        missing_fields.append("symbol")
    if latest_price is not None:
        fields_extracted.append("latest_visible_price")
    else:
        missing_fields.append("price")
    if visible_timeframe:
        fields_extracted.append("timeframe")
    missing_fields.extend(["1D.bars", "1H.bars", "5m.bars"])
    ok = bool(symbol)
    return BrowserExtractionResult(
        ok=ok,
        source_name="thinkorswim_manual_session",
        page_url_attempted=page_url,
        requested_url=page_url,
        symbol_requested=symbol,
        symbol_detected=symbol or None,
        timestamp_utc=timestamp_utc,
        latest_visible_price=latest_price,
        visible_timeframe=visible_timeframe,
        fields_extracted=fields_extracted,
        missing_fields=missing_fields,
        warnings=warnings,
        errors=[] if ok else ["Manual thinkorswim session payload did not include a usable symbol."],
        extraction_status="partial" if ok else "failed",
        extraction_completeness="partial" if ok else "none",
        trust_classification="browser_partial" if ok else "browser_failed",
        visible_data=dict(payload.get("visible_data", {})),
        adapter_kind="thinkorswim_manual",
        page_title=page_title,
        screenshot_paths=screenshot_paths,
        selector_debug=selector_debug,
        visible_ticker_text=visible_ticker_text,
        visible_timeframe_text=visible_timeframe,
        chart_regions_captured=chart_regions_captured,
    )


def _failed_run_state(source_mode: str, failure_reason: str) -> dict[str, Any]:
    return {
        "stages": ["Preparing analysis request", "Resolving source mode", "Failed"],
        "source_mode_requested": source_mode,
        "source_used": None,
        "fallback_chain": [],
        "timeframe_coverage": {},
        "warnings": [],
        "failure_reason": failure_reason,
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bundle_coverage(bundle: Any) -> dict[str, bool]:
    return {
        "1D": bool(getattr(bundle, "daily", None) and bundle.daily.bars),
        "1H": bool(getattr(bundle, "hourly", None) and bundle.hourly.bars),
        "5m": bool(getattr(bundle, "intraday_5m", None) and bundle.intraday_5m.bars),
        "1m": False,
    }


def _single_bundle_provider(source_name: str, bundle: Any, fallback_chain: list[str]) -> Any:
    return type(
        "SingleBundleProvider",
        (),
        {
            "source_name": source_name,
            "fallback_chain": list(fallback_chain),
            "get_symbol_data": lambda self, symbol_context: bundle,
        },
    )()


def _make_provider(source_mode: str) -> Any:
    if source_mode == "yahoo":
        provider = YahooFinanceMarketDataProvider()
        provider.source_name = "yahoo"
        return provider
    if source_mode == "twelvedata":
        provider = TwelveDataMarketDataProvider()
        provider.source_name = "twelvedata"
        return provider
    raise ValueError(f"No live provider for source_mode={source_mode}")


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    trimmed = str(value).strip()
    if len(trimmed) <= 4:
        return "*" * len(trimmed)
    return ("*" * max(0, len(trimmed) - 4)) + trimmed[-4:]


def _float_or_none(value: Any) -> float | None:
    if value in ("", None):
        return None
    return float(value)


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {key: _drop_none(item) for key, item in value.items()}
        return {key: item for key, item in cleaned.items() if item is not None and item != {}}
    return value


def _build_override_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    editable = dict(payload.get("editable_settings", {}))
    public_webhook_url = payload.get("public_webhook_url")
    override = {
        "defaults": {
            "trend_filter": {
                "minimum_trend_strength_score": _float_or_none(
                    editable.get("trend_filter", {}).get("minimum_trend_strength_score")
                ),
                "minimum_slope_pct": _float_or_none(editable.get("trend_filter", {}).get("minimum_slope_pct")),
            },
            "compression": {
                "maximum_pullback_depth_pct": _float_or_none(
                    editable.get("compression", {}).get("maximum_pullback_depth_pct")
                ),
                "minimum_range_contraction_pct": _float_or_none(
                    editable.get("compression", {}).get("minimum_range_contraction_pct")
                ),
                "minimum_volatility_contraction_pct": _float_or_none(
                    editable.get("compression", {}).get("minimum_volatility_contraction_pct")
                ),
            },
            "breakout_trigger": {
                "breakout_buffer_pct": _float_or_none(editable.get("breakout_trigger", {}).get("breakout_buffer_pct")),
                "minimum_breakout_range_vs_base_avg": _float_or_none(
                    editable.get("breakout_trigger", {}).get("minimum_breakout_range_vs_base_avg")
                ),
                "minimum_relative_volume": _float_or_none(
                    editable.get("breakout_trigger", {}).get("minimum_relative_volume")
                ),
            },
            "trap_risk": {
                "maximum_distance_from_trend_ref_pct": _float_or_none(
                    editable.get("trap_risk", {}).get("maximum_distance_from_trend_ref_pct")
                ),
                "maximum_rejection_wick_pct": _float_or_none(
                    editable.get("trap_risk", {}).get("maximum_rejection_wick_pct")
                ),
                "minimum_overhead_clearance_pct": _float_or_none(
                    editable.get("trap_risk", {}).get("minimum_overhead_clearance_pct")
                ),
            },
        },
        "scoring": {
            "scoring": {
                "weights": {
                    "trend_alignment": _float_or_none(editable.get("scoring", {}).get("trend_alignment")),
                    "squeeze_quality": _float_or_none(editable.get("scoring", {}).get("squeeze_quality")),
                    "breakout_impulse": _float_or_none(editable.get("scoring", {}).get("breakout_impulse")),
                    "path_quality": _float_or_none(editable.get("scoring", {}).get("path_quality")),
                    "trap_risk_penalty": _float_or_none(editable.get("scoring", {}).get("trap_risk_penalty")),
                }
            }
        },
    }
    return _drop_none(override), str(public_webhook_url).strip() or None


def _build_source_settings_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source_settings = dict(payload.get("source_settings", {}))
    preferences = dict(source_settings.get("source_preferences", {}))
    browser = dict(source_settings.get("browser", {}))
    tradingview = dict(browser.get("tradingview", {}))
    thinkorswim = dict(browser.get("thinkorswim", {}))
    return {
        "twelvedata": {"api_key": ""},
        "source_preferences": {
            "default_mode": str(preferences.get("default_mode", _SOURCE_PROGRAM_MODE) or _SOURCE_PROGRAM_MODE).strip().lower(),
            "webhook_fallback_enabled": False,
            "browser_fallback_enabled": True,
            "ocr_fallback_enabled": False,
        },
        "browser": {
            "provider": "thinkorswim",
            "headless": False,
            "persist_screenshots": bool(browser.get("persist_screenshots", True)),
            "screenshot_dir": str(browser.get("screenshot_dir", "out/browser_artifacts") or "out/browser_artifacts"),
            "thinkorswim": {
                "enabled": bool(thinkorswim.get("enabled", True)),
                "base_url": str(thinkorswim.get("base_url", "https://trade.thinkorswim.com/") or "https://trade.thinkorswim.com/").strip(),
                "profile_dir": str(thinkorswim.get("profile_dir", "data/browser_profiles/thinkorswim_web") or "data/browser_profiles/thinkorswim_web").strip(),
                "page_load_timeout_ms": int(thinkorswim.get("page_load_timeout_ms", 20000) or 20000),
                "settle_wait_ms": int(thinkorswim.get("settle_wait_ms", 2000) or 2000),
                "keep_browser_open": bool(thinkorswim.get("keep_browser_open", True)),
                "launch_on_startup": bool(thinkorswim.get("launch_on_startup", False)),
            },
            "tradingview": {
                "enabled": False,
                "chart_url_template": str(tradingview.get("chart_url_template", "") or "").strip(),
                "exchange_prefix": str(tradingview.get("exchange_prefix", "") or "").strip(),
                "page_load_timeout_ms": int(tradingview.get("page_load_timeout_ms", 15000) or 15000),
                "settle_wait_ms": int(tradingview.get("settle_wait_ms", 2500) or 2500),
            },
        },
    }


@dataclass(slots=True)
class GUIApplication:
    processor: WebhookProcessor
    state: GUIState
    browser_service: BrowserSourceManager
    ocr_service: OCRScreenService
    host: str
    port: int
    config_dir: Path
    override_path: Path | None = None
    demo_override_path: Path | None = None
    source_settings_path: Path | None = None
    manual_session_target_symbol: str | None = None
    manual_session_command_id: int = 0
    manual_session_last_seen_at: str | None = None
    manual_session_last_event: str | None = None
    manual_session_last_error: str | None = None
    manual_session_last_symbol: str | None = None

    def reload_config(self) -> ScanConfig:
        self.processor.config = load_scan_config(self.config_dir, override_path=self.override_path)
        return self.processor.config

    def source_settings(self) -> dict[str, Any]:
        if self.source_settings_path is None:
            return load_source_settings(self.config_dir / "gui_sources.yaml")
        return load_source_settings(self.source_settings_path)

    def _twelvedata_api_key(self) -> str | None:
        source_settings = self.source_settings()
        api_key = str(source_settings.get("twelvedata", {}).get("api_key", "") or "").strip()
        return api_key or None

    def _source_preferences(self) -> dict[str, Any]:
        return dict(self.source_settings().get("source_preferences", {}))

    def _build_browser_record(
        self,
        symbol: str,
        *,
        requested_source_mode: str = "browser",
        fallback_chain: list[str] | None = None,
        inherited_warnings: list[str] | None = None,
        precomputed_result: BrowserExtractionResult | None = None,
    ) -> tuple[int, dict[str, Any]]:
        fallback_chain = list(fallback_chain or [])
        inherited_warnings = list(inherited_warnings or [])
        if precomputed_result is None:
            self.state.advance_run("Preparing browser extraction", mode_kind="browser")
            self.state.advance_run("Opening supported page", mode_kind="browser")
            self.state.advance_run("Waiting for page content", mode_kind="browser")
            self.state.advance_run("Searching symbol", mode_kind="browser")
            self.state.advance_run("Extracting visible data", mode_kind="browser")
            result = self.browser_service.extract_symbol(symbol)
        else:
            self.state.advance_run("Normalizing manual session data", mode_kind="manual_session")
            result = precomputed_result
        warnings = list(inherited_warnings) + list(result.warnings)
        if result.errors:
            warnings.extend(result.errors)
        if not result.ok:
            reason = result.errors[0] if result.errors else "No supported browser adapter could handle this request."
            self.state.fail_run(
                reason,
                source_used=result.source_name,
                source_class="browser_failed",
                fallback_chain=fallback_chain,
                warnings=warnings,
                mode_kind="browser",
            )
            return 400, {
                "ok": False,
                "error": reason,
                "browser_result": {
                    "source_name": result.source_name,
                    "page_url_attempted": result.page_url_attempted,
                "fields_extracted": result.fields_extracted,
                "missing_fields": result.missing_fields,
                "warnings": result.warnings,
                "errors": result.errors,
                "selector_debug": result.selector_debug,
                "screenshot_paths": result.screenshot_paths,
                },
                "run_state": self.state.run_state_payload(),
            }

        self.state.advance_run(
            "Normalizing extracted values",
            source_used=result.source_name,
            source_class="browser_partial" if result.extraction_completeness == "partial" else "browser_fresh",
            fallback_chain=fallback_chain,
            warnings=warnings,
            mode_kind="browser",
        )
        source_manager = SourceManager()
        snapshot_result = source_manager.from_browser(result)
        record = build_empty_scan_record(
            symbol,
            scan_id=f"browser-{symbol}-{result.timestamp_utc or _utc_now_iso()}",
            config_version=self.processor.config.defaults.get("version", "v1-defaults"),
            status=ScanStatus.SKIPPED,
        )
        record.timestamp_utc = result.timestamp_utc or _utc_now_iso()
        record.snapshot = snapshot_result.snapshot
        record.metrics.update(
            {
                "browser_source_name": result.source_name,
                "browser_adapter_kind": result.adapter_kind,
                "browser_page_url_attempted": result.page_url_attempted,
                "browser_requested_url": result.requested_url,
                "browser_page_title": result.page_title,
                "visible_quote_price": result.latest_visible_price,
                "browser_visible_ticker_text": result.visible_ticker_text,
                "visible_timeframe": result.visible_timeframe,
                "browser_chart_canvas_present": result.chart_canvas_present,
                "browser_chart_canvas_width": result.chart_canvas_width,
                "browser_chart_canvas_height": result.chart_canvas_height,
                "browser_price_axis_present": result.price_axis_present,
                "browser_price_axis_canvas_width": result.price_axis_canvas_width,
                "browser_price_axis_canvas_height": result.price_axis_canvas_height,
                "browser_time_axis_present": result.time_axis_present,
                "browser_time_axis_canvas_width": result.time_axis_canvas_width,
                "browser_time_axis_canvas_height": result.time_axis_canvas_height,
                "browser_screenshot_count": len(result.screenshot_paths),
                "fields_extracted_count": len(result.fields_extracted),
                "extraction_completeness": result.extraction_completeness,
            }
        )
        if result.latest_visible_price is not None:
            record.levels.breakout_price = result.latest_visible_price
        summary = "Browser data found current price, but higher timeframe context is missing."
        reasons = [
            "Browser extraction succeeded for visible quote data only.",
            f"Browser source opened {result.source_name.replace('_', ' ')}.",
            "Higher timeframe bars were not available from the visible page.",
        ]
        if result.adapter_kind == "tradingview":
            summary = "TradingView browser extraction found visible chart context, but structured higher timeframe data is still missing."
            reasons = [
                "TradingView browser extraction captured visible ticker, timeframe, and chart canvas data only.",
                "The result stays browser-extracted partial context, not structured OHLCV.",
                "Higher timeframe bars and hidden indicator values were not inferred from canvas visuals.",
            ]
        record.explanations = ExplanationPayload(
            summary=summary,
            reasons=reasons,
            skip_reason="Not enough structured timeframe context was available from the browser page.",
        )
        record.debug.data_quality_warnings.extend(result.warnings)
        record.thesis, record.diagnostics = build_thesis(record)
        record.thesis.explanation_summary = record.explanations.summary
        record.thesis.explanation_reasons = list(record.explanations.reasons)
        record.diagnostics.source = snapshot_result.diagnostics
        record.diagnostics.source["requested_source_mode"] = requested_source_mode
        record.diagnostics.source["mode_kind"] = "browser"
        record.diagnostics.source["source_class"] = result.trust_classification
        record.diagnostics.source["source_class_label"] = self.state._source_class_label(result.trust_classification)
        record.diagnostics.source["is_live"] = False
        record.diagnostics.source["freshness_state"] = "fresh"
        record.diagnostics.source["fallback_chain"] = list(fallback_chain)
        record.diagnostics.system["warnings"] = list(record.debug.data_quality_warnings)
        validate_scan_record(record)
        self.processor.signal_logger.log_signal(record)
        self.state.advance_run(
            "Building analysis record",
            source_used=result.source_name,
            source_class=result.trust_classification,
            fallback_chain=fallback_chain,
            warnings=warnings,
            mode_kind="browser",
        )
        raw_payload = {
            "_ingest_mode": "browser",
            "_requested_source_mode": requested_source_mode,
            "_symbol": symbol,
            "browser_source_name": result.source_name,
            "page_url_attempted": result.page_url_attempted,
            "browser_adapter_kind": result.adapter_kind,
            "selector_debug": result.selector_debug,
            "screenshot_paths": result.screenshot_paths,
        }
        return self._store_record_response(record, raw_payload, source_mode_requested=requested_source_mode)

    def _make_live_provider(self, source_mode: str) -> Any:
        if source_mode == "twelvedata":
            provider = TwelveDataMarketDataProvider(api_key=self._twelvedata_api_key())
            provider.source_name = "twelvedata"
            return provider
        return _make_provider(source_mode)

    def _masked_source_settings_payload(self) -> dict[str, Any]:
        source_settings = self.source_settings()
        source_preferences = dict(source_settings.get("source_preferences", {}))
        api_key = str(source_settings.get("twelvedata", {}).get("api_key", "") or "").strip()
        browser = dict(source_settings.get("browser", {}))
        tradingview = dict(browser.get("tradingview", {}))
        return {
            "twelvedata": {
                "configured": False,
                "masked_api_key": None,
            },
            "source_preferences": {
                "default_mode": source_preferences.get("default_mode", _SOURCE_PROGRAM_MODE),
                "webhook_fallback_enabled": False,
                "browser_fallback_enabled": True,
                "ocr_fallback_enabled": False,
                "auto_priority": [
                    "thinkorswim web persistent browser",
                ],
            },
            "browser": {
                "provider": "thinkorswim",
                "headless": False,
                "persist_screenshots": bool(browser.get("persist_screenshots", True)),
                "screenshot_dir": str(browser.get("screenshot_dir", "out/browser_artifacts") or "out/browser_artifacts"),
                "thinkorswim": {
                    **self.browser_service.thinkorswim_browser_status(),
                    "page_load_timeout_ms": int(dict(browser.get("thinkorswim", {})).get("page_load_timeout_ms", 20000) or 20000),
                    "settle_wait_ms": int(dict(browser.get("thinkorswim", {})).get("settle_wait_ms", 2000) or 2000),
                },
                "tradingview": {
                    "enabled": bool(tradingview.get("enabled", False)),
                    "chart_url_configured": bool(str(tradingview.get("chart_url_template", "") or "").strip()),
                    "exchange_prefix": str(tradingview.get("exchange_prefix", "") or ""),
                    "page_load_timeout_ms": int(tradingview.get("page_load_timeout_ms", 15000) or 15000),
                    "settle_wait_ms": int(tradingview.get("settle_wait_ms", 2500) or 2500),
                },
            },
            "program": {
                "active": True,
                "mode": _SOURCE_PROGRAM_MODE,
                "message": _SOURCE_PROGRAM_MESSAGE,
                "archived_integrations": ["twelvedata", "yahoo", "tradingview_webhook", "ocr"],
            },
        }

    def test_twelvedata_connection(self, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        payload = payload or {}
        incoming_api_key = str(payload.get("api_key", "") or "").strip()
        api_key = incoming_api_key or self._twelvedata_api_key()
        if not api_key:
            return 400, {
                "ok": False,
                "status": "not_configured",
                "message": "No Twelve Data API key is saved yet.",
            }

        provider = TwelveDataMarketDataProvider(
            api_key=api_key,
            daily_outputsize=2,
            hourly_outputsize=2,
            intraday_outputsize=2,
        )
        bundle = provider.get_symbol_data(SymbolContext(symbol="SPY"))
        warnings = list(bundle.warnings)
        coverage = _bundle_coverage(bundle)
        if all(coverage.get(name) for name in ("1D", "1H", "5m")):
            return 200, {
                "ok": True,
                "status": "connected",
                "message": "Twelve Data connection is working.",
                "coverage": coverage,
                "warnings": warnings,
            }

        warning_text = " ".join(warnings).lower()
        if "api key" in warning_text or "invalid api key" in warning_text:
            return 400, {
                "ok": False,
                "status": "invalid_key",
                "message": "Twelve Data rejected the saved API key.",
                "coverage": coverage,
                "warnings": warnings,
            }
        if any("failed to fetch" in warning.lower() for warning in warnings):
            return 400, {
                "ok": False,
                "status": "network_error",
                "message": "The app could not reach Twelve Data right now.",
                "coverage": coverage,
                "warnings": warnings,
            }
        return 400, {
            "ok": False,
            "status": "provider_unavailable",
            "message": "Twelve Data did not return enough data to validate the connection.",
            "coverage": coverage,
            "warnings": warnings,
        }

    def _store_record_response(
        self,
        record: Any,
        raw_payload: dict[str, Any],
        *,
        source_mode_requested: str,
    ) -> tuple[int, dict[str, Any]]:
        self.state.add_record(record, raw_payload)
        stored = self.state.get_record(record.scan_id)
        if stored is not None:
            self.state.complete_run(stored, source_mode=source_mode_requested)
        replay_result = build_replay_result_payload(record, self.state)
        return 200, {
            "ok": True,
            "status": record.status.value,
            "record": self.state.record_summary(stored),
            "result": replay_result,
            "run_state": self.state.run_state_payload(),
        }

    def analyze_manual_session(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        symbol = str(payload.get("symbol", "") or "").strip().upper()
        self.state.start_run(symbol=symbol or "", source_mode=_SOURCE_PROGRAM_MODE)
        self.state.advance_run("Reading manual thinkorswim session payload", mode_kind="manual_session")
        result = _manual_session_payload_to_browser_result(payload)
        if not result.ok:
            reason = result.errors[0] if result.errors else "Manual session payload was incomplete."
            self.state.fail_run(
                reason,
                source_used=result.source_name,
                source_class="browser_failed",
                warnings=list(result.warnings),
                mode_kind="manual_session",
            )
            return 400, {"ok": False, "error": reason, "run_state": self.state.run_state_payload()}
        return self._build_browser_record(
            result.symbol_detected or result.symbol_requested,
            requested_source_mode=_SOURCE_PROGRAM_MODE,
            fallback_chain=[],
            inherited_warnings=[],
            precomputed_result=result,
        )

    def queue_manual_session_command(self, symbol: str) -> tuple[int, dict[str, Any]]:
        self.manual_session_target_symbol = symbol
        self.manual_session_command_id += 1
        self.manual_session_last_symbol = symbol
        self.manual_session_last_event = f"Queued symbol switch for {symbol}."
        self.manual_session_last_error = None
        self.state.advance_run(
            "Waiting for thinkorswim helper to switch the live tab",
            source_used="thinkorswim_manual_session",
            source_class="browser_partial",
            mode_kind="manual_session",
        )
        return 200, {
            "ok": True,
            "status": "queued",
            "message": f"Queued {symbol} for the manual thinkorswim helper.",
            "command_id": self.manual_session_command_id,
            "symbol": symbol,
            "run_state": self.state.run_state_payload(),
        }

    def next_manual_session_command(self) -> dict[str, Any]:
        self.manual_session_last_seen_at = _utc_now_iso()
        if not self.manual_session_target_symbol:
            return {"ok": True, "status": "idle", "command": None}
        return {
            "ok": True,
            "status": "queued",
            "command": {
                "id": self.manual_session_command_id,
                "symbol": self.manual_session_target_symbol,
                "action": "switch_symbol",
            },
        }

    def report_manual_session_payload(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.manual_session_last_seen_at = _utc_now_iso()
        self.manual_session_last_event = "Helper reported selector data back to stocknogs."
        self.manual_session_last_error = None
        status_code, response = self.analyze_manual_session(payload)
        if status_code == 200:
            self.manual_session_target_symbol = None
        return status_code, response

    def report_manual_session_debug(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        event = str(payload.get("event", "") or "").strip() or "helper_event"
        symbol = str(payload.get("symbol", "") or "").strip().upper() or None
        message = str(payload.get("message", "") or "").strip() or event
        error = str(payload.get("error", "") or "").strip() or None
        self.manual_session_last_seen_at = _utc_now_iso()
        self.manual_session_last_event = message
        self.manual_session_last_error = error
        if symbol:
            self.manual_session_last_symbol = symbol
        if error:
            warnings = list(self.state.run_state_payload().get("warnings", []))
            warnings.append(f"Helper error: {error}")
            self.state.advance_run(
                "Helper reported an in-tab error",
                source_used="thinkorswim_manual_session",
                source_class="browser_partial",
                warnings=warnings,
                mode_kind="manual_session",
            )
        elif event == "switch_started" and symbol:
            self.state.advance_run(
                f"Helper is switching the live thinkorswim tab to {symbol}",
                source_used="thinkorswim_manual_session",
                source_class="browser_partial",
                mode_kind="manual_session",
            )
        elif event == "switch_finished" and symbol:
            self.state.advance_run(
                f"Helper switched the live thinkorswim tab to {symbol} and is collecting selectors",
                source_used="thinkorswim_manual_session",
                source_class="browser_partial",
                mode_kind="manual_session",
            )
        return 200, {"ok": True, "helper_status": self.manual_session_status()}

    def manual_session_status(self) -> dict[str, Any]:
        return {
            "pending_symbol": self.manual_session_target_symbol,
            "command_id": self.manual_session_command_id,
            "last_seen_at": self.manual_session_last_seen_at,
            "last_event": self.manual_session_last_event,
            "last_error": self.manual_session_last_error,
            "last_symbol": self.manual_session_last_symbol,
            "helper_running": bool(self.manual_session_last_seen_at),
        }

    def process_payload(
        self,
        payload_dict: dict[str, Any],
        *,
        ingest_mode: str,
        source_mode_requested: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            payload = TradingViewWebhookPayload.from_dict(payload_dict)
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}

        record = self.processor.build_record(
            payload,
            ingest_mode=ingest_mode,
            requested_source_mode=source_mode_requested,
        )
        raw_payload = {
            **payload_dict,
            "_ingest_mode": ingest_mode,
            "_requested_source_mode": source_mode_requested or ingest_mode,
        }
        return self._store_record_response(record, raw_payload, source_mode_requested=source_mode_requested or ingest_mode)

    def _run_live_scan(self, *, symbol: str, source_mode: str) -> tuple[int, dict[str, Any]]:
        self.state.advance_run("Resolving source mode", mode_kind="live")
        symbol_context = SymbolContext(symbol=symbol)

        if source_mode == "ocr":
            self.state.advance_run("Preparing screen read", mode_kind="ocr")
            result = self.ocr_service.analyze(symbol)
            warnings = list(result.warnings)
            if result.capture_source:
                warnings.insert(0, f"Capture source: {result.capture_source}")
            reason = result.reason or "Screen-read fallback could not analyze this symbol."
            self.state.fail_run(reason, source_class="unavailable", warnings=warnings, mode_kind="ocr")
            return 400, {
                "ok": False,
                "error": reason,
                "ocr_status": self.ocr_service.status_payload(),
                "ocr_result": {
                    "extracted": result.extracted,
                    "missing_fields": result.missing_fields,
                    "warnings": result.warnings,
                    "capture_source": result.capture_source,
                    "engine_available": result.engine_available,
                },
                "run_state": self.state.run_state_payload(),
            }

        if source_mode == "browser":
            return self._build_browser_record(symbol, requested_source_mode=source_mode)

        if source_mode == "webhook":
            self.state.advance_run("Waiting for webhook payload", mode_kind="webhook")
            stored = self.state.get_latest_record_for_symbol(
                symbol,
                ingest_mode="webhook",
                fresh_within_seconds=_FRESH_WEBHOOK_MAX_AGE_SECONDS,
            )
            if stored is None:
                reason = "No fresh webhook payload available for requested symbol."
                self.state.fail_run(reason, source_class="unavailable", mode_kind="webhook")
                return 400, {"ok": False, "error": reason, "run_state": self.state.run_state_payload()}
            self.state.complete_run(stored, source_mode=source_mode)
            return 200, {
                "ok": True,
                "status": stored.record.status.value,
                "record": self.state.record_summary(stored),
                "result": build_replay_result_payload(stored.record, self.state),
                "run_state": self.state.run_state_payload(),
                "reused_existing_record": True,
            }

        provider_name: str
        fallback_chain: list[str] = []
        warnings: list[str] = []
        coverage: dict[str, bool] = {}
        bundle = None
        source_preferences = self._source_preferences()

        if source_mode == "twelvedata":
            self.state.advance_run("Checking Twelve Data", mode_kind="live")
            provider_name = "twelvedata"
            provider = self._make_live_provider(provider_name)
            bundle = provider.get_symbol_data(symbol_context)
            warnings = list(bundle.warnings)
            coverage = _bundle_coverage(bundle)
            self.state.advance_run(
                "Fetching live bars",
                source_used=provider_name,
                coverage=coverage,
                warnings=warnings,
                mode_kind="live",
            )
            if not all(coverage[key] for key in ("1D", "1H", "5m")):
                reason = (
                    "Twelve Data key missing."
                    if any("API key" in warning for warning in warnings)
                    else "Live source returned incomplete timeframe data."
                )
                self.state.fail_run(
                    reason,
                    source_used=provider_name,
                    source_class="unavailable",
                    warnings=warnings,
                    coverage=coverage,
                    mode_kind="live",
                )
                return 400, {"ok": False, "error": reason, "run_state": self.state.run_state_payload()}
        else:
            self.state.advance_run("Checking Twelve Data", mode_kind="live")
            primary_provider = self._make_live_provider("twelvedata")
            primary_bundle = primary_provider.get_symbol_data(symbol_context)
            warnings.extend(primary_bundle.warnings)
            coverage = _bundle_coverage(primary_bundle)
            if all(coverage[key] for key in ("1D", "1H", "5m")):
                provider_name = "twelvedata"
                bundle = primary_bundle
            else:
                fallback_chain.append("twelvedata")
                self.state.advance_run(
                    "Checking Yahoo fallback",
                    source_used="twelvedata",
                    fallback_chain=fallback_chain,
                    coverage=coverage,
                    warnings=warnings,
                    mode_kind="live",
                )
                yahoo_provider = YahooFinanceMarketDataProvider()
                yahoo_provider.source_name = "yahoo"
                yahoo_bundle = yahoo_provider.get_symbol_data(symbol_context)
                warnings.extend(yahoo_bundle.warnings)
                yahoo_coverage = _bundle_coverage(yahoo_bundle)
                if all(yahoo_coverage[key] for key in ("1D", "1H", "5m")):
                    provider_name = "yahoo"
                    bundle = yahoo_bundle
                    coverage = yahoo_coverage
                else:
                    fallback_chain.append("yahoo")
                    stored = None
                    if source_preferences.get("webhook_fallback_enabled", True):
                        self.state.advance_run(
                            "Waiting for webhook payload",
                            source_used="yahoo",
                            fallback_chain=fallback_chain,
                            coverage=yahoo_coverage,
                            warnings=warnings,
                            mode_kind="live",
                        )
                        stored = self.state.get_latest_record_for_symbol(
                            symbol,
                            ingest_mode="webhook",
                            fresh_within_seconds=_FRESH_WEBHOOK_MAX_AGE_SECONDS,
                        )
                    if stored is not None:
                        self.state.complete_run(stored, source_mode=source_mode)
                        return 200, {
                            "ok": True,
                            "status": stored.record.status.value,
                            "record": self.state.record_summary(stored),
                            "result": build_replay_result_payload(stored.record, self.state),
                            "run_state": self.state.run_state_payload(),
                            "reused_existing_record": True,
                        }

                    if source_preferences.get("browser_fallback_enabled", True):
                        fallback_chain.append("browser")
                        browser_status = self.browser_service.status_payload()
                        if browser_status.get("playwright_available"):
                            return self._build_browser_record(
                                symbol,
                                requested_source_mode=source_mode,
                                fallback_chain=fallback_chain,
                                inherited_warnings=warnings,
                            )
                        warnings.append("Browser fallback is enabled but Playwright is not installed.")

                    ocr_status = self.ocr_service.status_payload()
                    ocr_result = None
                    if source_preferences.get("ocr_fallback_enabled", True):
                        self.state.advance_run(
                            "Checking screen-read fallback",
                            source_used="webhook_unavailable",
                            fallback_chain=fallback_chain,
                            coverage=yahoo_coverage,
                            warnings=warnings,
                            mode_kind="live",
                        )
                    if source_preferences.get("ocr_fallback_enabled", True) and ocr_status["configured"]:
                        fallback_chain.append("ocr")
                        ocr_result = self.ocr_service.analyze(symbol)
                        warnings.extend(ocr_result.warnings)
                        if ocr_result.capture_source:
                            warnings.append(f"OCR capture source: {ocr_result.capture_source}")
                    elif source_preferences.get("ocr_fallback_enabled", True) and ocr_status["enabled"]:
                        warnings.append("Screen-read fallback is enabled but not configured yet.")
                    elif not source_preferences.get("webhook_fallback_enabled", True):
                        warnings.append("TradingView webhook fallback is disabled in source settings.")
                    elif not source_preferences.get("ocr_fallback_enabled", True):
                        warnings.append("Screen-read fallback is disabled in source settings.")

                    reason = "No supported source could produce usable data."
                    if ocr_result is not None and ocr_result.reason:
                        reason = ocr_result.reason
                    self.state.fail_run(
                        reason,
                        source_used="ocr_unavailable" if ocr_status["enabled"] else "webhook_unavailable",
                        source_class="unavailable",
                        fallback_chain=fallback_chain,
                        warnings=warnings,
                        coverage=yahoo_coverage,
                        mode_kind="live",
                    )
                    return 400, {"ok": False, "error": reason, "run_state": self.state.run_state_payload()}

        self.state.advance_run(
            "Building normalized snapshot",
            source_used=provider_name,
            fallback_chain=fallback_chain,
            coverage=coverage,
            warnings=warnings,
            mode_kind="live",
        )
        self.state.advance_run(
            "Running thesis engine",
            source_used=provider_name,
            fallback_chain=fallback_chain,
            coverage=coverage,
            warnings=warnings,
            mode_kind="live",
        )
        self.state.advance_run(
            "Scoring setup",
            source_used=provider_name,
            fallback_chain=fallback_chain,
            coverage=coverage,
            warnings=warnings,
            mode_kind="live",
        )
        provider = _single_bundle_provider(provider_name, bundle, fallback_chain)
        runner = ScanRunner(
            config=self.processor.config,
            market_data_provider=provider,
            signal_logger=self.processor.signal_logger,
        )
        record = runner.run_symbol(symbol_context, requested_source_mode=source_mode, mode_kind="live")
        self.state.advance_run(
            "Preparing display result",
            source_used=provider_name,
            fallback_chain=fallback_chain,
            coverage=coverage,
            warnings=warnings,
            mode_kind="live",
        )
        raw_payload = {
            "_ingest_mode": "live",
            "_requested_source_mode": source_mode,
            "_symbol": symbol,
        }
        return self._store_record_response(record, raw_payload, source_mode_requested=source_mode)

    def analyze_symbol(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        symbol = str(payload.get("symbol", "")).strip().upper()
        source_mode = str(payload.get("source_mode", _SOURCE_PROGRAM_MODE)).strip().lower()
        if not symbol or not _TICKER_RE.fullmatch(symbol):
            reason = "Invalid ticker format."
            self.state.start_run(symbol=symbol or "", source_mode=source_mode)
            self.state.fail_run(reason)
            return 400, {"ok": False, "error": reason, "run_state": self.state.run_state_payload()}

        self.state.start_run(symbol=symbol, source_mode=source_mode)
        if source_mode != _SOURCE_PROGRAM_MODE:
            reason = f"Unsupported source mode: {source_mode}"
            self.state.fail_run(reason, source_used="unsupported_source", source_class="unavailable", mode_kind="live")
            return 400, {"ok": False, "error": reason, "run_state": self.state.run_state_payload()}
        return self.queue_manual_session_command(symbol)

    def settings_response(self, *, server_port: int) -> dict[str, Any]:
        payload = self.state.settings_payload(
            host=self.host,
            port=server_port,
            current_config=self.processor.config,
        )
        payload["payload_example"] = {
            "symbol": "SPY",
            "exchange": "NYSEARCA",
            "timeframe": "5m",
            "timestamp": "2026-04-01T13:35:00Z",
            "close": 500.2,
            "trend_pass": True,
            "compression_pass": True,
            "breakout_pass": True,
            "trap_risk_elevated": False,
            "compression_high": 499.8,
            "compression_low": 496.4,
            "trigger_level": 499.85,
            "breakout_price": 500.2,
            "breakout_range_vs_base_avg": 1.8,
            "relative_volume": 1.4,
            "rejection_wick_pct": 8.0,
            "overhead_clearance_pct": 2.2,
        }
        payload["ocr_status"] = self.ocr_service.status_payload()
        payload["browser_status"] = self.browser_service.status_payload()
        payload["source_settings"] = self._masked_source_settings_payload()
        payload["analyze_modes"] = [
            {"value": _SOURCE_PROGRAM_MODE, "label": _SOURCE_PROGRAM_LABEL},
        ]
        payload["source_program"] = {
            "mode": _SOURCE_PROGRAM_MODE,
            "label": _SOURCE_PROGRAM_LABEL,
            "active": True,
            "message": _SOURCE_PROGRAM_MESSAGE,
            "browser_status": self.browser_service.thinkorswim_browser_status(),
            "manual_session_status": self.manual_session_status(),
            "manual_session_helper": {
                "path": "scripts/thinkorswim_manual_session_helper.js",
                "submit_endpoint": "/api/manual-session/analyze",
            },
            "archived_integrations": ["twelvedata", "yahoo", "tradingview_webhook", "ocr"],
        }
        return payload

    def start_source_browser(self) -> tuple[int, dict[str, Any]]:
        result = self.browser_service.start_thinkorswim_browser()
        status_code = 200 if result.get("ok") else 400
        return status_code, {"ok": bool(result.get("ok")), **result, "browser_status": self.browser_service.thinkorswim_browser_status()}

    def stop_source_browser(self) -> tuple[int, dict[str, Any]]:
        result = self.browser_service.stop_thinkorswim_browser()
        return 200, {"ok": True, **result, "browser_status": self.browser_service.thinkorswim_browser_status()}

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.override_path is None:
            raise ValueError("GUI settings override path is not configured.")
        override_payload, public_webhook_url = _build_override_payload(payload)
        save_yaml(self.override_path, override_payload)
        if self.source_settings_path is not None:
            save_source_settings(self.source_settings_path, _build_source_settings_payload(payload))
        self.state.public_webhook_url = public_webhook_url
        self.reload_config()
        return {"ok": True, "message": "Settings saved locally.", "settings": self.settings_response(server_port=self.port)}

    def reset_settings(self) -> dict[str, Any]:
        if self.override_path is not None:
            reset_yaml(self.override_path)
        if self.source_settings_path is not None:
            reset_yaml(self.source_settings_path)
        self.state.public_webhook_url = None
        self.reload_config()
        return {"ok": True, "message": "Settings reset to defaults.", "settings": self.settings_response(server_port=self.port)}

    def load_demo_settings(self) -> dict[str, Any]:
        if self.override_path is None:
            raise ValueError("GUI settings override path is not configured.")
        if self.demo_override_path is None:
            raise ValueError("Demo preset path is not configured.")
        save_yaml(self.override_path, load_optional_yaml(self.demo_override_path))
        self.reload_config()
        return {"ok": True, "message": "Demo preset loaded.", "settings": self.settings_response(server_port=self.port)}

    def delete_record(self, scan_id: str) -> tuple[int, dict[str, Any]]:
        if not self.state.delete_record(scan_id):
            return 404, {"ok": False, "error": "Record not found."}
        return 200, {"ok": True, "message": "Record deleted.", "run_state": self.state.run_state_payload()}

    def clear_records(self, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        payload = payload or {}
        symbol = str(payload.get("symbol", "") or "").strip() or None
        deleted_count = self.state.clear_records(symbol=symbol)
        if deleted_count == 0:
            return 200, {"ok": True, "message": "No matching records to clear.", "deleted_count": 0}
        label = f" for {symbol.upper()}" if symbol else ""
        return 200, {"ok": True, "message": f"Cleared {deleted_count} record(s){label}.", "deleted_count": deleted_count}


def create_gui_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    config_dir: str | Path = "config",
    log_path: str | Path | None = None,
    override_path: str | Path | None = None,
    demo_override_path: str | Path | None = None,
) -> ThreadingHTTPServer:
    config_dir_path = Path(config_dir)
    override_file = Path(override_path) if override_path is not None else None
    source_settings_file = (override_file.parent if override_file is not None else config_dir_path) / "gui_sources.yaml"
    app = GUIApplication(
        processor=WebhookProcessor(
            config=load_scan_config(config_dir_path, override_path=override_file),
            signal_logger=SignalLogger(log_path=Path(log_path) if log_path is not None else None),
        ),
        state=GUIState(
            config_dir=config_dir_path,
            log_path=Path(log_path) if log_path is not None else None,
            override_path=override_file,
        ),
        browser_service=BrowserSourceManager(settings_path=source_settings_file),
        ocr_service=OCRScreenService((override_file.parent if override_file is not None else config_dir_path) / "ocr_user.yaml"),
        host=host,
        port=port,
        config_dir=config_dir_path,
        override_path=override_file,
        demo_override_path=Path(demo_override_path) if demo_override_path is not None else None,
        source_settings_path=source_settings_file,
    )
    if app.browser_service.thinkorswim_browser_status().get("launch_on_startup"):
        app.browser_service.start_thinkorswim_browser()

    class GUIHandler(BaseHTTPRequestHandler):
        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._write_cors_headers()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._write_html(200, build_index_html())
                return
            if parsed.path == "/api/health":
                self._write_json(200, app.state.health_payload(host=app.host, port=self.server.server_port))
                return
            if parsed.path == "/api/run-state":
                self._write_json(
                    200,
                    {
                        "ok": True,
                        "run_state": app.state.run_state_payload(),
                        "manual_session_status": app.manual_session_status(),
                    },
                )
                return
            if parsed.path == "/api/settings":
                self._write_json(200, app.settings_response(server_port=self.server.server_port))
                return
            if parsed.path == "/api/manual-session/next-command":
                self._write_json(200, app.next_manual_session_command())
                return
            if parsed.path == "/api/manual-session/status":
                self._write_json(200, {"ok": True, "helper_status": app.manual_session_status()})
                return
            if parsed.path == "/api/source-program/browser-status":
                self._write_json(200, {"ok": True, "browser_status": app.browser_service.thinkorswim_browser_status()})
                return
            if parsed.path == "/api/source-settings/test-twelvedata":
                status_code, payload = app.test_twelvedata_connection()
                self._write_json(status_code, payload)
                return
            if parsed.path == "/api/diagnostics":
                recent_record = app.state.list_records(limit=1)
                latest = recent_record[0].record.to_dict() if recent_record else None
                self._write_json(
                    200,
                    {
                        "ok": True,
                        "latest_record": latest,
                        "source": latest.get("diagnostics", {}).get("source") if latest else {},
                        "strategy": latest.get("diagnostics", {}).get("strategy") if latest else {},
                        "system": latest.get("diagnostics", {}).get("system") if latest else {},
                        "ocr": latest.get("diagnostics", {}).get("ocr") if latest else {},
                    },
                )
                return
            if parsed.path == "/api/recent":
                recent = [app.state.record_summary(stored) for stored in app.state.list_recent_records(limit=6)]
                self._write_json(200, {"ok": True, "records": recent})
                return
            if parsed.path == "/api/records":
                query = parse_qs(parsed.query)
                symbol = query.get("symbol", [None])[0]
                status = query.get("status", [None])[0]
                start_date = query.get("start_date", [None])[0]
                end_date = query.get("end_date", [None])[0]
                limit_value = query.get("limit", [None])[0]
                limit = int(limit_value) if limit_value else None
                records = [
                    app.state.record_summary(stored)
                    for stored in app.state.list_records(
                        symbol=symbol,
                        status=status,
                        start_date=start_date,
                        end_date=end_date,
                        limit=limit,
                    )
                ]
                self._write_json(200, {"ok": True, "records": records})
                return
            if parsed.path.startswith("/api/records/"):
                scan_id = parsed.path.removeprefix("/api/records/")
                stored = app.state.get_record(scan_id)
                if stored is None:
                    self._write_json(404, {"ok": False, "error": "Record not found."})
                    return
                self._write_json(200, build_detail_payload(stored.record, stored.raw_payload, app.state))
                return
            self._write_json(404, {"ok": False, "error": "Not found."})

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in {
                "/api/replay",
                "/api/analyze",
                "/webhook",
                "/api/settings/save",
                "/api/source-settings/test-twelvedata",
                "/api/settings/reset",
                "/api/settings/load-demo",
                "/api/records/clear",
                "/api/source-program/start-browser",
                "/api/source-program/stop-browser",
                "/api/manual-session/analyze",
                "/api/manual-session/report",
                "/api/manual-session/debug",
            }:
                self._write_json(404, {"ok": False, "error": "Not found."})
                return

            payload = {}
            if self.path not in {"/api/settings/reset", "/api/settings/load-demo"}:
                try:
                    content_length = int(self.headers.get("Content-Length", "0"))
                    raw_body = self.rfile.read(content_length)
                    payload = json.loads(raw_body.decode("utf-8"))
                except json.JSONDecodeError:
                    self._write_json(400, {"ok": False, "error": "Request body must be valid JSON."})
                    return

            try:
                if self.path == "/api/analyze":
                    status_code, response = app.analyze_symbol(payload)
                    self._write_json(status_code, response)
                    return
                if self.path in {"/api/replay", "/webhook"}:
                    ingest_mode = "replay" if self.path == "/api/replay" else "webhook"
                    status_code, response = app.process_payload(payload, ingest_mode=ingest_mode)
                    self._write_json(status_code, response)
                    return
                if self.path == "/api/settings/save":
                    self._write_json(200, app.save_settings(payload))
                    return
                if self.path == "/api/source-settings/test-twelvedata":
                    status_code, response = app.test_twelvedata_connection(payload)
                    self._write_json(status_code, response)
                    return
                if self.path == "/api/settings/reset":
                    self._write_json(200, app.reset_settings())
                    return
                if self.path == "/api/settings/load-demo":
                    self._write_json(200, app.load_demo_settings())
                    return
                if self.path == "/api/records/clear":
                    status_code, response = app.clear_records(payload)
                    self._write_json(status_code, response)
                    return
                if self.path == "/api/manual-session/analyze":
                    status_code, response = app.analyze_manual_session(payload)
                    self._write_json(status_code, response)
                    return
                if self.path == "/api/manual-session/report":
                    status_code, response = app.report_manual_session_payload(payload)
                    self._write_json(status_code, response)
                    return
                if self.path == "/api/manual-session/debug":
                    status_code, response = app.report_manual_session_debug(payload)
                    self._write_json(status_code, response)
                    return
                if self.path == "/api/source-program/start-browser":
                    status_code, response = app.start_source_browser()
                    self._write_json(status_code, response)
                    return
                if self.path == "/api/source-program/stop-browser":
                    status_code, response = app.stop_source_browser()
                    self._write_json(status_code, response)
                    return
            except ValueError as exc:
                self._write_json(400, {"ok": False, "error": str(exc)})
                return

        def do_DELETE(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/records/"):
                self._write_json(404, {"ok": False, "error": "Not found."})
                return
            scan_id = parsed.path.removeprefix("/api/records/")
            if not scan_id:
                self._write_json(400, {"ok": False, "error": "Record id is required."})
                return
            status_code, response = app.delete_record(scan_id)
            self._write_json(status_code, response)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status_code)
            self._write_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _write_html(self, status_code: int, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status_code)
            self._write_cors_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _write_cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    server = ThreadingHTTPServer((host, port), GUIHandler)
    app.port = server.server_port
    return server

