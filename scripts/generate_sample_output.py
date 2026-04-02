from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_scan import build_runner
from src.scanner.models import SymbolContext
from src.utils.validation import validate_scan_record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate the sample scan output from a fixture-backed run.")
    parser.add_argument(
        "--fixture",
        default=str(ROOT / "tests" / "fixtures" / "daily_hourly_5m_trap_risk_clean.json"),
        help="Path to a multi-timeframe fixture JSON file.",
    )
    parser.add_argument("--symbol", default="NVDA", help="Symbol to evaluate.")
    parser.add_argument(
        "--output",
        default=str(ROOT / "data" / "samples" / "sample_scan_output.json"),
        help="Path to write the sample output JSON.",
    )
    parser.add_argument(
        "--config-override",
        help="Optional override YAML for demo-specific config adjustments, for example config/demo.yaml.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_override_path = Path(args.config_override) if args.config_override else None
    runner = build_runner(fixture_path=Path(args.fixture), config_override_path=config_override_path)
    record = runner.run_symbol(SymbolContext(symbol=args.symbol))
    validate_scan_record(record)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
