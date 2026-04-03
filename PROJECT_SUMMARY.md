# Project Summary

This file is the cleaned chronological summary of `stocknogs` from the original repository foundation through the current state.

It is meant to answer four questions clearly:

1. What the project was originally built to do
2. What has been added or changed over time
3. What is currently working today
4. What still needs attention next

## 1. Original Product Direction

`stocknogs` started as a local Python-only chart-analysis assistant for liquid US stocks with a narrow, deterministic V1 scope.

The intended V1 boundaries were:

- bullish continuation breakout setups only
- required timeframes: Daily, 1H, 5m
- deterministic scoring and explanation logic
- no broker execution
- no machine learning
- no short-selling logic
- no portfolio management
- no cloud or mobile expansion

The core philosophy from the beginning was:

- reliability over complexity
- explainability over opaque heuristics
- stable structured outputs over ad hoc data blobs

## 2. Initial Backend Foundation

The first major phase built the core scanner pipeline and canonical repo structure.

### 2.1 Core modules

The backend was organized into deterministic analysis modules:

- trend filter
- compression detector
- breakout trigger detector
- trap-risk detection
- quality scoring
- explanation generation
- skip / no-trade reasoning

### 2.2 Scanner orchestration

The scanner pipeline was built around `ScanRecord` and related models in `src/scanner/`.

The early scanner output shape included:

- setup status
- levels
- scores
- flags
- explanations
- metrics

This established the initial engine and testable deterministic behavior.

## 3. Product-Shaped Output Refactor

Once the scanner baseline existed, the project added more product-facing normalized output fields on top of the legacy scanner fields.

### 3.1 New product-oriented fields

The following were introduced:

- `snapshot`
- `thesis`
- `diagnostics`

### 3.2 Why this mattered

This created a cleaner separation between:

- raw scanner internals
- source normalization
- product-facing analysis output
- GUI presentation

It allowed the GUI and later workflow layers to consume stable, normalized structures instead of reaching directly into module-specific output.

## 4. Architectural Cleanup Pass

After the product-shaped fields were introduced, the codebase had real wiring risks. A focused stabilization pass cleaned those up.

### 4.1 Dual-output alignment

The project now had both:

- legacy analysis fields
- product-facing output fields

Alignment tests were added so mirrored values stay consistent and drift is caught early.

### 4.2 Source diagnostics ownership

`SourceManager` became the single source of truth for `diagnostics.source`.

This reduced split responsibility between:

- source normalization
- thesis generation
- scanner flow
- webhook flow

### 4.3 Source fallback cleanup

Fallback-chain propagation was tightened so the app no longer silently lost provider/fallback context.

### 4.4 Thesis conservatism

The thesis layer was made more conservative so it does not overstate bias or target confidence when the data does not truly support it.

### 4.5 GUI/API separation

The original large GUI file was split into clearer layers:

- `gui_api.py`
- `gui_html.py`
- `gui_responses.py`

### 4.6 Diagnostics normalization

Diagnostics structure was normalized across:

- scanner output
- webhook ingestion
- GUI views

## 5. GUI Readability Pass

At this stage, the backend logic worked, but the GUI still felt too developer-oriented.

### 5.1 Main problem

The UI exposed too much engine-shaped output too early:

- raw JSON too high in the page
- technical names too visible
- too many numbers without interpretation
- not enough plain-English guidance

### 5.2 Main UI improvements

The readability pass introduced:

- plain-language summaries
- action-first detail cards
- confidence explanation copy
- timeframe story summaries
- summary-first Home / Live / History / Detail views
- advanced technical data moved lower

### 5.3 New UX principle

The GUI became intentionally organized around:

- simple first
- detailed second
- technical third

## 6. Live Analysis Workflow Pass

Once the GUI became more readable, the next major problem was workflow usability.

### 6.1 Analyze Ticker flow

A real `Analyze Ticker` panel was added so a user can:

- enter a symbol
- choose a source mode
- run analysis without restarting the app
- switch cleanly to newly created records

### 6.2 Run-state model

A lightweight local run-state model was added so the GUI could show:

- idle / running / success / failed
- current ticker
- requested source mode
- current step
- completed steps
- source used
- fallback chain
- coverage / missing context
- failure reason

### 6.3 Better detail structure

The mid-tier detail sections stopped relying on JSON-like dumps for important user-facing information.

Readable summaries were added for:

- timeframe interpretation
- levels summary
- score summary
- strategy match
- pass/fail explanation

## 7. Source Trust Remediation

This was a major turning point for the product.

### 7.1 Problem discovered

The project surfaced fake-looking or stale records too easily in user-facing flows.

An obvious example was a clearly unrealistic `NVDA` price that revealed source trust and provenance problems.

### 7.2 Root issues

The app was mixing or over-trusting:

- replay/demo records
- stale webhook reuse
- insufficiently labeled source paths

### 7.3 Changes made

Explicit source trust classification was added. The system began distinguishing:

- `live_structured`
- `webhook_fresh`
- `webhook_stale`
- `replay_demo`
- `unavailable`

The UI and stored records now expose this more clearly as:

- Live data
- Fresh TradingView alert
- Stored TradingView alert
- Replay/demo
- Unavailable

### 7.4 Trust rules added

- webhook analyze mode only reuses fresh records for the same symbol
- freshness window defaulted to 15 minutes
- auto mode no longer silently reuses replay/demo as fallback
- provenance survives log reloads / GUI restart
- recent-record ranking prefers live and fresher records over lower-trust records

## 8. Public Product Direction Shift

After source-trust issues became clear, the product direction was tightened.

### 8.1 New public source philosophy

The intended user-facing source order became:

1. structured live market data
2. fresh TradingView webhook events
3. bounded fallback sources
4. clear failure when data is not usable

### 8.2 Decision made

Replay/demo should not remain part of the normal public product experience.

That led to the next cleanup.

## 9. Removal of Public Demo / Replay Flow

Replay and demo behavior were intentionally removed from the normal end-user GUI flow.

### 9.1 What changed

- replay/demo was removed from the public Analyze Ticker source choices
- Replay Lab was removed from normal primary navigation
- demo/sample prompts were removed from the ordinary product flow

### 9.2 What stayed

Replay/testing backend paths were intentionally kept for:

- development
- deterministic tests
- internal validation

So replay was not deleted from the codebase, only removed from the normal end-user product path.

## 10. OCR Fallback Foundation

The next bounded fallback added was OCR / screen-read support.

### 10.1 Goal

Provide an honest fallback path that can read visible chart information without pretending to be a structured market-data provider.

### 10.2 What OCR currently does

The OCR service can report status and, when configured, attempt to extract:

- visible ticker
- visible timeframe
- visible current price

### 10.3 What OCR explicitly does not do

- reconstruct OHLCV bars
- infer hidden timeframe context
- fabricate indicators or levels
- pretend it has a full structured market-data view

This kept OCR bounded and trustworthy.

## 11. Real-User Live Source Onboarding

Once source trust was fixed, a new product problem became clear: real users still could not conveniently configure live data from inside the GUI.

### 11.1 What was added

The GUI gained:

- Twelve Data API key entry
- local save / update / clear support
- masked key display after save
- Twelve Data connection test
- user-local source preference controls

### 11.2 Source preference controls added

Users can now configure:

- default source mode
- webhook fallback enabled/disabled
- browser fallback enabled/disabled
- OCR fallback enabled/disabled

### 11.3 Why this mattered

This made the product far more usable for a normal person because they no longer had to rely only on manual shell environment setup.

## 12. Browser Extraction Fallback: Yahoo Phase

The first bounded browser fallback implementation was added after webhook and before OCR in the practical fallback story.

### 12.1 Product role

Browser extraction was defined as:

- bounded
- lower trust than structured live data
- explicit about missing higher timeframe context

It was not allowed to become:

- a generic arbitrary-site scraping framework
- a login automation flow
- a substitute for structured OHLCV

### 12.2 First supported page

The first explicit browser page pattern supported was:

- Yahoo Finance public stock quote pages

### 12.3 What Yahoo browser extraction returned

It could extract quote-level visible data such as:

- requested symbol
- detected symbol heading
- current visible quote price
- page URL attempted
- extraction timing
- missing fields / warnings

### 12.4 What it did not do

- reconstruct bars from page fragments
- infer hidden timeframe context
- pretend quote-page extraction was equivalent to structured live data

## 13. TradingView Browser Extraction Expansion

The next bounded fallback expansion added a TradingView browser adapter for the local workflow you explicitly requested.

### 13.1 Why this expansion happened

Yahoo quote-page extraction was useful but limited.

You wanted a browser fallback that could use your actual TradingView chart workflow while still staying honest about what was and was not truly extracted.

### 13.2 What was added

The browser extraction system was extended with:

- richer `BrowserExtractionResult` metadata
- a second explicit adapter: `TradingViewChartAdapter`
- config-driven TradingView chart URL support
- visible ticker extraction
- visible timeframe extraction
- chart canvas metadata
- price-axis / time-axis presence metadata
- screenshot artifact capture
- selector debug metadata

### 13.3 TradingView extraction design rules

The TradingView adapter was intentionally built under these rules:

- use a configured TradingView chart URL template
- do not hardcode one symbol
- do not hardcode one session URL
- do not pretend chart canvas equals structured market data
- only record visible/extracted UI information

### 13.4 What TradingView browser extraction can currently extract

It can now return, when available:

- requested symbol
- detected visible ticker
- visible timeframe text
- page title
- chart canvas present / size / aria label
- price-axis presence / size metadata
- bottom time-axis presence / size metadata
- selector debug for which selector worked
- saved screenshot artifact paths
- chart region capture status

### 13.5 Artifact capture

TradingView browser extraction can save bounded artifacts under:

- `out/browser_artifacts/tradingview/`

Possible artifacts include:

- full page screenshot
- chart region screenshot
- price-axis screenshot
- bottom time-axis screenshot

### 13.6 What TradingView browser extraction still does not do

It still does not:

- reconstruct OHLCV bars from canvas visuals
- infer hidden indicator values
- extract price-axis text unless truly read
- behave like structured live OHLCV
- widen into a generic arbitrary-site scraping engine

### 13.7 Trust behavior

TradingView browser extraction still remains:

- browser-derived
- partial
- lower trust than structured live data
- lower trust than fresh webhook records

It is not classified as:

- `structured_live`
- `webhook`

It remains browser-extracted partial context.

## 14. Current Architecture State

As of the current checkpoint, the project now has:

- deterministic breakout-analysis backend
- webhook ingestion
- GUI live-analysis flow
- readable summary-first UI
- run-state and progress visibility
- preserved source provenance
- explicit source trust labeling
- bounded OCR fallback foundation
- GUI-managed Twelve Data API key support
- user-local source preferences
- bounded browser extraction fallback
- bounded TradingView browser extraction

## 15. Current Source Hierarchy in Practice

The intended product hierarchy remains:

1. structured live market data
2. fresh TradingView webhook events
3. browser extraction fallback
4. OCR / screen-read fallback
5. clear failure if usable data is unavailable

In practice today:

- structured live uses Twelve Data first and Yahoo as an additional structured provider path
- webhook remains event-driven fresh record reuse only
- browser can use Yahoo quote extraction or configured TradingView chart extraction
- OCR remains bounded visible-text fallback only

## 16. What Is Working Right Now

As of now, the project can legitimately do all of the following:

- run deterministic scan analysis
- ingest TradingView webhook payloads
- store and reload records with provenance
- show simple summary-first GUI views
- run live analysis from the GUI
- track run status and failure reasons
- manage Twelve Data API keys locally in the GUI
- test Twelve Data connectivity
- run bounded browser fallback
- run bounded TradingView browser extraction when configured
- report OCR status honestly
- keep all existing tests passing

## 17. What Is Still Intentionally Unsupported

The following are still intentionally out of scope or bounded:

- broker execution
- order routing
- portfolio management
- shorts
- machine learning
- mobile or cloud deployment
- generic web scraping across arbitrary sites
- login automation
- anti-bot / captcha bypass
- reconstructing hidden OHLCV from screenshots or canvases
- pretending browser or OCR fallbacks are equal to structured live data

## 18. What Still Needs Focus

The major remaining work is still concentrated on real-data capture quality and product hardening, not widening product scope.

Main follow-up areas:

- validate the structured live path with real user Twelve Data keys
- validate the TradingView browser adapter on real local chart pages
- refine TradingView selectors only where live validation proves necessary
- deepen OCR setup in a bounded way:
  - capture input
  - region mapping
  - richer OCR diagnostics
- continue simplifying user-facing source trust and missing-context language

## 19. Current Best Next Step

The best next step after this checkpoint is:

1. validate the real live-data path end-to-end with a real saved Twelve Data key
2. validate the TradingView browser adapter on a real local chart session
3. then deepen OCR setup in a bounded way

That keeps the project moving toward a genuinely usable local product without drifting into fake capability or unsupported automation.

## 20. One-Sentence Summary

`stocknogs` began as a deterministic breakout scanner and has evolved into a local, summary-first chart-analysis assistant with structured live data support, fresh webhook reuse, bounded browser extraction, bounded OCR fallback, explicit source trust, and preserved provenance across stored analysis records.
