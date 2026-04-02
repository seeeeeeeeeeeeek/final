# stocknogs

A local multi-timeframe chart-analysis companion for liquid US stocks. The app combines structured live market data, TradingView webhook events, replayable payloads, and a local GUI to build a deterministic thesis with bias, confidence, setup status, targets when available, invalidation, and clear diagnostics.

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

## Source Priority And Fallback
Source selection is explicit and diagnostics-first.

Priority order:
1. Structured live OHLCV and indicator-ready data
2. TradingView webhook events
3. Browser/platform scraping fallback
4. OCR/screen-capture fallback
5. Clear diagnostic failure if nothing usable is available

Current Phase 1 implementation:
- Twelve Data and Yahoo style structured OHLCV providers remain available
- TradingView webhook payloads normalize into the same internal snapshot model
- Source, fallback chain, freshness, latency, and missing-field diagnostics are attached to records
- Browser and OCR fallback are planned, not implemented yet

## Twelve Data Environment Variable Setup
Use environment variables only. Never hardcode or commit API keys.

```powershell
$env:TWELVE_DATA_API_KEY="your_api_key_here"
```

Notes:
- The key is not stored in repo config files.
- The code does not intentionally log the key.

## Install Or Update On Another Windows PC
If you want someone else to install or update the latest repo with one script, use:

- [install_or_update_stocknogs.bat](c:/Users/Apple/Desktop/stocknogs/install_or_update_stocknogs.bat)
- [install_or_update_stocknogs.ps1](c:/Users/Apple/Desktop/stocknogs/install_or_update_stocknogs.ps1)

Recommended simple path:
1. Download `install_or_update_stocknogs.bat`.
2. Run it on the target Windows machine.
3. It will download the latest PowerShell updater from this GitHub repo and then:
   - clone `main` into `Desktop\\stocknogs` if the folder does not exist
   - force-sync an existing `stocknogs` git repo to the latest `origin/main`
   - move a non-git `stocknogs` folder aside into a timestamped backup, then clone fresh

Optional custom target folder:

```powershell
install_or_update_stocknogs.bat "C:\Users\YourName\Desktop\stocknogs"
```

Notes:
- Git or GitHub Desktop must already be installed.
- The updater is intentionally destructive for existing git checkouts: it resets to the latest remote `main` and removes untracked files inside that repo folder.

## Run The GUI
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
- The GUI remains Python-only and reuses the same webhook, replay, scoring, explanation, snapshot, thesis, and logging backend paths.
- The interface now prioritizes simple summaries first and advanced technical details second, so non-technical testers can understand the result before opening diagnostics or raw JSON.
- Analysis Detail and Replay Lab now lead with user-readable action summaries, target/invalidation guidance, confidence explanations, and timeframe story before exposing engine-shaped technical output.
- The Live Analysis page now includes an `Analyze Ticker` control, source-mode selection, and a run-status panel that shows source path, coverage, fallback chain, and readable failure messages while a run is happening.

## GUI Workflow
Visible GUI pages:
1. Home
2. Live Analysis
3. Analysis Detail
4. Replay Lab
5. Strategy Settings
6. TradingView Setup
7. History
8. Diagnostics

Recommended tester flow:
1. Run `python scripts/run_gui.py`.
2. Open `Live Analysis`, enter a ticker, choose a source mode, and click `Analyze`.
3. Watch the run-status panel to see the requested source, source actually used, fallback chain, coverage, and failures if any.
4. Open `Analysis Detail` to inspect the readable summary, source path, detailed analysis, and advanced diagnostics.
5. Use `Replay Lab` when you want deterministic sample runs or webhook-style testing.
6. Review `History` to confirm persistence across sessions.
7. Open `TradingView Setup` when you are ready to connect a public webhook URL.

Source modes in the GUI:
- `auto`: tries live structured data first and falls back through the currently supported local source chain
- `twelvedata`: runs direct live analysis from Twelve Data only
- `webhook`: reuses already received TradingView webhook records for the requested symbol
- `replay`: runs a sample payload through the replay path
- `ocr`: shown as unavailable until OCR fallback exists

## Replay And Testing Flow
- Replay Lab in the GUI accepts TradingView-style JSON and routes it through the same validation and record-building path as `/webhook`.
- Replayed records are written to the same JSONL log and reappear in History on restart.
- Fixture-backed scans remain available for deterministic module and integration testing.

Run a single fixture-backed scan from the command line:

```powershell
python scripts/run_scan.py --fixture tests/fixtures/daily_hourly_5m_trap_risk_clean.json --symbol NVDA
```

Run the same fixture with the demo-qualified override:

```powershell
python scripts/run_scan.py --fixture tests/fixtures/daily_hourly_5m_trap_risk_clean.json --symbol NVDA --config-override config/demo.yaml
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
1. Open [stocknogs_breakout_webhook_template.pine](c:/Users/Apple/Desktop/stocknogs/pine/stocknogs_breakout_webhook_template.pine) in TradingView Pine Editor.
2. Add the script to your chart.
3. Create an alert on the indicator.
4. Enable TradingView webhook delivery.
5. Paste your webhook URL, for example `https://your-public-endpoint.example/webhook`.
6. Use the script's dynamic `alert()` message output for the webhook body.

Notes:
- The webhook URL must be publicly reachable by TradingView.
- The local server example in this repo is useful for development, but TradingView cannot reach `127.0.0.1` directly.
- The exact JSON contract is documented in [tradingview_webhook_contract.md](c:/Users/Apple/Desktop/stocknogs/docs/tradingview_webhook_contract.md).

## Run With Real Data
Real structured market data paths currently available:
- `yahoo`: public Yahoo Finance chart data, requires internet access and no API key
- `twelvedata`: Twelve Data historical bars, requires internet access and `TWELVE_DATA_API_KEY`
- `auto`: tries real providers in order and uses the first one that returns complete Daily, 1H, and 5m coverage

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

Fixture-backed mode remains available:

```powershell
python scripts/run_scan.py --provider fixture --fixture tests/fixtures/daily_hourly_5m_trap_risk_clean.json --symbol NVDA
```

## Diagnostics And Debugging
Each record now carries first-class diagnostics payloads for:
- Source selection
- Fallback chain
- Timeframe coverage
- Freshness and latency
- Missing fields
- Strategy rule pass/fail context
- Provider warnings

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
#   f i n a l  
 
