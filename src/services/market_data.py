from __future__ import annotations

from abc import ABC, abstractmethod
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode, quote
from urllib.request import urlopen

from src.scanner.models import MarketDataBundle, MarketDataSlice, SymbolContext


class MarketDataProvider(ABC):
    """Abstract provider contract for market data retrieval."""

    @abstractmethod
    def get_symbol_data(self, symbol_context: SymbolContext) -> MarketDataBundle:
        """Return daily, 1H, and 5m market data for a symbol."""


class NullMarketDataProvider(MarketDataProvider):
    """Scaffold provider that returns empty data with an explicit warning."""

    def get_symbol_data(self, symbol_context: SymbolContext) -> MarketDataBundle:
        return MarketDataBundle(
            warnings=[f"No market data provider configured for {symbol_context.symbol}."]
        )


def load_fixture_market_data(path: str | Path) -> MarketDataBundle:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping at fixture path {fixture_path}")
    return MarketDataBundle(
        daily=MarketDataSlice(timeframe="1D", bars=payload.get("daily", [])),
        hourly=MarketDataSlice(timeframe="1H", bars=payload.get("hourly", [])),
        intraday_5m=MarketDataSlice(timeframe="5m", bars=payload.get("intraday_5m", [])),
    )


class FixtureMarketDataProvider(MarketDataProvider):
    """Load market data from a multi-timeframe JSON fixture for deterministic demo runs."""

    def __init__(self, fixture_path: str | Path) -> None:
        self.fixture_path = Path(fixture_path)

    def get_symbol_data(self, symbol_context: SymbolContext) -> MarketDataBundle:
        _ = symbol_context
        bundle = load_fixture_market_data(self.fixture_path)
        return bundle


def _epoch_to_utc_iso(timestamp: int | float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_yahoo_chart_url(symbol: str, *, range_value: str, interval: str) -> str:
    query = urlencode(
        {
            "range": range_value,
            "interval": interval,
            "includePrePost": "false",
            "events": "div,splits",
        }
    )
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"


def _fetch_json(url: str, timeout: float = 20.0) -> dict:
    with urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Expected mapping payload from market data endpoint.")
    return payload


def _http_json(url: str, timeout: float = 20.0) -> dict:
    return _fetch_json(url, timeout=timeout)


def _extract_yahoo_bars(payload: dict) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    chart = payload.get("chart", {})
    error = chart.get("error")
    if error:
        description = error.get("description") or error.get("code") or "Unknown Yahoo Finance error."
        return [], [f"Yahoo Finance returned an error: {description}"]

    results = chart.get("result") or []
    if not results:
        return [], ["Yahoo Finance returned no chart results."]

    result = results[0]
    timestamps = result.get("timestamp") or []
    quote_list = result.get("indicators", {}).get("quote") or []
    if not quote_list:
        return [], ["Yahoo Finance response did not include quote data."]

    quote = quote_list[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    bars: list[dict] = []
    for index, timestamp in enumerate(timestamps):
        bar = {
            "timestamp_utc": _epoch_to_utc_iso(timestamp),
            "open": _to_float(opens[index]) if index < len(opens) else None,
            "high": _to_float(highs[index]) if index < len(highs) else None,
            "low": _to_float(lows[index]) if index < len(lows) else None,
            "close": _to_float(closes[index]) if index < len(closes) else None,
            "volume": _to_int(volumes[index]) if index < len(volumes) else None,
        }
        if None in (bar["timestamp_utc"], bar["open"], bar["high"], bar["low"], bar["close"]):
            warnings.append(f"Skipped malformed Yahoo Finance bar at index {index}.")
            continue
        bars.append(bar)

    if not bars:
        warnings.append("Yahoo Finance returned no complete OHLCV bars after validation.")
    return bars, warnings


class YahooFinanceMarketDataProvider(MarketDataProvider):
    """Historical OHLCV provider backed by Yahoo Finance chart data."""

    def __init__(
        self,
        *,
        daily_range: str = "6mo",
        hourly_range: str = "60d",
        intraday_range: str = "5d",
        timeout: float = 20.0,
    ) -> None:
        self.daily_range = daily_range
        self.hourly_range = hourly_range
        self.intraday_range = intraday_range
        self.timeout = timeout

    def _fetch_timeframe(self, symbol: str, *, range_value: str, interval: str, timeframe: str) -> tuple[MarketDataSlice, list[str]]:
        url = _build_yahoo_chart_url(symbol, range_value=range_value, interval=interval)
        try:
            payload = _fetch_json(url, timeout=self.timeout)
            bars, warnings = _extract_yahoo_bars(payload)
        except Exception as exc:
            return (
                MarketDataSlice(timeframe=timeframe, bars=[]),
                [f"Failed to fetch {timeframe} data for {symbol}: {exc}"],
            )
        return MarketDataSlice(timeframe=timeframe, bars=bars), warnings

    def get_symbol_data(self, symbol_context: SymbolContext) -> MarketDataBundle:
        daily, daily_warnings = self._fetch_timeframe(
            symbol_context.symbol,
            range_value=self.daily_range,
            interval="1d",
            timeframe="1D",
        )
        hourly, hourly_warnings = self._fetch_timeframe(
            symbol_context.symbol,
            range_value=self.hourly_range,
            interval="1h",
            timeframe="1H",
        )
        intraday_5m, intraday_warnings = self._fetch_timeframe(
            symbol_context.symbol,
            range_value=self.intraday_range,
            interval="5m",
            timeframe="5m",
        )
        return MarketDataBundle(
            daily=daily,
            hourly=hourly,
            intraday_5m=intraday_5m,
            warnings=[*daily_warnings, *hourly_warnings, *intraday_warnings],
        )


def _build_twelve_data_url(symbol: str, *, interval: str, apikey: str, outputsize: int) -> str:
    query = urlencode(
        {
            "symbol": symbol,
            "interval": interval,
            "apikey": apikey,
            "format": "JSON",
            "outputsize": outputsize,
            "timezone": "UTC",
            "order": "asc",
        },
        quote_via=quote,
    )
    return f"https://api.twelvedata.com/time_series?{query}"


def _extract_twelve_data_bars(payload: dict) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    if payload.get("status") == "error":
        message = payload.get("message") or "Unknown Twelve Data error."
        return [], [f"Twelve Data returned an error: {message}"]

    values = payload.get("values")
    if not isinstance(values, list):
        return [], ["Twelve Data response did not include values."]

    bars: list[dict] = []
    for index, row in enumerate(values):
        if not isinstance(row, dict):
            warnings.append(f"Skipped malformed Twelve Data row at index {index}.")
            continue
        bar = {
            "timestamp_utc": f"{str(row.get('datetime')).replace(' ', 'T')}Z" if row.get("datetime") else None,
            "open": _to_float(row.get("open")),
            "high": _to_float(row.get("high")),
            "low": _to_float(row.get("low")),
            "close": _to_float(row.get("close")),
            "volume": _to_int(row.get("volume")),
        }
        if None in (bar["timestamp_utc"], bar["open"], bar["high"], bar["low"], bar["close"]):
            warnings.append(f"Skipped malformed Twelve Data bar at index {index}.")
            continue
        bars.append(bar)

    if not bars:
        warnings.append("Twelve Data returned no complete OHLCV bars after validation.")
    return bars, warnings


class TwelveDataMarketDataProvider(MarketDataProvider):
    """Historical OHLCV provider backed by Twelve Data time_series."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        daily_outputsize: int = 180,
        hourly_outputsize: int = 500,
        intraday_outputsize: int = 500,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY")
        self.daily_outputsize = daily_outputsize
        self.hourly_outputsize = hourly_outputsize
        self.intraday_outputsize = intraday_outputsize
        self.timeout = timeout

    def _fetch_timeframe(
        self,
        symbol: str,
        *,
        interval: str,
        outputsize: int,
        timeframe: str,
    ) -> tuple[MarketDataSlice, list[str]]:
        if not self.api_key:
            return (
                MarketDataSlice(timeframe=timeframe, bars=[]),
                ["Twelve Data API key is not configured. Set TWELVE_DATA_API_KEY."],
            )

        url = _build_twelve_data_url(symbol, interval=interval, apikey=self.api_key, outputsize=outputsize)
        try:
            payload = _http_json(url, timeout=self.timeout)
            bars, warnings = _extract_twelve_data_bars(payload)
        except Exception as exc:
            return (
                MarketDataSlice(timeframe=timeframe, bars=[]),
                [f"Failed to fetch {timeframe} data for {symbol} from Twelve Data: {exc}"],
            )
        return MarketDataSlice(timeframe=timeframe, bars=bars), warnings

    def get_symbol_data(self, symbol_context: SymbolContext) -> MarketDataBundle:
        daily, daily_warnings = self._fetch_timeframe(
            symbol_context.symbol,
            interval="1day",
            outputsize=self.daily_outputsize,
            timeframe="1D",
        )
        hourly, hourly_warnings = self._fetch_timeframe(
            symbol_context.symbol,
            interval="1h",
            outputsize=self.hourly_outputsize,
            timeframe="1H",
        )
        intraday_5m, intraday_warnings = self._fetch_timeframe(
            symbol_context.symbol,
            interval="5min",
            outputsize=self.intraday_outputsize,
            timeframe="5m",
        )
        return MarketDataBundle(
            daily=daily,
            hourly=hourly,
            intraday_5m=intraday_5m,
            warnings=[*daily_warnings, *hourly_warnings, *intraday_warnings],
        )
