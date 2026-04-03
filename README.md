# stocknogs

A local multi-timeframe chart-analysis companion for liquid US stocks. The app combines structured live market data, fresh TradingView webhook events, and a local GUI to build a deterministic thesis with bias, confidence, setup status, targets when available, invalidation, and clear diagnostics.

## Product Concept

stocknogs is not a broker or order-routing system. It is a Windows-friendly local analysis assistant that reviews Daily, 1H, and 5m context, then explains what is aligned, what is missing, and why a setup qualified, failed, or became too risky.

Primary outputs:

- Higher-timeframe bias
- Setup status
- Confidence score
- Strategy fit
- Short-term / intraday / swing thesis fields
- Targets and invalidation when they can be derived
- Source diagnostics and fallback visibility

## Quick Start on Another Windows PC

Use only the Windows updater script:

1. Download [`install_or_update_stocknogs.bat`](./install_or_update_stocknogs.bat).
2. Run it on the target Windows machine.
3. The script will clone or update the latest `main` branch into `Desktop\stocknogs`.

Optional custom target folder:

```powershell
install_or_update_stocknogs.bat "C:\Users\YourName\Desktop\stocknogs"
```

Notes:

- Git or GitHub Desktop must already be installed.
- The updater force-syncs an existing `stocknogs` git checkout to the latest remote `main`.
- If `Desktop\stocknogs` exists but is not the expected repo, the updater moves it aside into a timestamped backup and clones fresh.

## Source Priority and Fallback

Source selection is explicit and diagnostics-first.

Priority order:

1. Structured live OHLCV and indicator-ready data
2. Fresh TradingView webhook events
3. OCR/screen-read fallback
4. Clear diagnostic failure if nothing usable is available

Current Phase 1 implementation:

- Twelve Data and Yahoo style structured OHLCV providers remain available
- TradingView webhook payloads normalize into the same internal snapshot model
- Source, fallback chain, freshness, latency, and missing-field diagnostics are attached to records
- OCR screen-read fallback now has a bounded foundation for visible ticker, timeframe, and price extraction only
- OCR does not fabricate OHLCV bars or hidden higher-timeframe context

## Twelve Data Environment Variable Setup

Use environment variables only. Never hardcode or commit API keys.

```powershell
$env:TWELVE_DATA_API_KEY="your_api_key_here"
```

Notes:

- The key is not stored in repo config files.
- The code does not intentionally log the key.

## Run the GUI

Start the local tester GUI:

```powershell
python scripts/run_gui.py
```

Open:

```text
http://127.0.0.1:8080/
```

The GUI serves both the tester interface and the webhook endpoint:

```text
http://127.0.0.1:8080/webhook
```

GUI notes:

- Record history is loaded from the GUI JSONL log on startup.
- Local setting changes are stored in `config/gui_user.yaml` by default.
- The GUI remains Python-only and reuses the same webhook, scoring, explanation, snapshot, thesis, and logging backend paths.
- The interface prioritizes simple summaries first and advanced technical details second.
- Analysis Detail leads with user-readable action summaries, target/invalidation guidance, confidence explanations, and timeframe story before exposing engine-shaped technical output.
- The Live Analysis page includes an `Analyze Ticker` control, source-mode selection, and a run-status panel that shows source path, coverage, fallback chain, and readable failure messages while a run is happening.
- The GUI now separates `Live data`, `Fresh TradingView alert`, and `Stored TradingView alert` results so stale event input is not mistaken for current structured live market analysis.
- Screen-read fallback is shown as a bounded OCR fallback only. It is honest about what it can and cannot read.

## GUI Workflow

Visible GUI pages:

1. Home
2. Live Analysis
3. Analysis Detail
4. Strategy Settings
5. TradingView Setup
6. History
7. Diagnostics

Recommended tester flow:

1. Run `python scripts/run_gui.py`.
2. Open `Live Analysis`, enter a ticker, choose a source mode, and click `Analyze`.
3. Watch the run-status panel to see the requested source, source actually used, fallback chain, coverage, and failures if any.
4. Open `Analysis Detail` to inspect the readable summary, source path, detailed analysis, and advanced diagnostics.
5. Review `History` to confirm persistence across sessions.
6. Open `TradingView Setup` when you are ready to connect a public webhook URL.

Source modes in the GUI:

- `auto`: tries live structured data first, then fresh stored webhook payloads if available, then bounded OCR fallback if configured; it does not fall back to replay/demo records
- `twelvedata`: runs direct live analysis from Twelve Data only
- `webhook`: reuses only fresh already received TradingView webhook records for the requested symbol
- `ocr`: bounded screen-read fallback for visible ticker, timeframe, and price extraction only

## OCR Screen-Read Fallback

OCR is a fallback, not a replacement for structured live market data.

Current OCR foundation:

- local Windows-friendly configuration via `config/ocr_user.yaml`
- reads visible chart information only
- can attempt to extract:
  - ticker symbol
  - timeframe label
  - current visible price
- reports what is missing instead of inventing data

Current OCR limitations:

- it does not reconstruct OHLCV bars from the screen
- it does not infer hidden higher-timeframe context
- it does not claim a full multi-timeframe analysis when only partial chart text is visible
- if OCR is disabled or not configured, the GUI shows a clear readable failure

Internal replay/testing paths still exist for development and automated tests, but they are not part of the normal end-user GUI flow.

Run a single fixture-backed scan from the command line:

```powershell
python scripts/run_scan.py --fixture tests/fixtures/daily_hourly_5m_trap_risk_clean.json --symbol NVDA
```

## TradingView Webhook Setup

Start the local webhook receiver:

```powershell
python scripts/run_webhook_server.py --host 127.0.0.1 --port 8000
```

TradingView should `POST` JSON to:

```text
http://127.0.0.1:8000/webhook
```

Expected JSON shape:

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

TradingView setup steps:

1. Open [`pine/stocknogs_breakout_webhook_template.pine`](./pine/stocknogs_breakout_webhook_template.pine) in TradingView Pine Editor.
2. Add the script to your chart.
3. Create an alert on the indicator.
4. Enable TradingView webhook delivery.
5. Paste your webhook URL, for example `https://your-public-endpoint.example/webhook`.
6. Use the script's dynamic `alert()` message output for the webhook body.

Notes:

- The webhook URL must be publicly reachable by TradingView.
- The local server example in this repo is useful for development, but TradingView cannot reach `127.0.0.1` directly.
- Webhook mode is event-driven. It reuses only fresh TradingView alert payloads for the requested symbol.
- The exact JSON contract is documented in [`docs/tradingview_webhook_contract.md`](./docs/tradingview_webhook_contract.md).

## Run with Real Data

Real structured market data paths currently available:

- `yahoo`: public Yahoo Finance chart data, requires internet access and no API key
- `twelvedata`: Twelve Data historical bars, requires internet access and `TWELVE_DATA_API_KEY`
- `auto`: tries real providers in order, then fresh webhook event reuse, then bounded OCR fallback if configured

Run a one-symbol scan with real Daily, 1H, and 5m data:

```powershell
python scripts/run_scan.py --provider yahoo --symbol NVDA
```

Run with Twelve Data:

```powershell
python scripts/run_scan.py --provider twelvedata --symbol NVDA
```

Run with simple real-provider fallback:

```powershell
python scripts/run_scan.py --provider auto --symbol NVDA
```

Write the real-data scan record to disk:

```powershell
python scripts/run_scan.py --provider yahoo --symbol NVDA --output out/nvda_real_scan.json
```

## Diagnostics and Debugging

Each record now carries first-class diagnostics payloads for:

- Source selection
- Fallback chain
- Timeframe coverage
- Freshness and latency
- Missing fields
- Strategy rule pass/fail context
- Provider warnings
- OCR capture/read warnings when screen-read fallback is attempted

The GUI `Diagnostics` page shows the latest source, strategy, OCR placeholder, and system diagnostics in one place.

## Architecture

- `src/services/`: market data access, webhook handling, GUI API, config loading, and logging
- `src/analysis/`: source normalization and thesis generation
- `src/scanner/`: orchestration and canonical record models
- `src/modules/`: current deterministic strategy modules
- `tests/unit/`: module and engine tests
- `tests/integration/`: end-to-end flow tests for scan, webhook, and GUI paths

## Current Limitations

- Phase 1 adds the normalized snapshot and thesis skeleton, not the full preset engine.
- Targets and invalidation remain rule-light and only use real available structure; missing targets show as `Not available yet`.
- OCR and browser scraping fallback are not implemented yet.
- The app is local-first and Windows-friendly, but not packaged in this step.
- No broker execution, order placement, ML, mobile, or cloud deployment is included.

## Next Build Direction

The next implementation phase should add:

- strategy preset evaluation
- target / invalidation engine
- richer thesis detail views in the GUI
- deeper diagnostics for preset scoring and failure reasons
