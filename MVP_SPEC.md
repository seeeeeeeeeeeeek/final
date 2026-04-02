# Breakout Quality Scanner MVP Spec

## Product Focus
This MVP scans for bullish continuation compression breakouts in liquid US stocks and produces ranked, explainable outputs. It is intentionally narrow and excludes execution, short setups, and machine learning.

## Supported Market
- Liquid US stocks only

Suggested baseline universe filters:
- Listed common stocks on major US exchanges
- Minimum configurable average daily dollar volume
- Minimum configurable average daily share volume
- Minimum configurable price floor
- Exclude ETFs, warrants, rights, preferreds, and OTC symbols in V1

## Supported Direction
- Bullish continuation breakouts only

## Timeframes
- Daily: primary trend and context
- 1H: intermediate compression structure and trend maintenance
- 5m: trigger confirmation and breakout path quality

## Exact Setup Definition For A Compression Breakout
A valid V1 setup is a bullish continuation breakout where price is already in a higher timeframe uptrend, then forms a constructive pause or squeeze, then breaks out with expansion.

### Required Conditions
1. Higher timeframe trend is bullish.
2. Price has an identifiable prior impulse leg before the compression.
3. Compression forms above a configurable higher timeframe support reference, such as rising moving averages or prior breakout area.
4. Compression shows contracting range and restrained pullback depth relative to the prior impulse.
5. Breakout occurs through the compression high or defined trigger level.
6. Breakout candle and immediate follow-through show expansion in range, momentum, or volume relative to the compression regime.
7. Trap-risk conditions do not exceed configured tolerance.

### Compression Characteristics
Compression in V1 should be defined using configurable thresholds across both daily and 1H context:
- Bar ranges contract over a minimum number of bars.
- Pullbacks remain shallow relative to the prior impulse.
- Local lows do not show severe trend damage.
- Volatility compresses versus recent baseline.
- Price remains structurally near the upper half of the base, or reclaims it before trigger.
- Optional volume dry-up during the squeeze can improve score but should not be mandatory in V1.

### Breakout Trigger Characteristics
The trigger should represent transition from compression to expansion:
- Price breaks above the defined compression high or trigger threshold.
- Range expansion exceeds a configurable multiple of recent compression-bar range.
- Relative volume or participation expansion is favorable if volume data is available and enabled.
- 5m path should avoid immediate failed breakout behavior, such as sharp rejection back into the base.

## Feature List

### 1. Higher Timeframe Trend Filter
Purpose:
Determine whether the symbol is in a bullish continuation environment worth scanning.

Suggested V1 checks:
- Daily moving average alignment or slope confirmation
- Price above configurable trend reference(s)
- Higher highs / higher lows or equivalent structural trend test
- No major recent breakdown invalidation

### 2. Compression Detector
Purpose:
Detect constructive pause structures after an impulse leg.

Suggested V1 checks:
- Minimum and maximum compression length
- Range contraction across the base
- Pullback depth constraint
- Volatility contraction relative to lookback
- Position of price within the base

### 3. Breakout Trigger Detector
Purpose:
Identify the actual breakout event from the compression.

Suggested V1 checks:
- Break above compression high
- Minimum breakout expansion threshold
- Optional volume confirmation
- 5m confirmation window for follow-through

### 4. Breakout Quality Score
Purpose:
Rank candidates using interpretable sub-scores.

Suggested score components:
- Trend alignment score
- Squeeze quality score
- Breakout impulse score
- Path quality score
- Trap-risk penalty

Output:
- Normalized total score
- Component scores
- Ranked ordering

### 5. Trap-Risk Detector
Purpose:
Identify signals likely to fail or trap late buyers.

Suggested V1 checks:
- Breakout too extended from trend reference
- Breakout directly into nearby overhead resistance
- Excessive wick/rejection on breakout candle
- Weak follow-through after trigger
- Expansion without prior constructive compression
- Abnormal gap behavior if configured

### 6. Explanation Generator
Purpose:
Produce concise, structured reasons for why a candidate qualified and how it was scored.

Output examples:
- "Daily trend aligned; 1H base tightened over 9 bars; 5m breakout expanded with favorable follow-through."
- "High score due to shallow pullback, strong range expansion, and low rejection."

### 7. Skip / No-Trade Reason Generator
Purpose:
Explain why a symbol did not qualify or why an otherwise valid breakout is not actionable.

Output examples:
- "Skipped: daily trend filter failed."
- "No-trade: breakout triggered but trap risk elevated due to immediate rejection and nearby resistance."

## Data Schema For Scanner Outputs
Suggested canonical output object:

```json
{
  "scan_id": "2026-04-01T13:35:00Z",
  "symbol": "NVDA",
  "market": "US",
  "direction": "long",
  "status": "qualified",
  "timestamp_utc": "2026-04-01T13:35:00Z",
  "timeframes": {
    "trend": "1D",
    "setup": "1H",
    "trigger": "5m"
  },
  "setup_window": {
    "compression_start": "2026-03-25T13:30:00Z",
    "compression_end": "2026-04-01T13:30:00Z",
    "trigger_time": "2026-04-01T13:35:00Z"
  },
  "levels": {
    "compression_high": 942.10,
    "compression_low": 910.40,
    "trigger_level": 942.15,
    "breakout_price": 944.20,
    "nearest_overhead_resistance": 968.00
  },
  "metrics": {
    "prior_impulse_pct": 8.4,
    "compression_depth_pct": 3.1,
    "compression_length_bars": 11,
    "range_contraction_pct": 42.0,
    "volatility_contraction_pct": 35.0,
    "breakout_range_vs_base_avg": 2.2,
    "relative_volume": 1.8,
    "distance_from_trend_ref_pct": 4.0,
    "rejection_wick_pct": 9.0
  },
  "scores": {
    "total": 86.0,
    "trend_alignment": 18.0,
    "squeeze_quality": 24.0,
    "breakout_impulse": 22.0,
    "path_quality": 17.0,
    "trap_risk_penalty": -5.0
  },
  "flags": {
    "daily_trend_pass": true,
    "compression_pass": true,
    "trigger_pass": true,
    "trap_risk_elevated": false,
    "volume_confirmation_used": true
  },
  "explanations": {
    "summary": "Daily uptrend intact; 1H base tightened with shallow pullback; 5m breakout expanded cleanly.",
    "reasons": [
      "Price held above daily trend reference.",
      "1H range and volatility contracted through the base.",
      "5m breakout cleared the base high with strong expansion."
    ],
    "skip_reason": null,
    "no_trade_reason": null
  },
  "debug": {
    "config_version": "v1-defaults",
    "data_quality_warnings": []
  }
}
```

Rejected or skipped symbols should use the same top-level schema where practical, with `status` values such as `skipped`, `rejected`, or `no_trade`, and with populated reason fields.

## Configuration Options
- Universe filters
  - minimum price
  - minimum average daily volume
  - minimum average daily dollar volume
  - include or exclude ETFs
- Trend filter thresholds
  - moving average periods
  - minimum slope
  - minimum trend strength score
- Compression thresholds
  - minimum base bars
  - maximum base bars
  - maximum pullback depth
  - minimum range contraction
  - minimum volatility contraction
- Trigger thresholds
  - breakout buffer above compression high
  - minimum breakout expansion
  - confirmation bar count
  - optional relative volume threshold
- Trap-risk thresholds
  - maximum distance from trend reference
  - maximum rejection wick percentage
  - minimum overhead clearance
  - failed follow-through tolerance
- Scoring weights
  - trend alignment weight
  - squeeze quality weight
  - breakout impulse weight
  - path quality weight
  - trap-risk penalty weight
- Logging options
  - log level
  - include per-module metrics
  - persist debug payloads

## Acceptance Criteria For Each Module

### Higher Timeframe Trend Filter
- Correctly classifies a clear daily uptrend as pass using configured rules.
- Correctly rejects symbols with broken or sideways higher timeframe structure when below threshold.
- Returns both pass/fail and supporting metrics used for the decision.

### Compression Detector
- Detects a valid tightening base after a prior impulse in representative bullish examples.
- Rejects wide, loose, or excessively deep pullbacks.
- Returns measurable properties including length, depth, contraction, and position in range.

### Breakout Trigger Detector
- Identifies break above compression high only when trigger conditions are met.
- Rejects marginal or premature breaks without required expansion.
- Returns trigger time, trigger level, breakout price, and expansion metrics.

### Breakout Quality Score
- Produces deterministic scores from the same input data and config.
- Exposes all component scores and final total.
- Ranks stronger example setups above weaker but still valid setups.

### Trap-Risk Detector
- Flags setups with material rejection, extension, nearby overhead resistance, or weak follow-through.
- Does not invalidate otherwise strong examples unless configured thresholds are exceeded.
- Returns explicit risk flags and penalty contributions.

### Explanation Generator
- Produces concise, structured explanations for qualified signals.
- Explanation text must map to actual module outputs rather than inferred narrative.
- No missing explanation field for qualified records.

### Skip / No-Trade Reason Generator
- Produces at least one clear primary reason for skipped or no-trade outcomes.
- Reasons must reference the failed module or threshold family.
- No skipped or rejected output should be emitted without a reason field.

## Suggested Folder Structure For The Future Codebase
```text
stocknogs/
  docs/
    PRD.md
    MVP_SPEC.md
    AGENTS.md
  config/
    defaults.yaml
    scoring.yaml
    universe.yaml
  data/
    samples/
    fixtures/
  src/
    scanner/
      __init__.py
      runner.py
      universe.py
      models.py
    modules/
      trend_filter.py
      compression.py
      breakout_trigger.py
      quality_score.py
      trap_risk.py
      explanation.py
      skip_reasons.py
    services/
      market_data.py
      logging.py
      config_loader.py
    utils/
      timeframes.py
      math.py
      validation.py
  tests/
    unit/
    integration/
    fixtures/
  scripts/
    run_scan.py
    backfill_samples.py
  logs/
  README.md
```
