from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.scanner.models import ScanConfig, SymbolContext
from src.scanner.runner import ScanRunner
from src.services.config_loader import load_optional_yaml, load_scan_config, reset_yaml, save_yaml
from src.services.gui_html import build_index_html
from src.services.gui_responses import build_detail_payload, build_replay_result_payload
from src.services.gui_state import GUIState
from src.services.logging import SignalLogger
from src.services.market_data import TwelveDataMarketDataProvider, YahooFinanceMarketDataProvider
from src.services.ocr_screen import OCRScreenService
from src.services.webhook_models import TradingViewWebhookPayload
from src.services.webhook_server import WebhookProcessor

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")
_FRESH_WEBHOOK_MAX_AGE_SECONDS = 15 * 60


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


@dataclass(slots=True)
class GUIApplication:
    processor: WebhookProcessor
    state: GUIState
    ocr_service: OCRScreenService
    host: str
    port: int
    config_dir: Path
    override_path: Path | None = None
    demo_override_path: Path | None = None

    def reload_config(self) -> ScanConfig:
        self.processor.config = load_scan_config(self.config_dir, override_path=self.override_path)
        return self.processor.config

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

        if source_mode == "twelvedata":
            self.state.advance_run("Checking Twelve Data", mode_kind="live")
            provider_name = "twelvedata"
            provider = _make_provider(provider_name)
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
            primary_provider = _make_provider("twelvedata")
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

                    self.state.advance_run(
                        "Checking screen-read fallback",
                        source_used="webhook_unavailable",
                        fallback_chain=fallback_chain,
                        coverage=yahoo_coverage,
                        warnings=warnings,
                        mode_kind="live",
                    )
                    ocr_status = self.ocr_service.status_payload()
                    ocr_result = None
                    if ocr_status["configured"]:
                        fallback_chain.append("ocr")
                        ocr_result = self.ocr_service.analyze(symbol)
                        warnings.extend(ocr_result.warnings)
                        if ocr_result.capture_source:
                            warnings.append(f"OCR capture source: {ocr_result.capture_source}")
                    elif ocr_status["enabled"]:
                        warnings.append("Screen-read fallback is enabled but not configured yet.")

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
        source_mode = str(payload.get("source_mode", "auto")).strip().lower()
        if not symbol or not _TICKER_RE.fullmatch(symbol):
            reason = "Invalid ticker format."
            self.state.start_run(symbol=symbol or "", source_mode=source_mode)
            self.state.fail_run(reason)
            return 400, {"ok": False, "error": reason, "run_state": self.state.run_state_payload()}

        self.state.start_run(symbol=symbol, source_mode=source_mode)
        supported_modes = {"auto", "twelvedata", "webhook", "ocr"}
        if source_mode not in supported_modes:
            reason = f"Unsupported source mode: {source_mode}"
            self.state.fail_run(reason, source_class="unavailable")
            return 400, {"ok": False, "error": reason, "run_state": self.state.run_state_payload()}

        return self._run_live_scan(symbol=symbol, source_mode=source_mode)

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
        payload["analyze_modes"] = [
            {"value": "auto", "label": "Auto"},
            {"value": "twelvedata", "label": "Twelve Data"},
            {"value": "webhook", "label": "TradingView webhook"},
            {"value": "ocr", "label": "Screen read fallback"},
        ]
        return payload

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.override_path is None:
            raise ValueError("GUI settings override path is not configured.")
        override_payload, public_webhook_url = _build_override_payload(payload)
        save_yaml(self.override_path, override_payload)
        self.state.public_webhook_url = public_webhook_url
        self.reload_config()
        return {"ok": True, "message": "Settings saved locally.", "settings": self.settings_response(server_port=self.port)}

    def reset_settings(self) -> dict[str, Any]:
        if self.override_path is not None:
            reset_yaml(self.override_path)
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
        ocr_service=OCRScreenService((override_file.parent if override_file is not None else config_dir_path) / "ocr_user.yaml"),
        host=host,
        port=port,
        config_dir=config_dir_path,
        override_path=override_file,
        demo_override_path=Path(demo_override_path) if demo_override_path is not None else None,
    )

    class GUIHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._write_html(200, build_index_html())
                return
            if parsed.path == "/api/health":
                self._write_json(200, app.state.health_payload(host=app.host, port=self.server.server_port))
                return
            if parsed.path == "/api/run-state":
                self._write_json(200, {"ok": True, "run_state": app.state.run_state_payload()})
                return
            if parsed.path == "/api/settings":
                self._write_json(200, app.settings_response(server_port=self.server.server_port))
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
                "/api/settings/reset",
                "/api/settings/load-demo",
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
                if self.path == "/api/settings/reset":
                    self._write_json(200, app.reset_settings())
                    return
                if self.path == "/api/settings/load-demo":
                    self._write_json(200, app.load_demo_settings())
                    return
            except ValueError as exc:
                self._write_json(400, {"ok": False, "error": str(exc)})
                return

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _write_html(self, status_code: int, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer((host, port), GUIHandler)
    app.port = server.server_port
    return server

