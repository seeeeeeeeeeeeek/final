import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from src.scanner.models import SymbolContext
from src.scanner.runner import ScanRunner
from scripts.run_scan import _select_provider
from src.services.config_loader import load_scan_config
from src.services.logging import SignalLogger
from src.services.market_data import (
    MarketDataBundle,
    MarketDataSlice,
    NullMarketDataProvider,
    TwelveDataMarketDataProvider,
    YahooFinanceMarketDataProvider,
)
from src.utils.validation import validate_scan_record


def test_scan_pipeline_scaffold_builds_valid_record(tmp_path) -> None:
    config = load_scan_config("config")
    runner = ScanRunner(
        config=config,
        market_data_provider=NullMarketDataProvider(),
        signal_logger=SignalLogger(log_path=tmp_path / "signals.log"),
    )
    record = runner.run_symbol(SymbolContext(symbol="AAPL"))
    validate_scan_record(record)
    assert record.explanations.summary
    assert record.module_results["trend_filter"].module_name == "trend_filter"


def test_sample_output_shape_matches_current_model_expectations() -> None:
    payload = json.loads(Path("data/samples/sample_scan_output.json").read_text(encoding="utf-8"))
    assert payload["status"] in {"qualified", "skipped", "rejected", "no_trade"}
    assert set(payload["setup_window"]) == {"compression_start", "compression_end", "trigger_time"}
    assert set(payload["levels"]) == {
        "compression_high",
        "compression_low",
        "trigger_level",
        "breakout_price",
        "nearest_overhead_resistance",
    }
    assert set(payload["scores"]) == {
        "total",
        "trend_alignment",
        "squeeze_quality",
        "breakout_impulse",
        "path_quality",
        "trap_risk_penalty",
    }
    assert set(payload["explanations"]) == {"summary", "reasons", "skip_reason", "no_trade_reason"}
    assert set(payload["snapshot"]) == {
        "symbol",
        "source_type",
        "source_confidence",
        "source_used",
        "timestamp_utc",
        "daily",
        "hourly",
        "intraday_5m",
        "intraday_1m",
        "freshness_seconds",
        "latency_ms",
        "fallback_chain",
        "missing_fields",
        "warnings",
    }
    assert set(payload["thesis"]) == {
        "short_term_bias",
        "intraday_bias",
        "swing_bias",
        "short_term_target",
        "intraday_target",
        "swing_target",
        "invalidation",
        "confidence_score",
        "strategy_match",
        "runner_up_strategy",
        "explanation_summary",
        "explanation_reasons",
        "source_used",
    }
    assert set(payload["diagnostics"]) == {"source", "ocr", "strategy", "system"}


def test_generate_sample_output_script_produces_valid_export(tmp_path) -> None:
    output_path = tmp_path / "sample_output.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_sample_output.py",
            "--fixture",
            "tests/fixtures/daily_hourly_5m_trap_risk_clean.json",
            "--symbol",
            "NVDA",
            "--output",
            str(output_path),
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "generated:" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["symbol"] == "NVDA"
    assert payload["status"] in {"qualified", "skipped", "rejected", "no_trade"}
    assert payload["explanations"]["summary"]


def test_generate_sample_output_script_supports_demo_override_and_qualifies(tmp_path) -> None:
    output_path = tmp_path / "qualified_sample_output.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_sample_output.py",
            "--fixture",
            "tests/fixtures/daily_hourly_5m_trap_risk_clean.json",
            "--symbol",
            "NVDA",
            "--config-override",
            "config/demo.yaml",
            "--output",
            str(output_path),
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "generated:" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "qualified"
    assert payload["explanations"]["summary"]


def test_run_scan_script_writes_valid_record_export(tmp_path) -> None:
    output_path = tmp_path / "scan_output.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_scan.py",
            "--fixture",
            "tests/fixtures/daily_hourly_5m_trap_risk_clean.json",
            "--symbol",
            "NVDA",
            "--output",
            str(output_path),
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "symbol: NVDA" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["symbol"] == "NVDA"
    assert payload["scores"]["total"] >= 0.0
    assert payload["explanations"]["summary"]


def test_run_scan_script_supports_demo_override_and_exports_valid_payload(tmp_path) -> None:
    output_path = tmp_path / "qualified_scan_output.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_scan.py",
            "--fixture",
            "tests/fixtures/daily_hourly_5m_trap_risk_clean.json",
            "--symbol",
            "NVDA",
            "--config-override",
            "config/demo.yaml",
            "--output",
            str(output_path),
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "status: qualified" in result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "qualified"
    assert payload["scores"]["total"] >= 0.0


def test_yahoo_provider_maps_historical_payload_into_market_data_bundle() -> None:
    sample_payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1714550400, 1714636800],
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, 101.0],
                                "high": [102.0, 103.0],
                                "low": [99.5, 100.5],
                                "close": [101.5, 102.5],
                                "volume": [1000000, 1100000],
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }
    provider = YahooFinanceMarketDataProvider()
    with patch("src.services.market_data._fetch_json", return_value=sample_payload):
        bundle = provider.get_symbol_data(SymbolContext(symbol="NVDA"))
    assert len(bundle.daily.bars) == 2
    assert len(bundle.hourly.bars) == 2
    assert len(bundle.intraday_5m.bars) == 2
    assert bundle.daily.bars[0]["timestamp_utc"].endswith("Z")
    assert bundle.daily.bars[0]["open"] == 100.0
    assert bundle.daily.bars[0]["volume"] == 1000000


def test_twelvedata_provider_maps_historical_payload_into_market_data_bundle() -> None:
    sample_payload = {
        "meta": {"symbol": "NVDA", "interval": "1day"},
        "values": [
            {"datetime": "2024-05-01 00:00:00", "open": "100", "high": "102", "low": "99", "close": "101", "volume": "1000000"},
            {"datetime": "2024-05-02 00:00:00", "open": "101", "high": "103", "low": "100", "close": "102", "volume": "1100000"},
        ],
        "status": "ok",
    }
    provider = TwelveDataMarketDataProvider(api_key="demo")
    with patch("src.services.market_data._http_json", return_value=sample_payload):
        bundle = provider.get_symbol_data(SymbolContext(symbol="NVDA"))
    assert len(bundle.daily.bars) == 2
    assert len(bundle.hourly.bars) == 2
    assert len(bundle.intraday_5m.bars) == 2
    assert bundle.hourly.bars[0]["timestamp_utc"].endswith("Z")
    assert bundle.hourly.bars[0]["close"] == 101.0


def test_auto_provider_falls_back_from_twelvedata_to_yahoo() -> None:
    empty_bundle = MarketDataBundle(
        daily=MarketDataSlice(timeframe="1D", bars=[]),
        hourly=MarketDataSlice(timeframe="1H", bars=[]),
        intraday_5m=MarketDataSlice(timeframe="5m", bars=[]),
        warnings=["Twelve Data unavailable."],
    )
    full_bundle = MarketDataBundle(
        daily=MarketDataSlice(timeframe="1D", bars=[{"timestamp_utc": "2024-05-01T00:00:00Z", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]),
        hourly=MarketDataSlice(timeframe="1H", bars=[{"timestamp_utc": "2024-05-01T00:00:00Z", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]),
        intraday_5m=MarketDataSlice(timeframe="5m", bars=[{"timestamp_utc": "2024-05-01T00:00:00Z", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]),
        warnings=[],
    )
    with patch.object(TwelveDataMarketDataProvider, "get_symbol_data", return_value=empty_bundle):
        with patch.object(YahooFinanceMarketDataProvider, "get_symbol_data", return_value=full_bundle):
            selection = _select_provider("auto", Path("tests/fixtures/daily_hourly_5m_trap_risk_clean.json"), "NVDA")
    assert selection.selected_name == "yahoo"
    assert selection.bundle is not None
    assert len(selection.bundle.daily.bars) == 1
    assert selection.fallback_chain == ["twelvedata"]


def test_auto_provider_reports_failure_diagnostics_when_all_real_providers_fail() -> None:
    empty_twelve = MarketDataBundle(
        daily=MarketDataSlice(timeframe="1D", bars=[]),
        hourly=MarketDataSlice(timeframe="1H", bars=[]),
        intraday_5m=MarketDataSlice(timeframe="5m", bars=[]),
        warnings=["Twelve Data unavailable."],
    )
    empty_yahoo = MarketDataBundle(
        daily=MarketDataSlice(timeframe="1D", bars=[]),
        hourly=MarketDataSlice(timeframe="1H", bars=[]),
        intraday_5m=MarketDataSlice(timeframe="5m", bars=[]),
        warnings=["Yahoo returned no chart results."],
    )
    with patch.object(TwelveDataMarketDataProvider, "get_symbol_data", return_value=empty_twelve):
        with patch.object(YahooFinanceMarketDataProvider, "get_symbol_data", return_value=empty_yahoo):
            selection = _select_provider("auto", Path("tests/fixtures/daily_hourly_5m_trap_risk_clean.json"), "NVDA")
    assert selection.selected_name == "auto_failed"
    assert selection.fallback_chain == ["twelvedata", "yahoo"]
    assert selection.failure_reason
    assert selection.warnings_by_provider["twelvedata"] == ["Twelve Data unavailable."]
    assert selection.warnings_by_provider["yahoo"] == ["Yahoo returned no chart results."]


def test_run_scan_script_prints_provider_diagnostics(tmp_path) -> None:
    output_path = tmp_path / "scan_output.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_scan.py",
            "--provider",
            "fixture",
            "--fixture",
            "tests/fixtures/daily_hourly_5m_trap_risk_clean.json",
            "--symbol",
            "NVDA",
            "--output",
            str(output_path),
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "provider_used: fixture" in result.stdout
    assert "daily_bars:" in result.stdout
    assert "warnings_count:" in result.stdout
