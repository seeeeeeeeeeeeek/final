# AGENTS.md

## Project Rules For Codex
- Treat this repository as the foundation of a breakout quality scanner for liquid US stocks.
- Keep V1 narrow and consistent with `PRD.md` and `MVP_SPEC.md`.
- Do not implement beyond the documented V1 scope unless the user explicitly confirms scope expansion.
- Ask for confirmation before widening scope beyond V1.
- Prefer reliability and explainability over complexity.
- Prefer modular, testable code with clear interfaces between scanner modules.
- Keep all thresholds configurable; avoid hard-coding strategy constants unless they are documented defaults.
- Add logs for every signal decision, including pass, fail, skip, and no-trade outcomes.
- Surface assumptions clearly in code comments, docs, config, and user-facing explanations.

## Explicit V1 Constraints
- Supported market: liquid US stocks only.
- Supported direction: bullish continuation breakouts only.
- Required timeframes: Daily, 1H, 5m.
- Do not add broker execution.
- Do not add machine learning in V1.
- Do not add short-selling logic in V1.
- Do not add portfolio management or order sizing in V1 unless explicitly requested later.

## Implementation Standards
- Build small, composable modules for:
  - trend filter
  - compression detector
  - breakout trigger detector
  - quality scoring
  - trap-risk detection
  - explanation generation
  - skip/no-trade reasoning
- Keep business logic deterministic and easy to test.
- Prefer plain, inspectable scoring logic over opaque heuristics.
- Ensure every scanner decision can be traced back to metrics and thresholds.
- Use structured outputs with stable field names.
- Preserve a clear separation between data access, signal logic, scoring, and presentation layers.

## Testing And Verification Expectations
- Add unit tests for each module before expanding complexity.
- Use fixture-based tests for representative bullish continuation examples, false positives, and edge cases.
- Verify deterministic output for identical input data and config.
- Validate that every rejected or skipped signal has a clear reason.

## Logging And Explainability Expectations
- Log the input context, computed metrics, pass/fail decisions, scores, and final status for every evaluated symbol.
- Keep explanation text grounded in actual computed values.
- Ensure skip and no-trade reasons identify the failed module or elevated risk condition.

## Change Management Rules
- When implementing new work, update docs if thresholds, schema, or module responsibilities change.
- If a request conflicts with the V1 scope, pause and ask for explicit confirmation before proceeding.
- If a proposed solution increases complexity without clear reliability gains, choose the simpler, more explainable option.
