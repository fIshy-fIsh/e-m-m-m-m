# Phase 13A Step 2F — Offline Live Recipe Valuation Requirements

## Context and authority

This step follows `specs/mission.md` and `specs/tech-stack.md`. It starts only from the immutable Step 2E `LiveRecipeConstructionResult` and adds offline complete output valuation, authoritative EV/ROI metrics, and authoritative risk evaluation. It remains read-only and does not make the scanner production-ready.

Baseline is `45f0fd68cca7dcbeb04675af4b8b2db3a1bd0e5c` on `feature/steamdt-cache-rate-limit` with a clean tree and index.

## Public contract

`app.services.live_recipe_valuation` must export only:

- `LiveRecipeValuationError`
- `LiveRecipeValuationRejectionReason`
- `LiveValuedOpportunity`
- `LiveRecipeValuationRejection`
- `LiveRecipeValuationResult`
- `value_live_recipes`

`LiveRecipeValuationError` must always expose only:

```text
invalid live recipe valuation contract
```

`LiveRecipeValuationRejectionReason` must contain exactly, in order:

```text
MISSING_OUTPUT_PRICE = "missing_output_price"
PRICE_PROVIDER_ERROR = "price_provider_error"
INVALID_VALUATION_RESULT = "invalid_valuation_result"
```

Public DTOs must be frozen, keyword-only, `repr=False`, tuple-backed, defensively reconstructed, and field-ordered as follows:

```python
LiveValuedOpportunity(
    recipe: ConstructedRecipe,
    selected_source_offer_ids: tuple[str, ...],
    valued_tradeup_results: tuple[TradeupResult, ...],
    metrics: OpportunityMetrics,
    risk_decision: RiskDecision,
)

LiveRecipeValuationRejection(
    selected_source_offer_ids: tuple[str, ...],
    reason_code: LiveRecipeValuationRejectionReason,
)

LiveRecipeValuationResult(
    opportunities: tuple[LiveValuedOpportunity, ...],
    rejected: tuple[LiveRecipeValuationRejection, ...],
)
```

The entry point must be:

```python
async def value_live_recipes(
    *,
    construction_result: LiveRecipeConstructionResult,
    valuation_service: ValuationService,
    solver_config: RecipeSolverConfig,
    risk_config: RiskFilterConfig,
    liquidity_score: Decimal | None = None,
) -> LiveRecipeValuationResult:
```

An injected subclass/test double compatible with `ValuationService.value_tradeup_results()` is permitted. No provider, client, cache, limiter, runtime, or factory is constructed here.

## Sequential orchestration

For each `construction_result.recipes` value, in input order:

1. call `valuation_service.value_tradeup_results(list(recipe.tradeup_results))` exactly once;
2. apply provider/missing/integrity gates;
3. for complete trusted valuation only, call existing metrics once and existing risk evaluation once;
4. place the input recipe in exactly one output partition.

The API must not call or import `solve_recipes()`, `construct_recipes()`, `construct_recipe_selections()`, `construct_live_recipes()`, `calculate_tradeup_results()`, candidate selection, or metadata classification. It must not use concurrency, tasks, threads, retries, background work, or external connections.

An empty construction result returns empty opportunity and rejection tuples without invoking collaborators.

## Rejection taxonomy and precedence

Normal returned valuation data is untrusted. When safely inspectable, reason precedence is:

1. nonempty `price_lookup_result.errors` or a `PRICE_PROVIDER_ERROR` warning → `PRICE_PROVIDER_ERROR`;
2. missing declarations, known missing/fallback warnings, or an expected output with no quote → `MISSING_OUTPUT_PRICE`;
3. every other malformed or inconsistent returned valuation → `INVALID_VALUATION_RESULT`.

An ordinary `Exception` directly raised by `value_tradeup_results()` becomes a redacted `PRICE_PROVIDER_ERROR` rejection for that recipe, and later recipes continue.

All current missing-price strategies fail closed. `KEEP_ORIGINAL`, `ZERO_PRICE`, `DROP_RESULT`, and `require_all_prices` warning output cannot reach EV/risk. Metadata zero placeholders are never a fallback; partial result sets and reduced probability mass are never accepted; missing prices never become zero-price opportunities.

A provider/missing/integrity rejection is per recipe and invokes neither metrics nor risk. An ordinary metrics/risk failure or malformed metrics/risk result raises the fixed public orchestration error for the whole call and publishes no partial result.

`MemoryError`, `KeyboardInterrupt`, `asyncio.CancelledError`, and any other non-`Exception` `BaseException` propagate unchanged.

## Complete-price and valuation integrity gate

Before EV, valuation must prove:

- exact `ValuationResult`, `PriceLookupResult`, warning, quote, and result DTO/container contracts;
- result count and order exactly match construction geometry;
- output market hash name, probability, output float, and wear are unchanged item by item;
- probabilities and floats are finite floats in their existing engine domains;
- probability total satisfies existing `PROBABILITY_TOLERANCE`;
- estimated prices are exact finite nonnegative `Decimal` values;
- expected-value contributions are exact finite `Decimal` values equal to `price * Decimal(str(probability))`;
- each unique original output has exactly one aligned quote and there are no extra quote keys;
- quote key, quote market hash name, valued output name, and valued price agree exactly;
- quote source is an exact nonblank string;
- missing and error declarations are empty and no warning remains.

A genuinely provider-quoted zero price is valid; an unquoted zero placeholder is not. Raw quote data is ignored and never copied.

Valuation may change only output estimated price and expected-value contribution. It must not recompute trade-up geometry or modify the construction recipe.

## Metrics and risk

Metrics must use only the existing:

```python
calculate_opportunity_metrics(
    input_items=list(constructed.recipe.input_items),
    tradeup_results=list(validated_valued_results),
    sell_fee_rate=solver_config.sell_fee_rate,
)
```

No EV, ROI, fee, probability, or profit formula may be duplicated.

Risk must use only the existing:

```python
evaluate_opportunity(
    metrics=metrics,
    input_items=list(constructed.recipe.input_items),
    config=risk_config,
    liquidity_score=liquidity_score,
    paint_seeds=list(constructed.recipe.paint_seeds),
)
```

The live path must never pass `paint_seeds=None`. The config and result must be defensively detached, including mutable seed sets and reason lists.

A complete valued recipe always becomes a `LiveValuedOpportunity`, even when `risk_decision.passed` is false. Risk failure is not a valuation rejection.

## Provenance and redaction

Every opportunity or rejection retains `selected_source_offer_ids` exactly, with unchanged order and count. The API must not remap, parse, or infer IDs; parse URLs; access the offer pool; copy purchase or inspect links; or add seller/account data.

No public repr or orchestration exception may contain purchase/inspect links, market names, source-offer IDs, listing IDs, prices, floats, paint seeds, provider raw responses, nested exception text, API keys, tokens, Authorization values, or Cookies. Business rejection DTOs retain only selected source IDs and a stable reason code and remain `repr=False`.

## Multi-recipe and atomicity

Recipes are valued sequentially. A provider, missing, or invalid valuation for one recipe does not block later recipes. `opportunities` and `rejected` each preserve the relative input order of their own members. Every input recipe appears in exactly one partition.

Results are accumulated privately and returned only after every recipe finishes. A late metrics/risk orchestration failure returns no partial public result. This is atomic result publication, not rollback of already invoked injected collaborators.

## Legacy compatibility

Do not modify `valuation_service.py`, `price_provider.py`, `ev_service.py`, `risk_filter.py`, `pipeline_service.py`, `tradeup_engine.py`, `recipe_solver.py`, or `live_recipe_construction.py`.

Legacy behavior remains unchanged: provider exceptions can become warnings/missing output, missing-price strategies may keep/zero/drop, pipeline valuation errors keep the original recipe, warnings do not block, and post-valuation risk currently uses `paint_seeds=None`. Step 2F overlays a stricter live-only boundary without changing those callers.

## Scope and exclusions

Allowed changes are exactly:

```text
app/services/live_recipe_valuation.py
tests/test_live_recipe_valuation.py
README.md
docs/STEAMAPIS_MARKET_DATA_NOTES.md
specs/2026-08-12-live-recipe-valuation/plan.md
specs/2026-08-12-live-recipe-valuation/requirements.md
specs/2026-08-12-live-recipe-valuation/validation.md
```

No real SteamDT, SteamApis, BUFF, Redis, Discord, PostgreSQL, WebSocket, HTTP, browser, login, purchase, scheduler, FastAPI, Docker, environment, or background integration is allowed. Do not install dependencies, change config/secrets, modify Phase 12 strict BUFF modules, commit, push, or begin Step 2G.
