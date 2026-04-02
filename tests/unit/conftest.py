from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.scanner.models import MarketDataBundle, MarketDataSlice


@pytest.fixture
def fixture_dir() -> Path:
    return Path("tests/fixtures")


def load_daily_bundle(path: Path) -> MarketDataBundle:
    bars = json.loads(path.read_text(encoding="utf-8"))
    return MarketDataBundle(daily=MarketDataSlice(timeframe="1D", bars=bars))


def load_multi_timeframe_bundle(path: Path) -> MarketDataBundle:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return MarketDataBundle(
        daily=MarketDataSlice(timeframe="1D", bars=payload.get("daily", [])),
        hourly=MarketDataSlice(timeframe="1H", bars=payload.get("hourly", [])),
        intraday_5m=MarketDataSlice(timeframe="5m", bars=payload.get("intraday_5m", [])),
    )
