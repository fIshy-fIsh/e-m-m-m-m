# Phase 12E4D0 — Recipe Construction Contract Requirements

## Purpose

Expose the recipe construction stage that already exists before EV and risk evaluation, so a later offline BUFF integration can construct valid recipes without executing opportunity evaluation. Keep the established `solve_recipes()` API and all production callers fully compatible.

## Selected decisions

1. Keep the new public contract in `app/services/recipe_solver.py`.
2. Expose plural `construct_recipes(...) -> list[ConstructedRecipe]`.
3. Store exactly three tuple-backed fields on `ConstructedRecipe`: inputs, trade-up results, and compact non-null paint seeds.
4. Derive total input cost rather than storing it.

## Public construction result

`ConstructedRecipe` must be a frozen, keyword-only, repr-suppressed dataclass with exactly:

- `input_items: tuple[InputItem, ...]`
- `tradeup_results: tuple[TradeupResult, ...]`
- `paint_seeds: tuple[int, ...]`

It must:

- contain exactly ten existing `InputItem` values in selected solver order;
- contain at least one existing `TradeupResult` in engine order;
- retain selected candidates' non-null integer paint seeds in selected order, including zero;
- expose `input_total_cost_cny` as an exact `Decimal` sum derived from inputs;
- expose no `OpportunityMetrics`, profit/ROI fields, `RiskDecision`, hash, timestamp, metadata, listing, valuation, alert, or duplicate count/cost state;
- not modify supplied objects or expose nested state through normal repr.

## Construction API

```python
def construct_recipes(
    candidates: list[CandidateListing],
    skins: list[SkinMetadata],
    solver_config: RecipeSolverConfig,
) -> list[ConstructedRecipe]:
    ...
```

The API must reuse, not duplicate, the existing construction logic:

1. Exact, case-sensitive metadata lookup by market hash name with the current duplicate-name behavior.
2. Candidate eligibility and normalized `InputItem` construction.
3. Collection, rarity, StatTrak, Souvenir, and float-range checks.
4. Deterministic ordering by adjusted float, price, market name, and listing ID.
5. Optional per-collection limiting after global sorting.
6. Selection of the first ten eligible inputs.
7. Outcome-pool construction from all supplied metadata.
8. One trade-up-engine invocation.

Current V1 cardinality remains `[]` or a one-element list. The API must not deduplicate candidate occurrences, mutate inputs, reorder engine results, retry, fall back, or perform background work.

## Normal empty and failure behavior

Preserve current behavior exactly:

- no eligible candidates: `[]`;
- fewer than ten retained candidates: `[]`;
- no output pool: `[]`;
- adjusted-float `ValueError`: skip that candidate;
- `calculate_tradeup_results()` `ValueError`: `[]`;
- output-pool errors and non-`ValueError` engine errors: propagate;
- `MemoryError`, `KeyboardInterrupt`, and `asyncio.CancelledError`: propagate unchanged.

Do not translate unexpected exceptions into an empty business result.

## Evaluation compatibility

The existing public contract remains:

```python
def solve_recipes(
    candidates: list[CandidateListing],
    skins: list[SkinMetadata],
    solver_config: RecipeSolverConfig,
    risk_config: RiskFilterConfig,
    liquidity_score: Decimal | None = None,
) -> list[RecipeCandidate]:
    ...
```

Its signature, parameter names/order/defaults, return annotation, list return shape, `RecipeCandidate` fields, validations, and observable behavior must remain unchanged.

For each call it must:

1. Invoke `construct_recipes()` exactly once.
2. Return `[]` without metrics or risk work when construction is empty.
3. Convert construction tuples into fresh lists for the existing `RecipeCandidate` contract.
4. Call `calculate_opportunity_metrics()` exactly once per construction.
5. Call `evaluate_opportunity()` exactly once per construction after metrics.
6. Preserve fee, risk config, liquidity score, compact selected paint seeds, hash semantics, aware UTC timestamp, result order, and failed-risk recipe retention.
7. Never rerun trade-up construction or candidate/metadata selection.

Metrics and risk remain mandatory and non-optional on `RecipeCandidate`; no dummy or placeholder values are allowed.

## Execution boundaries

`construct_recipes()` must not call:

- `calculate_opportunity_metrics()` or other EV/ROI/profit calculation;
- `evaluate_opportunity()` or any risk filter;
- valuation providers;
- pipeline, scheduler, FastAPI, alert, or Discord services;
- BUFF or SteamDT clients;
- Redis/cache services;
- environment/config readers;
- network, task, thread, executor, retry, fallback, or background work.

`solve_recipes()` continues to run its existing in-memory metrics and risk evaluation. The production pipeline, scheduler, and alerts continue to call only `solve_recipes()`.

## Compatibility scope

No production changes are permitted in:

- `tradeup_engine.py`
- `ev_service.py`
- `risk_filter.py`
- metadata models, service, or provider
- `pipeline_service.py`
- scheduler/FastAPI/alerts
- BUFF/SteamDT/Redis code
- existing BUFF integration scripts

No fixture, roadmap, config, environment, Docker, database, Discord, or automatic-purchase change is permitted.

## Repository scope

Create exactly:

- `specs/2026-07-28-recipe-construction-contract/plan.md`
- `specs/2026-07-28-recipe-construction-contract/requirements.md`
- `specs/2026-07-28-recipe-construction-contract/validation.md`

Modify only:

- `app/services/recipe_solver.py`
- `tests/test_recipe_solver.py`
- `README.md`

Phase 12E4D integration files must not be created or restored in this phase. `specs/roadmap.md` remains unchanged because this internal compatibility seam does not complete a top-level roadmap phase.

## Documentation contract

README must state:

- recipe construction and evaluated opportunity creation are separate public stages;
- construction includes trade-up geometry but not EV, ROI, profit metrics, or risk;
- `solve_recipes()` still performs complete metrics and risk evaluation;
- `RecipeCandidate` still represents an evaluated opportunity;
- pipeline, scheduler, and alerts remain unchanged;
- no dummy or optional metrics/risk fields were introduced;
- the seam enables but does not implement the later offline BUFF recipe integration;
- no external service is connected and the project remains not production-ready.
