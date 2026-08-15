# Phase 13A Step 2M-A3 — Plan

1. **Freeze the composition contract**
   - Record the audited Step 2F input contract, authoritative output-name flow, source-by-construction policy, inherited strict rejection behavior, and offline boundaries.
   - Limit protected changes to the explicitly approved `MemoryError` propagation correction in `ValuationService` and its focused test.

2. **Correct process-control propagation**
   - Re-raise provider-originated `MemoryError` before the existing ordinary provider-exception conversion in `ValuationService`.
   - Prove exception identity propagation without changing ordinary exception behavior.

3. **Add the closed A3 adapter**
   - Accept an existing `LiveRecipeConstructionResult`, borrowed `SteamDTMarketDataClient`, solver config, risk config, and optional liquidity score.
   - Construct one `SteamDTBuffPriceProvider` and one `ValuationService`, then delegate once to the existing `value_live_recipes()` authority.
   - Add no pricing, output-name, EV, ROI, fee, probability, risk, fallback, retry, cache, network, or lifecycle logic.

4. **Exercise the full offline chain**
   - Fake only the narrow SteamDT market-data client boundary.
   - Use the real aggregate helper, exact BUFF selector, BUFF provider, valuation service, Step 2F gate, metrics, fee, and risk logic.
   - Cover complete valuation, bid exclusion, source provenance, shared outputs, deterministic alignment, whole-recipe failure isolation, provenance, paint seeds, and all required BUFF selection failures.

5. **Document and validate**
   - Add a minimal SteamDT notes section explaining the composition and its limitations.
   - Run all focused suites, full pytest, Ruff, Mypy, and whitespace/scope audits entirely offline.
   - Leave all files unstaged and uncommitted; do not push or begin Step 2M-A4.
