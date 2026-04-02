from __future__ import annotations

SUPPORTED_TIMEFRAMES = ("1D", "1H", "5m")


def is_supported_timeframe(value: str) -> bool:
    return value in SUPPORTED_TIMEFRAMES
