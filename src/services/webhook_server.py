from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from src.modules.explanation import build_explanations
from src.modules.quality_score import evaluate_quality_score
from src.modules.skip_reasons import build_skip_or_no_trade_reason
from src.analysis.source_manager import SourceManager
from src.analysis.thesis_engine import build_thesis
from src.scanner.models import (
    DecisionOutcome,
    ModuleResult,
    ScanConfig,
    ScanFlags,
    ScanStatus,
    SymbolContext,
    build_empty_scan_record,
)
from src.services.config_loader import load_scan_config
from src.services.logging import SignalLogger
from src.services.webhook_models import TradingViewWebhookPayload
from src.utils.validation import validate_scan_record


@dataclass(slots=True)
class WebhookProcessor:
    config: ScanConfig
    signal_logger: SignalLogger

    def _build_trend_result(self, payload: TradingViewWebhookPayload) -> ModuleResult:
        passed = payload.trend_pass
        return ModuleResult(
            module_name="trend_filter",
            outcome=DecisionOutcome.PASS if passed else DecisionOutcome.FAIL,
            passed=passed,
            metrics={
                "trend_strength_score": 100.0 if passed else 0.0,
                "alert_timeframe": payload.timeframe,
            },
            reasons=[
                "TradingView webhook reported trend_pass=true."
                if passed
                else "TradingView webhook reported trend_pass=false."
            ],
            flags={"daily_trend_pass": passed},
        )

    def _build_compression_result(self, payload: TradingViewWebhookPayload) -> ModuleResult:
        passed = payload.compression_pass
        metrics: dict[str, float | int | bool | str | None] = {
            "compression_high": payload.compression_high,
            "compression_low": payload.compression_low,
        }
        return ModuleResult(
            module_name="compression",
            outcome=DecisionOutcome.PASS if passed else DecisionOutcome.FAIL,
            passed=passed,
            metrics=metrics,
            reasons=[
                "TradingView webhook reported compression_pass=true."
                if passed
                else "TradingView webhook reported compression_pass=false."
            ],
            flags={"compression_pass": passed},
        )

    def _build_breakout_result(self, payload: TradingViewWebhookPayload) -> ModuleResult:
        passed = payload.breakout_pass
        breakout_price = payload.breakout_price if payload.breakout_price is not None else payload.close
        metrics: dict[str, float | int | bool | str | None] = {
            "trigger_level": payload.trigger_level,
            "breakout_price": breakout_price,
            "breakout_range_vs_base_avg": payload.breakout_range_vs_base_avg,
            "relative_volume": payload.relative_volume,
            "breakout_timestamp_utc": payload.timestamp,
        }
        return ModuleResult(
            module_name="breakout_trigger",
            outcome=DecisionOutcome.PASS if passed else DecisionOutcome.FAIL,
            passed=passed,
            metrics=metrics,
            reasons=[
                "TradingView webhook reported breakout_pass=true."
                if passed
                else "TradingView webhook reported breakout_pass=false."
            ],
            flags={"trigger_pass": passed},
        )

    def _build_trap_risk_result(self, payload: TradingViewWebhookPayload) -> ModuleResult:
        elevated = payload.trap_risk_elevated
        metrics: dict[str, float | int | bool | str | None] = {
            "rejection_wick_pct": payload.rejection_wick_pct,
            "overhead_clearance_pct": payload.overhead_clearance_pct,
            "trap_risk_penalty": 1 if elevated else 0,
        }
        return ModuleResult(
            module_name="trap_risk",
            outcome=DecisionOutcome.NO_TRADE if elevated else DecisionOutcome.PASS,
            passed=not elevated,
            metrics=metrics,
            reasons=[
                "TradingView webhook reported trap_risk_elevated=true."
                if elevated
                else "TradingView webhook reported trap_risk_elevated=false."
            ],
            flags={"trap_risk_elevated": elevated},
        )

    def build_record(self, payload: TradingViewWebhookPayload) -> Any:
        source_manager = SourceManager()
        snapshot_result = source_manager.from_webhook(payload)
        trend_result = self._build_trend_result(payload)
        compression_result = self._build_compression_result(payload)
        breakout_result = self._build_breakout_result(payload)
        trap_risk_result = self._build_trap_risk_result(payload)
        score_result = evaluate_quality_score(
            SymbolContext(symbol=payload.symbol),
            self.config.scoring,
            trend_result,
            compression_result,
            breakout_result,
            trap_risk_result,
        )

        record = build_empty_scan_record(
            payload.symbol,
            scan_id=f"webhook-{payload.symbol}-{payload.timestamp}",
            config_version=self.config.defaults.get("version", "v1-defaults"),
            status=ScanStatus.SKIPPED,
        )
        record.timestamp_utc = payload.timestamp
        record.snapshot = snapshot_result.snapshot
        record.metrics.update(
            {
                "exchange": payload.exchange,
                "alert_timeframe": payload.timeframe,
                "close": payload.close,
                **trend_result.metrics,
                **compression_result.metrics,
                **breakout_result.metrics,
                **trap_risk_result.metrics,
            }
        )
        record.module_results = {
            "trend_filter": trend_result,
            "compression": compression_result,
            "breakout_trigger": breakout_result,
            "trap_risk": trap_risk_result,
            "quality_score": score_result,
        }
        record.flags = ScanFlags(
            daily_trend_pass=trend_result.passed,
            compression_pass=compression_result.passed,
            trigger_pass=breakout_result.passed,
            trap_risk_elevated=trap_risk_result.outcome == DecisionOutcome.NO_TRADE,
            volume_confirmation_used=payload.relative_volume is not None,
        )
        record.setup_window.trigger_time = payload.timestamp
        record.levels.compression_high = payload.compression_high
        record.levels.compression_low = payload.compression_low
        record.levels.trigger_level = payload.trigger_level
        record.levels.breakout_price = payload.breakout_price if payload.breakout_price is not None else payload.close
        record.levels.nearest_overhead_resistance = None
        record.scores.total = float(score_result.metrics.get("total", 0.0))
        record.scores.trend_alignment = float(score_result.metrics.get("trend_alignment", 0.0))
        record.scores.squeeze_quality = float(score_result.metrics.get("squeeze_quality", 0.0))
        record.scores.breakout_impulse = float(score_result.metrics.get("breakout_impulse", 0.0))
        record.scores.path_quality = float(score_result.metrics.get("path_quality", 0.0))
        record.scores.trap_risk_penalty = float(score_result.metrics.get("trap_risk_penalty", 0.0))

        if not payload.trend_pass:
            record.status = ScanStatus.SKIPPED
        elif not payload.compression_pass or not payload.breakout_pass:
            record.status = ScanStatus.REJECTED
        elif payload.trap_risk_elevated:
            record.status = ScanStatus.NO_TRADE
        else:
            record.status = ScanStatus.QUALIFIED

        record.explanations = build_explanations(record)
        reason = build_skip_or_no_trade_reason(record)
        if record.status == ScanStatus.SKIPPED:
            record.explanations.skip_reason = reason
        if record.status == ScanStatus.NO_TRADE:
            record.explanations.no_trade_reason = reason
        record.thesis, record.diagnostics = build_thesis(record)
        record.diagnostics.source = snapshot_result.diagnostics

        validate_scan_record(record)
        self.signal_logger.log_signal(record)
        return record

    def handle_payload(self, payload_dict: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            payload = TradingViewWebhookPayload.from_dict(payload_dict)
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}

        record = self.build_record(payload)
        return 200, {"ok": True, "status": record.status.value, "record": record.to_dict()}


def create_webhook_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    config_dir: str | Path = "config",
    log_path: str | Path | None = None,
) -> ThreadingHTTPServer:
    processor = WebhookProcessor(
        config=load_scan_config(config_dir),
        signal_logger=SignalLogger(log_path=Path(log_path) if log_path is not None else None),
    )

    class WebhookHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/webhook":
                self._write_json(404, {"ok": False, "error": "Not found."})
                return

            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length)
                payload = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError:
                self._write_json(400, {"ok": False, "error": "Request body must be valid JSON."})
                return

            status_code, response = processor.handle_payload(payload)
            self._write_json(status_code, response)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), WebhookHandler)
