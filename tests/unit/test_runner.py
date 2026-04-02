from pathlib import Path

from src.scanner.models import MarketDataBundle, ScanConfig, ScanStatus, SymbolContext
from src.scanner.runner import ScanRunner
from src.services.config_loader import load_scan_config
from src.services.logging import SignalLogger
from src.services.market_data import MarketDataProvider, NullMarketDataProvider
from tests.unit.conftest import load_multi_timeframe_bundle


class FixtureMarketDataProvider(MarketDataProvider):
    def __init__(self, bundle: MarketDataBundle) -> None:
        self.bundle = bundle

    def get_symbol_data(self, symbol_context: SymbolContext) -> MarketDataBundle:
        _ = symbol_context
        return self.bundle


def _runner_config() -> ScanConfig:
    config = load_scan_config("config")
    defaults = dict(config.defaults)
    defaults["trend_filter"] = {
        **config.defaults.get("trend_filter", {}),
        "moving_average_periods": {"fast": 1, "slow": 2},
        "require_price_above_fast_ma": False,
        "require_higher_high_higher_low_structure": False,
    }
    return ScanConfig(defaults=defaults, scoring=config.scoring, universe=config.universe)


def test_runner_returns_stable_scaffold_record(tmp_path) -> None:
    runner = ScanRunner(
        config=_runner_config(),
        market_data_provider=NullMarketDataProvider(),
        signal_logger=SignalLogger(log_path=tmp_path / "signals.log"),
    )
    record = runner.run_symbol(SymbolContext(symbol="NVDA"))
    assert record.symbol == "NVDA"
    assert record.status in {ScanStatus.SKIPPED, ScanStatus.REJECTED, ScanStatus.NO_TRADE, ScanStatus.QUALIFIED}
    assert "trend_filter" in record.module_results
    assert record.to_dict()["explanations"]["summary"]


def test_runner_maps_qualified_record_fields_from_module_outputs(tmp_path, fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_trap_risk_clean.json")
    runner = ScanRunner(
        config=_runner_config(),
        market_data_provider=FixtureMarketDataProvider(bundle),
        signal_logger=SignalLogger(log_path=tmp_path / "signals.log"),
    )
    record = runner.run_symbol(SymbolContext(symbol="NVDA"))
    assert record.status == ScanStatus.QUALIFIED
    assert record.setup_window.compression_start is not None
    assert record.setup_window.compression_end is not None
    assert record.setup_window.trigger_time is not None
    assert record.levels.compression_high is not None
    assert record.levels.compression_low is not None
    assert record.levels.trigger_level is not None
    assert record.levels.breakout_price is not None
    assert record.explanations.summary
    assert record.scores.total > 0.0


def test_runner_serializes_no_trade_record_cleanly(tmp_path, fixture_dir: Path) -> None:
    bundle = load_multi_timeframe_bundle(fixture_dir / "daily_hourly_5m_trap_risk_overhead.json")
    runner = ScanRunner(
        config=_runner_config(),
        market_data_provider=FixtureMarketDataProvider(bundle),
        signal_logger=SignalLogger(log_path=tmp_path / "signals.log"),
    )
    record = runner.run_symbol(SymbolContext(symbol="AMD"))
    payload = record.to_dict()
    assert record.status == ScanStatus.NO_TRADE
    assert payload["status"] == "no_trade"
    assert payload["levels"]["breakout_price"] is not None
    assert payload["explanations"]["no_trade_reason"]
