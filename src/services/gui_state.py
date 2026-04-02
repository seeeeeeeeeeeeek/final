from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from src.scanner.models import (
    DebugPayload,
    DiagnosticsPayload,
    ExplanationPayload,
    MarketSnapshot,
    ModuleResult,
    PriceLevels,
    ScanConfig,
    ScanFlags,
    ScanRecord,
    ScanStatus,
    ScoreBreakdown,
    SetupWindow,
    ThesisPayload,
    TimeframeConfig,
)


@dataclass(slots=True)
class StoredRecord:
    record: ScanRecord
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class RunState:
    status: str = "idle"
    current_ticker: str | None = None
    source_mode_requested: str | None = None
    current_step: str = "Waiting to start"
    last_completed_step: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    source_used: str | None = None
    fallback_chain: list[str] = field(default_factory=list)
    coverage: dict[str, bool] = field(default_factory=dict)
    missing_context: list[str] = field(default_factory=list)
    mode_kind: str | None = None
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    latest_scan_id: str | None = None
    last_run_timestamp: str | None = None


def _safe_scan_status(value: Any) -> ScanStatus:
    try:
        return ScanStatus(str(value))
    except ValueError:
        return ScanStatus.SKIPPED


def _scan_record_from_payload(payload: dict[str, Any]) -> ScanRecord:
    return ScanRecord(
        scan_id=str(payload.get("scan_id", "")),
        symbol=str(payload.get("symbol", "")),
        market=str(payload.get("market", "US")),
        direction=str(payload.get("direction", "long")),
        status=_safe_scan_status(payload.get("status")),
        timestamp_utc=str(payload.get("timestamp_utc", "")),
        timeframes=TimeframeConfig(**dict(payload.get("timeframes", {}))),
        setup_window=SetupWindow(**dict(payload.get("setup_window", {}))),
        levels=PriceLevels(**dict(payload.get("levels", {}))),
        metrics=dict(payload.get("metrics", {})),
        scores=ScoreBreakdown(**dict(payload.get("scores", {}))),
        flags=ScanFlags(**dict(payload.get("flags", {}))),
        explanations=ExplanationPayload(**dict(payload.get("explanations", {}))),
        debug=DebugPayload(**dict(payload.get("debug", {}))),
        snapshot=MarketSnapshot(**dict(payload.get("snapshot", {}))),
        thesis=ThesisPayload(**dict(payload.get("thesis", {}))),
        diagnostics=DiagnosticsPayload(**dict(payload.get("diagnostics", {}))),
        module_results={},
    )


def _record_sort_key(stored: StoredRecord) -> tuple[int, str]:
    timestamp = stored.record.timestamp_utc or ""
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return (1, parsed.isoformat())
    except ValueError:
        return (0, timestamp)


@dataclass(slots=True)
class GUIState:
    config_dir: Path
    log_path: Path | None = None
    export_dir: Path | None = None
    override_path: Path | None = None
    max_records: int = 500
    public_webhook_url: str | None = None
    _records: list[StoredRecord] = field(default_factory=list)
    _run_state: RunState = field(default_factory=RunState)
    _run_state_lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.load_records_from_log()

    def load_records_from_log(self) -> None:
        if self.log_path is None or not self.log_path.exists():
            return

        loaded: list[StoredRecord] = []
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                try:
                    record = _scan_record_from_payload(payload)
                except TypeError:
                    continue
                loaded.append(StoredRecord(record=record, raw_payload=dict(payload.get("raw_payload", {}))))

        loaded.sort(key=_record_sort_key, reverse=True)
        self._records = loaded[: self.max_records]

    def add_record(self, record: ScanRecord, raw_payload: dict[str, Any]) -> None:
        self._records = [stored for stored in self._records if stored.record.scan_id != record.scan_id]
        self._records.insert(0, StoredRecord(record=record, raw_payload=raw_payload))
        self._records.sort(key=_record_sort_key, reverse=True)
        self._records = self._records[: self.max_records]

    def list_records(
        self,
        *,
        symbol: str | None = None,
        status: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> list[StoredRecord]:
        records = self._records
        if symbol:
            symbol_upper = symbol.upper()
            records = [stored for stored in records if stored.record.symbol.upper() == symbol_upper]
        if status:
            records = [stored for stored in records if stored.record.status.value == status]
        if start_date:
            records = [stored for stored in records if stored.record.timestamp_utc[:10] >= start_date]
        if end_date:
            records = [stored for stored in records if stored.record.timestamp_utc[:10] <= end_date]
        if limit is not None:
            records = records[:limit]
        return records

    def get_record(self, scan_id: str) -> StoredRecord | None:
        for stored in self._records:
            if stored.record.scan_id == scan_id:
                return stored
        return None

    def get_latest_record_for_symbol(self, symbol: str, *, ingest_mode: str | None = None) -> StoredRecord | None:
        symbol_upper = symbol.upper()
        for stored in self._records:
            if stored.record.symbol.upper() != symbol_upper:
                continue
            if ingest_mode is not None and stored.raw_payload.get("_ingest_mode") != ingest_mode:
                continue
            return stored
        return None

    def infer_bias(self, record: ScanRecord) -> str:
        if record.thesis.strategy_match == "Breakout Continuation":
            return "Bullish continuation"
        thesis_parts = [part for part in (record.thesis.swing_bias, record.thesis.intraday_bias) if part and part != "Unavailable"]
        if thesis_parts:
            return " / ".join(thesis_parts)
        if record.status == ScanStatus.QUALIFIED:
            return "Bullish continuation"
        if record.status == ScanStatus.NO_TRADE:
            return "Bullish but risk elevated"
        if record.status == ScanStatus.REJECTED:
            return "Setup invalid"
        return "Not aligned yet"

    def setup_status_label(self, record: ScanRecord) -> str:
        if record.status == ScanStatus.QUALIFIED:
            return "Ready / Valid setup"
        if record.status == ScanStatus.NO_TRADE:
            return "No trade"
        if record.status == ScanStatus.SKIPPED:
            return "Not enough data"
        return "Failed setup"

    def bias_label(self, record: ScanRecord) -> str:
        bias = self.infer_bias(record)
        if "Bullish" in bias or "Upward" in bias:
            return f"Upward bias ({bias})"
        if "Bearish" in bias:
            return f"Downward bias ({bias})"
        return bias

    def confidence_label(self, record: ScanRecord) -> str:
        total = record.thesis.confidence_score or record.scores.total
        if total >= 80.0:
            return "High"
        if total >= 60.0:
            return "Medium"
        if total > 0.0:
            return "Low"
        return "Very low"

    def confidence_explanation(self, record: ScanRecord) -> str:
        coverage = record.diagnostics.source.get("timeframe_coverage", {}) if record.diagnostics.source else {}
        missing = [name for name, available in coverage.items() if not available and name != "1m"]
        if missing:
            joined = ", ".join(missing)
            return f"Low confidence because {joined} context is missing."
        if record.status == ScanStatus.QUALIFIED and not record.levels.nearest_overhead_resistance:
            return "Medium confidence because the setup is active, but the next resistance level is unclear."
        if record.flags.trap_risk_elevated:
            return "Medium confidence because the setup triggered, but risk stayed elevated."
        if record.status == ScanStatus.QUALIFIED and all(
            (record.flags.daily_trend_pass, record.flags.compression_pass, record.flags.trigger_pass)
        ):
            return "High confidence because higher timeframe trend, setup, and trigger all align."
        if record.status == ScanStatus.NO_TRADE:
            return "Low confidence because the setup was technically valid, but not actionable."
        if record.status == ScanStatus.REJECTED:
            return "Low confidence because the setup rules failed before confirmation."
        return "Low confidence because the app does not have enough aligned evidence yet."

    def timeframe_summary(self, record: ScanRecord) -> dict[str, str]:
        swing_bias = record.thesis.swing_bias or "Unavailable"
        intraday_bias = record.thesis.intraday_bias or "Unavailable"
        short_term_bias = record.thesis.short_term_bias or "Unavailable"
        return {
            "daily_context": (
                "Bullish" if swing_bias == "Bullish" else "Bearish" if swing_bias == "Bearish" else "Unavailable"
            ),
            "hourly_setup": (
                "Constructive" if intraday_bias == "Constructive" else "Weak" if intraday_bias == "Weak" else "Unavailable"
            ),
            "trigger_5m": (
                "Active" if short_term_bias == "Active" else "Failed" if short_term_bias == "Invalid" else short_term_bias
            ),
            "execution_1m": "Not used",
        }

    def best_action_label(self, record: ScanRecord) -> str:
        if record.status == ScanStatus.QUALIFIED:
            return "Consider Long"
        if record.status == ScanStatus.NO_TRADE:
            return "No Trade"
        if "Bearish" in self.infer_bias(record):
            return "Consider Short"
        return "Watch Only"

    def trust_signals(self, record: ScanRecord) -> list[str]:
        signals: list[str] = []
        coverage = record.diagnostics.source.get("timeframe_coverage", {}) if record.diagnostics.source else {}
        if coverage:
            available = [name for name, present in coverage.items() if present]
            if available == ["5m"]:
                signals.append("5m only")
            elif coverage.get("1D") and coverage.get("1H"):
                signals.append("Daily + 1H aligned")
            elif not coverage.get("1D") or not coverage.get("1H"):
                signals.append("HTF missing")
        source_used = record.thesis.source_used or record.snapshot.source_used
        if source_used:
            signals.append(f"{source_used.title()} source")
        if record.flags.daily_trend_pass and record.flags.compression_pass:
            signals.append("Trend + setup aligned")
        return signals[:3]

    def helper_copy(self) -> dict[str, str]:
        return {
            "target": "Target = the next level the setup is aiming for.",
            "invalidation": "Invalidation = where the idea breaks.",
            "confidence": "Confidence = how complete and aligned the signal is.",
        }

    def _coverage_text(self, coverage: dict[str, bool]) -> str:
        available = [timeframe for timeframe in ("1D", "1H", "5m", "1m") if coverage.get(timeframe)]
        if not available:
            return "No timeframe data available"
        return ", ".join(available) + " available"

    def _missing_context(self, coverage: dict[str, bool]) -> list[str]:
        return [timeframe for timeframe in ("1D", "1H", "5m") if not coverage.get(timeframe)]

    def source_path(self, record: ScanRecord, raw_payload: dict[str, Any]) -> dict[str, Any]:
        source = record.diagnostics.source or {}
        coverage = dict(source.get("timeframe_coverage", {}))
        missing_context = self._missing_context(coverage)
        requested = (
            raw_payload.get("_requested_source_mode")
            or source.get("requested_source_mode")
            or ("webhook" if record.snapshot.source_type == "webhook" else "live")
        )
        mode_kind = (
            raw_payload.get("_ingest_mode")
            or source.get("mode_kind")
            or ("replay" if raw_payload.get("_ingest_mode") == "replay" else "live")
        )
        used = source.get("source_selected") or record.snapshot.source_used or "unknown"
        fallback_chain = list(source.get("fallback_chain", []))
        return {
            "requested": requested,
            "used": used,
            "fallback_chain": fallback_chain,
            "mode_kind": mode_kind,
            "coverage": coverage,
            "coverage_text": self._coverage_text(coverage),
            "missing_context": missing_context,
            "missing_context_text": ", ".join(missing_context) if missing_context else "None",
            "warnings": list(source.get("warnings", [])),
        }

    def timeframe_story(self, record: ScanRecord) -> list[dict[str, str]]:
        summary = self.timeframe_summary(record)
        return [
            {"label": "Daily context", "value": summary["daily_context"]},
            {"label": "1H setup", "value": summary["hourly_setup"]},
            {"label": "5m trigger", "value": summary["trigger_5m"]},
            {"label": "1m execution", "value": summary["execution_1m"]},
        ]

    def record_summary(self, stored: StoredRecord) -> dict[str, Any]:
        payload = stored.record.to_dict()
        source_path = self.source_path(stored.record, stored.raw_payload)
        payload["bias"] = self.bias_label(stored.record)
        payload["confidence_label"] = self.confidence_label(stored.record)
        payload["confidence_explanation"] = self.confidence_explanation(stored.record)
        payload["setup_status_label"] = self.setup_status_label(stored.record)
        payload["why_it_matters"] = stored.record.thesis.explanation_summary or stored.record.explanations.summary or "No explanation available yet."
        payload["has_raw_payload"] = bool(stored.raw_payload)
        payload["source_used"] = stored.record.thesis.source_used or stored.record.snapshot.source_used
        payload["strategy_match"] = stored.record.thesis.strategy_match
        payload["short_term_target"] = stored.record.thesis.short_term_target or "Not available yet"
        payload["invalidation"] = stored.record.thesis.invalidation or "Not available yet"
        payload["timeframe_summary"] = self.timeframe_summary(stored.record)
        payload["best_action"] = self.best_action_label(stored.record)
        payload["trust_signals"] = self.trust_signals(stored.record)
        payload["source_path"] = source_path
        return payload

    def start_run(self, *, symbol: str, source_mode: str) -> None:
        with self._run_state_lock:
            self._run_state = RunState(
                status="running",
                current_ticker=symbol.upper(),
                source_mode_requested=source_mode,
                current_step="Preparing analysis request",
                completed_steps=[],
                last_run_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )

    def advance_run(
        self,
        step: str,
        *,
        source_used: str | None = None,
        fallback_chain: list[str] | None = None,
        coverage: dict[str, bool] | None = None,
        mode_kind: str | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        with self._run_state_lock:
            if self._run_state.current_step and self._run_state.current_step not in self._run_state.completed_steps:
                self._run_state.completed_steps.append(self._run_state.current_step)
                self._run_state.last_completed_step = self._run_state.current_step
            self._run_state.current_step = step
            if source_used is not None:
                self._run_state.source_used = source_used
            if fallback_chain is not None:
                self._run_state.fallback_chain = list(fallback_chain)
            if coverage is not None:
                self._run_state.coverage = dict(coverage)
                self._run_state.missing_context = self._missing_context(coverage)
            if mode_kind is not None:
                self._run_state.mode_kind = mode_kind
            if warnings is not None:
                self._run_state.warnings = list(warnings)

    def fail_run(self, reason: str, *, source_used: str | None = None, fallback_chain: list[str] | None = None, warnings: list[str] | None = None, coverage: dict[str, bool] | None = None, mode_kind: str | None = None) -> None:
        self.advance_run(
            "Failed",
            source_used=source_used,
            fallback_chain=fallback_chain,
            warnings=warnings,
            coverage=coverage,
            mode_kind=mode_kind,
        )
        with self._run_state_lock:
            self._run_state.status = "failed"
            self._run_state.failure_reason = reason

    def complete_run(self, stored: StoredRecord, *, source_mode: str) -> None:
        source_path = self.source_path(stored.record, stored.raw_payload)
        self.advance_run(
            "Completed",
            source_used=source_path["used"],
            fallback_chain=source_path["fallback_chain"],
            coverage=source_path["coverage"],
            mode_kind=source_path["mode_kind"],
            warnings=source_path["warnings"],
        )
        with self._run_state_lock:
            self._run_state.status = "success"
            self._run_state.source_mode_requested = source_mode
            self._run_state.failure_reason = None
            self._run_state.latest_scan_id = stored.record.scan_id

    def run_state_payload(self) -> dict[str, Any]:
        with self._run_state_lock:
            state = RunState(
                status=self._run_state.status,
                current_ticker=self._run_state.current_ticker,
                source_mode_requested=self._run_state.source_mode_requested,
                current_step=self._run_state.current_step,
                last_completed_step=self._run_state.last_completed_step,
                completed_steps=list(self._run_state.completed_steps),
                source_used=self._run_state.source_used,
                fallback_chain=list(self._run_state.fallback_chain),
                coverage=dict(self._run_state.coverage),
                missing_context=list(self._run_state.missing_context),
                mode_kind=self._run_state.mode_kind,
                warnings=list(self._run_state.warnings),
                failure_reason=self._run_state.failure_reason,
                latest_scan_id=self._run_state.latest_scan_id,
                last_run_timestamp=self._run_state.last_run_timestamp,
            )

        return {
            "status": state.status,
            "current_ticker": state.current_ticker,
            "source_mode_requested": state.source_mode_requested,
            "current_step": state.current_step,
            "last_completed_step": state.last_completed_step,
            "completed_steps": state.completed_steps,
            "source_used": state.source_used,
            "fallback_chain": state.fallback_chain,
            "mode_kind": state.mode_kind,
            "timeframe_coverage": state.coverage,
            "coverage_text": self._coverage_text(state.coverage),
            "missing_context": state.missing_context,
            "warnings": state.warnings,
            "failure_reason": state.failure_reason,
            "latest_scan_id": state.latest_scan_id,
            "last_run_timestamp": state.last_run_timestamp,
        }

    def settings_payload(
        self,
        *,
        host: str,
        port: int,
        current_config: ScanConfig,
    ) -> dict[str, Any]:
        active_webhook_url = self.public_webhook_url or f"http://{host}:{port}/webhook"
        return {
            "mode": "webhook-first",
            "demo_replay_enabled": True,
            "webhook_enabled": True,
            "webhook_endpoint": f"http://{host}:{port}/webhook",
            "public_webhook_url": self.public_webhook_url,
            "active_webhook_url": active_webhook_url,
            "gui_url": f"http://{host}:{port}/",
            "config_dir": str(self.config_dir),
            "override_path": str(self.override_path) if self.override_path is not None else None,
            "log_path": str(self.log_path) if self.log_path is not None else None,
            "export_dir": str(self.export_dir) if self.export_dir is not None else None,
            "record_count": len(self._records),
            "direction": "long",
            "supported_market": "US",
            "editable_settings": {
                "trend_filter": {
                    "minimum_trend_strength_score": current_config.defaults.get("trend_filter", {}).get(
                        "minimum_trend_strength_score"
                    ),
                    "minimum_slope_pct": current_config.defaults.get("trend_filter", {}).get("minimum_slope_pct"),
                },
                "compression": {
                    "maximum_pullback_depth_pct": current_config.defaults.get("compression", {}).get(
                        "maximum_pullback_depth_pct"
                    ),
                    "minimum_range_contraction_pct": current_config.defaults.get("compression", {}).get(
                        "minimum_range_contraction_pct"
                    ),
                    "minimum_volatility_contraction_pct": current_config.defaults.get("compression", {}).get(
                        "minimum_volatility_contraction_pct"
                    ),
                },
                "breakout_trigger": {
                    "breakout_buffer_pct": current_config.defaults.get("breakout_trigger", {}).get("breakout_buffer_pct"),
                    "minimum_breakout_range_vs_base_avg": current_config.defaults.get("breakout_trigger", {}).get(
                        "minimum_breakout_range_vs_base_avg"
                    ),
                    "minimum_relative_volume": current_config.defaults.get("breakout_trigger", {}).get(
                        "minimum_relative_volume"
                    ),
                },
                "trap_risk": {
                    "maximum_distance_from_trend_ref_pct": current_config.defaults.get("trap_risk", {}).get(
                        "maximum_distance_from_trend_ref_pct"
                    ),
                    "maximum_rejection_wick_pct": current_config.defaults.get("trap_risk", {}).get(
                        "maximum_rejection_wick_pct"
                    ),
                    "minimum_overhead_clearance_pct": current_config.defaults.get("trap_risk", {}).get(
                        "minimum_overhead_clearance_pct"
                    ),
                },
                "scoring": {
                    "trend_alignment": current_config.scoring.get("scoring", {}).get("weights", {}).get("trend_alignment"),
                    "squeeze_quality": current_config.scoring.get("scoring", {}).get("weights", {}).get("squeeze_quality"),
                    "breakout_impulse": current_config.scoring.get("scoring", {}).get("weights", {}).get("breakout_impulse"),
                    "path_quality": current_config.scoring.get("scoring", {}).get("weights", {}).get("path_quality"),
                    "trap_risk_penalty": current_config.scoring.get("scoring", {}).get("weights", {}).get(
                        "trap_risk_penalty"
                    ),
                },
            },
        }

    def health_payload(self, *, host: str, port: int) -> dict[str, Any]:
        return {
            "ok": True,
            "app_status": "running",
            "webhook_status": "listening",
            "webhook_endpoint": f"http://{host}:{port}/webhook",
            "record_count": len(self._records),
        }
