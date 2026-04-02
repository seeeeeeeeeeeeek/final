# Breakout Quality Scanner PRD

## Product Vision
Build a focused scanner for liquid US stocks that identifies bullish compression-to-expansion continuation setups and ranks them by structural quality, trend alignment, breakout quality, and likelihood of failure. The product should help discretionary and systematic traders narrow a broad universe into a small, explainable watchlist of high-quality continuation candidates.

## Problem Statement
Most breakout tools flag simple price threshold events, such as new highs or range breaks, without distinguishing between clean continuation setups and noisy, late, or failure-prone moves. Traders still spend significant time manually filtering for context:
- Is the stock already in a healthy higher timeframe uptrend?
- Was the pre-breakout base actually constructive compression?
- Did the breakout show real expansion and participation?
- Is the post-breakout path likely tradeable, or does it carry obvious trap risk?

Generic breakout indicators do not reliably answer these questions, which leads to information overload, low signal quality, and inconsistent decision-making.

## Target User
- Active traders focused on liquid US equities
- Swing traders using daily and intraday alignment
- Intraday momentum traders who want daily and 1H context
- Systematic discretionary traders who value explainable scoring over black-box outputs

## Core Use Cases
- Scan a liquid US stock universe each day for bullish continuation breakouts aligned with the daily trend.
- Rank candidate setups by overall breakout quality rather than only by price change.
- Explain why a symbol is ranked highly, including trend context, compression structure, breakout impulse, and trap-risk observations.
- Explain why a symbol was skipped so the user can trust omissions and refine thresholds.
- Use daily, 1H, and 5m context together to validate trend, setup, and trigger quality.
- Review historical scan outputs to compare strong versus weak breakout structures.

## Product Differentiation From Generic Breakout Indicators
- Focuses on continuation structure, not generic level crossing.
- Separates setup quality into interpretable components: trend alignment, squeeze quality, breakout impulse, path quality, and trap risk.
- Uses multi-timeframe logic instead of a single-chart breakout event.
- Produces explicit no-trade and skip reasons, not just positive signals.
- Designed for explainability and auditability, with configurable thresholds and signal logs.
- Optimized for liquid US stocks, avoiding broad cross-asset generalization in V1.

## V1 Scope
- Universe: liquid US stocks only
- Direction: bullish continuation breakouts only
- Timeframes: Daily, 1H, 5m
- Scanner modules:
  - higher timeframe trend filter
  - compression detector
  - breakout trigger detector
  - breakout quality score
  - trap-risk detector
  - explanation generator
  - skip/no-trade reason generator
- Structured output for ranked candidates and rejected candidates
- Configurable thresholds for all major filters and score components
- Logging for all signal decisions and module outputs

## Out-of-Scope Items
- Broker integration or order execution
- Short setups
- Options-specific workflows
- Portfolio construction and position sizing
- Machine learning models or predictive black-box scoring
- Alternative data, fundamentals, news sentiment, or social signals
- Real-time streaming infrastructure beyond what is required to evaluate defined timeframes
- Cross-market support beyond liquid US stocks
- Fully automated strategy deployment

## Success Metrics
- High signal precision on reviewed V1 candidates relative to naive breakout scanners
- Meaningful reduction in manually reviewed symbols per session
- Consistent generation of interpretable reasons for signal and non-signal outcomes
- Stable scanner output across repeated runs with identical inputs
- Low rate of malformed or missing explanation fields in outputs
- Positive user judgment on ranking quality for top candidates

## Risks and Assumptions
### Risks
- Setup quality can be subjective, so threshold design may overfit to one trading style.
- Different sectors and volatility regimes may require different compression and breakout thresholds.
- Intraday data quality issues can distort compression and trigger detection.
- A strong-looking breakout can still fail due to external catalysts not modeled in V1.
- Excessive configurability can weaken consistency if defaults are not carefully chosen.

### Assumptions
- Users care more about reliable, explainable ranking than maximal signal count.
- Liquid US stocks provide sufficient price behavior consistency for a narrow V1.
- Bullish continuation breakouts are a strong enough initial wedge to validate product value.
- Daily, 1H, and 5m are sufficient to capture the core context for this setup class.
- Logging and explanation quality are first-order product requirements, not secondary features.
