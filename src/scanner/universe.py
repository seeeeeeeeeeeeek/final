from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class UniverseFilterResult:
    symbol: str
    is_eligible: bool
    reasons: list[str]


def screen_symbol(symbol: str, metadata: dict[str, Any], universe_config: dict[str, Any]) -> UniverseFilterResult:
    """Apply narrow V1 universe constraints using provided metadata only."""
    rules = universe_config.get("universe", {})
    reasons: list[str] = []

    price = float(metadata.get("price", 0.0))
    avg_volume = int(metadata.get("avg_daily_volume", 0))
    avg_dollar_volume = float(metadata.get("avg_daily_dollar_volume", 0.0))
    security_type = str(metadata.get("security_type", "unknown")).lower()
    exchange = str(metadata.get("exchange", "unknown")).upper()

    if price < float(rules.get("minimum_price", 0.0)):
        reasons.append("Price below minimum universe threshold.")
    if avg_volume < int(rules.get("minimum_avg_daily_volume", 0)):
        reasons.append("Average daily volume below minimum universe threshold.")
    if avg_dollar_volume < float(rules.get("minimum_avg_daily_dollar_volume", 0.0)):
        reasons.append("Average daily dollar volume below minimum universe threshold.")
    if security_type in {item.lower() for item in rules.get("exclude_security_types", [])}:
        reasons.append("Security type excluded from V1 universe.")
    if exchange not in set(rules.get("allowed_exchanges", [])):
        reasons.append("Exchange not allowed for V1 universe.")

    return UniverseFilterResult(symbol=symbol, is_eligible=not reasons, reasons=reasons)
