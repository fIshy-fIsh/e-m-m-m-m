# Phase 13A Step 2F — Offline Live Recipe Valuation Plan

1. Freeze the already-constructed live valuation boundary, exact public DTO/API contract, rejection precedence, redaction, and approved scope before source changes.
2. Add an independent async live valuation orchestrator that sequentially invokes an injected `ValuationService` once per constructed recipe and never reruns selection or construction.
3. Fail closed unless every output has an aligned provider quote and valuation changes only price and expected-value contribution.
4. Reuse `calculate_opportunity_metrics()` with the configured sell fee and `evaluate_opportunity()` with the construction recipe's real paint seeds.
5. Preserve exact ordered selected source-offer provenance and distinguish valuation rejection from a valid risk decision that fails thresholds.
6. Cover happy, missing/error, malformed-integrity, risk, redaction, exception, deterministic, multi-recipe, and architecture boundaries with synthetic tests.
7. Document the offline injected-provider boundary and legacy pipeline compatibility without changing protected core modules.
8. Run all focused and full validation, exact scope/security audits, and dry-runs; record observed results and stop uncommitted before Step 2G.
