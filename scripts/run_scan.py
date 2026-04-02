from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.source_manager import ProviderSelectionResult, SourceManager
from src.scanner.models import ScanConfig, SymbolContext
from src.scanner.runner import ScanRunner
from src.services.config_loader import load_scan_config
from src.services.logging import SignalLogger
from src.services.market_data import (
    FixtureMarketDataProvider,
    MarketDataProvider,
    TwelveDataMarketDataProvider,
    YahooFinanceMarketDataProvider,
)
from src.utils.validation import validate_scan_record


def _build_provider(provider_name: str, fixture_path: Path) -> tuple[str, MarketDataProvider]:
    if provider_name == "fixture":
        provider = FixtureMarketDataProvider(fixture_path)
        provider.source_name = "fixture"
        return "fixture", provider
    if provider_name == "yahoo":
        provider = YahooFinanceMarketDataProvider()
        provider.source_name = "yahoo"
        return "yahoo", provider
    if provider_name == "twelvedata":
        provider = TwelveDataMarketDataProvider()
        provider.source_name = "twelvedata"
        return "twelvedata", provider
    raise ValueError(f"Unsupported provider: {provider_name}")


def _select_provider(provider_name: str, fixture_path: Path, symbol: str) -> ProviderSelectionResult:
    if provider_name != "auto":
        selected_name, provider = _build_provider(provider_name, fixture_path)
        bundle = provider.get_symbol_data(SymbolContext(symbol=symbol))
        return ProviderSelectionResult(
            selected_name=selected_name,
            bundle=bundle,
            fallback_chain=[],
            warnings_by_provider={selected_name: list(bundle.warnings)},
        )

    manager = SourceManager()
    providers = [_build_provider(candidate, fixture_path) for candidate in ("twelvedata", "yahoo")]
    return manager.select_provider(SymbolContext(symbol=symbol), providers)


def build_runner(
    *,
    fixture_path: Path,
    log_path: Path | None = None,
    config_override_path: Path | None = None,
    provider_name: str = "fixture",
) -> ScanRunner:
    config = load_scan_config(ROOT / "config", override_path=config_override_path)
    selected_name, market_data_provider = _build_provider(provider_name, fixture_path)
    return ScanRunner(
        config=ScanConfig(defaults=config.defaults, scoring=config.scoring, universe=config.universe),
        market_data_provider=market_data_provider,
        signal_logger=SignalLogger(log_path=log_path),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a fixture-backed demo scan.")
    parser.add_argument(
        "--fixture",
        default=str(ROOT / "tests" / "fixtures" / "daily_hourly_5m_trap_risk_clean.json"),
        help="Path to a multi-timeframe fixture JSON file.",
    )
    parser.add_argument(
        "--provider",
        choices=("fixture", "yahoo", "twelvedata", "auto"),
        default="fixture",
        help="Market data source. Defaults to fixture-backed runs for safety.",
    )
    parser.add_argument("--symbol", default="NVDA", help="Symbol to evaluate.")
    parser.add_argument("--output", help="Optional path to write the serialized ScanRecord JSON.")
    parser.add_argument(
        "--config-override",
        help="Optional override YAML for demo-specific config adjustments, for example config/demo.yaml.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fixture_path = Path(args.fixture)
    output_path = Path(args.output) if args.output else None
    config_override_path = Path(args.config_override) if args.config_override else None

    if args.provider == "auto":
        selection = _select_provider(args.provider, fixture_path, args.symbol)
        if selection.selected_name == "auto_failed":
            print("provider_used: auto_failed")
            print(f"providers_tried: {', '.join(selection.fallback_chain) if selection.fallback_chain else 'none'}")
            print(f"fallback_chain: {', '.join(selection.fallback_chain) if selection.fallback_chain else 'none'}")
            print("daily_bars: 0")
            print("hourly_bars: 0")
            print("intraday_5m_bars: 0")
            warning_count = sum(len(warnings) for warnings in selection.warnings_by_provider.values())
            print(f"warnings_count: {warning_count}")
            for provider_name, warnings in selection.warnings_by_provider.items():
                if not warnings:
                    print(f"provider_warning[{provider_name}]: none")
                    continue
                for warning in warnings:
                    print(f"provider_warning[{provider_name}]: {warning}")
            print(f"summary: {selection.failure_reason or 'No real provider returned complete daily, hourly, and 5m data.'}")
            return 1
        selected_provider = selection.selected_name
        market_data = selection.bundle
        fallback_chain = selection.fallback_chain
        config = load_scan_config(ROOT / "config", override_path=config_override_path)
        single_bundle_provider = type(
            "SingleBundleProvider",
            (),
            {
                "source_name": selected_provider,
                "fallback_chain": fallback_chain,
                "get_symbol_data": lambda self, symbol_context: market_data,
            },
        )()
        runner = ScanRunner(
            config=ScanConfig(defaults=config.defaults, scoring=config.scoring, universe=config.universe),
            market_data_provider=single_bundle_provider,
            signal_logger=SignalLogger(log_path=None),
        )
        record = runner.run_symbol(SymbolContext(symbol=args.symbol))
        validate_scan_record(record)
        print(f"provider_used: {selected_provider}")
        print(f"providers_tried: {', '.join([*fallback_chain, selected_provider]) if fallback_chain else selected_provider}")
        print(f"fallback_chain: {', '.join(fallback_chain) if fallback_chain else 'none'}")
        print(f"daily_bars: {record.snapshot.daily.get('bar_count', 0)}")
        print(f"hourly_bars: {record.snapshot.hourly.get('bar_count', 0)}")
        print(f"intraday_5m_bars: {record.snapshot.intraday_5m.get('bar_count', 0)}")
        print(f"warnings_count: {len(record.debug.data_quality_warnings)}")
        for warning in record.debug.data_quality_warnings:
            print(f"warning: {warning}")
        print(f"symbol: {record.symbol}")
        print(f"status: {record.status.value}")
        print(f"total_score: {record.scores.total}")
        print(f"summary: {record.explanations.summary}")
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0

    runner = build_runner(
        fixture_path=fixture_path,
        config_override_path=config_override_path,
        provider_name=args.provider,
    )
    record = runner.run_symbol(SymbolContext(symbol=args.symbol))
    validate_scan_record(record)

    print(f"provider_used: {args.provider}")
    print(f"providers_tried: {args.provider}")
    print("fallback_chain: none")
    print(f"daily_bars: {record.snapshot.daily.get('bar_count', 0)}")
    print(f"hourly_bars: {record.snapshot.hourly.get('bar_count', 0)}")
    print(f"intraday_5m_bars: {record.snapshot.intraday_5m.get('bar_count', 0)}")
    print(f"warnings_count: {len(record.debug.data_quality_warnings)}")
    for warning in record.debug.data_quality_warnings:
        print(f"warning: {warning}")
    print(f"symbol: {record.symbol}")
    print(f"status: {record.status.value}")
    print(f"total_score: {record.scores.total}")
    print(f"summary: {record.explanations.summary}")

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
