# TradingView Webhook Contract

This document defines the TradingView alert JSON contract for the local webhook receiver. Field names and types must stay aligned with the Python receiver in `src/services/webhook_models.py`.

## Endpoint

`POST /webhook`

Content type:

`application/json`

## Required Fields

| Field | Type | Description |
| --- | --- | --- |
| `symbol` | string | Ticker symbol, for example `NVDA` |
| `exchange` | string | Exchange code or venue label, for example `NASDAQ` |
| `timeframe` | string | Alert timeframe label, for example `5m` |
| `timestamp` | string | ISO-8601 UTC timestamp, for example `2026-04-01T13:35:00Z` |
| `close` | number | Alert-bar close price |
| `trend_pass` | boolean | TradingView-side trend condition result |
| `compression_pass` | boolean | TradingView-side compression condition result |
| `breakout_pass` | boolean | TradingView-side breakout condition result |
| `trap_risk_elevated` | boolean | TradingView-side trap-risk flag |

## Optional Fields

| Field | Type | Description |
| --- | --- | --- |
| `compression_high` | number | Compression high reference |
| `compression_low` | number | Compression low reference |
| `trigger_level` | number | Breakout trigger level |
| `breakout_price` | number | Breakout execution/reference price |
| `breakout_range_vs_base_avg` | number | Breakout expansion multiple |
| `relative_volume` | number | Relative volume ratio |
| `rejection_wick_pct` | number | Breakout rejection wick percentage |
| `overhead_clearance_pct` | number | Clearance to nearest overhead resistance |

## Notes

- Required booleans must be sent as real JSON booleans, not quoted strings.
- Optional metrics may be omitted when unavailable.
- The receiver does not fetch bars in this step. It only validates and maps the payload.
- Field names are case-sensitive.

## Minimal Valid Payload

```json
{
  "symbol": "NVDA",
  "exchange": "NASDAQ",
  "timeframe": "5m",
  "timestamp": "2026-04-01T13:35:00Z",
  "close": 944.2,
  "trend_pass": true,
  "compression_pass": true,
  "breakout_pass": true,
  "trap_risk_elevated": false
}
```

## Full Example Payload

```json
{
  "symbol": "NVDA",
  "exchange": "NASDAQ",
  "timeframe": "5m",
  "timestamp": "2026-04-01T13:35:00Z",
  "close": 944.2,
  "trend_pass": true,
  "compression_pass": true,
  "breakout_pass": true,
  "trap_risk_elevated": false,
  "compression_high": 942.1,
  "compression_low": 910.4,
  "trigger_level": 942.15,
  "breakout_price": 944.2,
  "breakout_range_vs_base_avg": 2.2,
  "relative_volume": 1.8,
  "rejection_wick_pct": 9.0,
  "overhead_clearance_pct": 4.0
}
```
