from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.analysis.source_manager import SourceManager
from src.analysis.thesis_engine import build_thesis
from src.modules.breakout_trigger import evaluate_breakout_trigger
from src.modules.compression import evaluate_compression
from src.modules.explanation import build_explanations
from src.modules.quality_score import evaluate_quality_score
from src.modules.skip_reasons import build_skip_or_no_trade_reason
from src.modules.trap_risk import evaluate_trap_risk
from src.modules.trend_filter import evaluate_trend_filter
from src.scanner.models import (
    DecisionOutcome,
    ScanConfig,
    ScanFlags,
    ScanRecord,
    ScanStatus,
    SymbolContext,
    build_empty_scan_record,
)
from src.services.logging import SignalLogger
from src.services.market_data import MarketDataProvider
from src.utils.validation import validate_scan_record


def _maybe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nearest_overhead_from_metrics(record: ScanRecord) -> float | None:
    overhead = record.metrics.get("nearest_overhead_resistance")
    overhead_value = _maybe_float(overhead)
    if overhead_value is not None:
        return round(overhead_value, 4)
    return None


@dataclass(slots=True)
class ScanRunner:
    config: ScanConfig
    market_data_provider: MarketDataProvider
    signal_logger: SignalLogger

    def run_symbol(self, symbol_context: SymbolContext) -> ScanRecord:
        """Run the V1 pipeline and map module outputs into a stable ScanRecord shape."""
        scan_id = datetime.now(timezone.utc).isoformat()
        record = build_empty_scan_record(
            symbol_context.symbol,
            scan_id=scan_id,
            config_version=self.config.defaults.get("version", "v1-defaults"),
            status=ScanStatus.SKIPPED,
        )
        source_manager = SourceManager()
        provider_name = getattr(
            self.market_data_provider,
            "source_name",
            self.market_data_provider.__class__.__name__.replace("MarketDataProvider", "").lower() or "provider",
        )
        fallback_chain = getattr(self.market_data_provider, "fallback_chain", [])
        market_data, snapshot_result = source_manager.acquire_from_provider(
            symbol_context,
            self.market_data_provider,
            provider_name=provider_name,
            fallback_chain=fallback_chain,
        )
        record.debug.data_quality_warnings.extend(market_data.warnings)
        record.snapshot = snapshot_result.snapshot

        trend_result = evaluate_trend_filter(symbol_context, market_data, self.config.defaults)
        compression_result = evaluate_compression(symbol_context, market_data, self.config.defaults)
        breakout_result = evaluate_breakout_trigger(symbol_context, market_data, self.config.defaults)
        trap_risk_result = evaluate_trap_risk(symbol_context, market_data, self.config.defaults)
        score_result = evaluate_quality_score(
            symbol_context,
            self.config.scoring,
            trend_result,
            compression_result,
            breakout_result,
            trap_risk_result,
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
            volume_confirmation_used=bool(
                self.config.defaults.get("breakout_trigger", {}).get("use_volume_confirmation", False)
            ),
        )
        record.metrics.update(trend_result.metrics)
        record.metrics.update(compression_result.metrics)
        record.metrics.update(breakout_result.metrics)
        record.metrics.update(trap_risk_result.metrics)
        record.setup_window.compression_start = compression_result.metrics.get("compression_start")
        record.setup_window.compression_end = compression_result.metrics.get("compression_end")
        record.setup_window.trigger_time = breakout_result.metrics.get("breakout_timestamp_utc")
        record.levels.compression_high = _maybe_float(compression_result.metrics.get("compression_high"))
        record.levels.compression_low = _maybe_float(compression_result.metrics.get("compression_low"))
        record.levels.trigger_level = _maybe_float(breakout_result.metrics.get("trigger_level"))
        record.levels.breakout_price = _maybe_float(breakout_result.metrics.get("breakout_price"))
        record.levels.nearest_overhead_resistance = _nearest_overhead_from_metrics(record)
        record.scores.total = float(score_result.metrics.get("total", 0.0))
        record.scores.trend_alignment = float(score_result.metrics.get("trend_alignment", 0.0))
        record.scores.squeeze_quality = float(score_result.metrics.get("squeeze_quality", 0.0))
        record.scores.breakout_impulse = float(score_result.metrics.get("breakout_impulse", 0.0))
        record.scores.path_quality = float(score_result.metrics.get("path_quality", 0.0))
        record.scores.trap_risk_penalty = float(score_result.metrics.get("trap_risk_penalty", 0.0))

        if all((trend_result.passed, compression_result.passed, breakout_result.passed)):
            record.status = ScanStatus.QUALIFIED
        if trap_risk_result.outcome == DecisionOutcome.NO_TRADE:
            record.status = ScanStatus.NO_TRADE
        if not trend_result.passed:
            record.status = ScanStatus.SKIPPED
        elif not compression_result.passed or not breakout_result.passed:
            record.status = ScanStatus.REJECTED

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
