# Phase 13A Step 2M-A3 — Requirements

## Scope

Add one offline-only composition:

```text
LiveRecipeConstructionResult
→ SteamDTBuffPriceProvider
→ ValuationService
→ value_live_recipes(...)
→ LiveRecipeValuationResult
```

This phase composes existing authorities. It does not implement trade-up geometry, output-name derivation, SteamDT parsing, BUFF selection, EV, ROI, fee, probability, risk, fallback, runtime, or network behavior.

## Audited existing contract

The existing Step 2F entry point is:

```python
async def value_live_recipes(
    *,
    construction_result: LiveRecipeConstructionResult,
    valuation_service: ValuationService,
    solver_config: RecipeSolverConfig,
    risk_config: RiskFilterConfig,
    liquidity_score: Decimal | None = None,
) -> LiveRecipeValuationResult: ...
```

It requires a concrete `ValuationService`, not a `PriceLookupResult`, `ValuationResult`, mapping, or structural service.

For each recipe, `ValuationService` obtains authoritative names from existing `TradeupResult.output_market_hash_name` values, stably deduplicates them by first occurrence, asks its provider once, and applies returned prices while retaining result order and geometry. Step 2F then performs its existing strict complete-price gate before existing metrics and risk evaluation.

## Public API

`app/services/steamdt_buff_live_recipe_valuation.py` exports exactly:

- `value_live_recipes_with_steamdt_buff_prices`

The exact contract is:

```python
async def value_live_recipes_with_steamdt_buff_prices(
    *,
    construction_result: LiveRecipeConstructionResult,
    client: SteamDTMarketDataClient,
    solver_config: RecipeSolverConfig,
    risk_config: RiskFilterConfig,
    liquidity_score: Decimal | None = None,
) -> LiveRecipeValuationResult: ...
```

The function must:

1. construct exactly one `SteamDTBuffPriceProvider(client)`;
2. construct exactly one `ValuationService(provider)`;
3. invoke `value_live_recipes(...)` exactly once with the supplied construction/configuration values;
4. return that exact existing result.

It must not accept an arbitrary provider, valuation service, provider factory, source, valuation configuration, output-name mapping, or prebuilt price lookup. The client is borrowed and is never created, configured, closed, retried, cached, or otherwise owned by A3.

## Price and source authority

Every successful real output price in this composition must pass through the existing `SteamDTBuffPriceProvider`, whose existing authorities provide:

```text
get_steamdt_market_data(...)
→ select_buff_output_price(...)
→ PriceQuote(source="steamdt:buff", raw=None)
```

The resulting price is the exact positive finite gross BUFF aggregate `sell_price_cny` under the documented project CNY interpretation. It is not an executable listing price, guaranteed proceeds, a bid, a recent sale, or an official provider currency guarantee.

A3 must not:

- accept another provider source;
- fall back to STEAM, YOUPIN, C5, SteamApis, metadata estimates, zero, bids, or another BUFF-like literal;
- read or compare platform records itself;
- revalidate or duplicate the fixed source literal;
- retain raw provider data.

Source is guaranteed by the closed internal provider construction. The existing `LiveRecipeValuationResult` does not retain `PriceQuote.source`; A3 adds no wrapper or source field.

## Output-name collection and duplicate handling

Output identity remains the exact existing `TradeupResult.output_market_hash_name`, originating in current metadata/trade-up geometry. A3 must not infer names from display text, wear text, URLs, listings, purchase links, or string construction.

Within each recipe:

- `ValuationService` performs stable first-occurrence exact-name deduplication;
- `SteamDTBuffPriceProvider` strips, drops blanks, and stable-deduplicates canonical names;
- valid engine geometry already merges same exact output names;
- Step 2F rejects malformed duplicate, missing, extra, renamed, or reordered geometry.

Provider deduplication must not alter the recipe's valued-result order, probability, float, wear, or output alignment. Whitespace/canonicalization collisions fail closed under existing alignment checks.

Across recipes, Step 2F invokes valuation separately. A shared output name is looked up once per recipe, in recipe order. A3 adds no global deduplication, prefetch, cache, or cross-recipe quote reuse.

## Missing and invalid prices

The following must create no quote and no partial or fallback valuation:

- no exact BUFF record;
- duplicate exact BUFF records;
- missing BUFF sell price;
- nonfinite, zero, or negative BUFF sell price;
- ordinary provider/client failure;
- valid/high prices on another platform when BUFF is absent;
- high BUFF bid when its sell price is invalid or absent.

The existing A2 batch provider reports each ordinary selection/lookup failure in both `missing` and `errors`. Step 2F gives provider errors precedence, so these failures reject the entire affected recipe as:

```text
LiveRecipeValuationRejectionReason.PRICE_PROVIDER_ERROR
```

No EV, fee, ROI, or risk result is generated for that recipe. Later recipes continue after ordinary per-recipe rejection. Metadata placeholder prices, including zero, never become an accepted fallback because Step 2F rejects every missing/fallback warning or declaration.

## EV, fee, ROI, and risk

Only the existing `value_live_recipes()` path may execute:

- `calculate_opportunity_metrics(...)`;
- the configured `RecipeSolverConfig.sell_fee_rate` exactly once;
- EV and ROI calculations;
- `evaluate_opportunity(...)` with existing `RiskFilterConfig` and optional liquidity score.

A3 must not import, call, copy, or change these algorithms. Probability, thresholds, fee configuration, and risk configuration remain unchanged. Bidding data never participates.

Existing Step 2F behavior remains authoritative: a complete valuation may produce a `LiveValuedOpportunity` whose `risk_decision.passed` is false; a risk failure is not a valuation rejection.

## Provenance and paint seeds

A3 must preserve the exact Step 2F behavior:

- successful opportunities and rejections retain the original ordered `selected_source_offer_ids`;
- source-offer IDs are not inferred from names, URLs, or positions;
- the original recipe and trade-up geometry remain unchanged;
- actual compact non-null `ConstructedRecipe.paint_seeds` are passed to existing risk evaluation;
- no purchase/inspect link is copied, generated, or acted upon.

## Process-control and redaction

Provider-originated `MemoryError`, `asyncio.CancelledError`, `KeyboardInterrupt`, and `SystemExit` must propagate by identity, stop later calls/recipes, and return no partial result.

The current generic service swallows `MemoryError` under broad `Exception`. The user explicitly authorized one prerequisite behavior correction:

```python
except MemoryError:
    raise
except Exception as exc:
    ... existing behavior ...
```

Only `app/services/valuation_service.py` and its focused test may change for this correction. Public signatures, DTOs, ordinary provider-error conversion, messages, missing strategies, and all other behavior remain unchanged.

A3 adds no error class, logging, exception stringification, or wrapper. Existing fixed/redacted provider and Step 2F errors remain authoritative. API keys, Authorization data, raw SteamDT responses, raw listings, purchase links, and nested exception text must not enter public A3 output or logs.

## Offline-only architecture

Production A3 code must not import, construct, call, or own:

- a concrete SteamDT HTTP client or endpoint;
- SteamApis modules;
- direct BUFF modules;
- HTTP/WebSocket/network libraries;
- environment/settings/secrets;
- retry, timeout, limiter, Redis, or cache;
- task/concurrency/background primitives;
- scheduler, runtime, FastAPI, Discord, database, or Docker paths;
- recipe construction/solver execution;
- metrics or risk authorities directly;
- listing, purchase, inspect, login, cookie, captcha, or auto-buy behavior.

Tests fake only `SteamDTMarketDataClient.get_price_single_candidates()`. They must use the real A2 provider/aggregate/policy, real `ValuationService`, real Step 2F, and real metrics/risk code. No real request or service connection may occur.

## Allowed files

New:

- `app/services/steamdt_buff_live_recipe_valuation.py`
- `tests/test_steamdt_buff_live_recipe_valuation.py`
- `specs/2026-08-15-steamdt-buff-live-recipe-valuation/plan.md`
- `specs/2026-08-15-steamdt-buff-live-recipe-valuation/requirements.md`
- `specs/2026-08-15-steamdt-buff-live-recipe-valuation/validation.md`

Modified:

- `app/services/valuation_service.py` — only the approved `MemoryError` rethrow;
- `tests/test_valuation_service.py` — only focused prerequisite coverage;
- `docs/STEAMDT_API_NOTES.md` — minimal A3 notes.

No other file may change.

## Known limitations

- Final `LiveRecipeValuationResult` does not retain per-output `PriceQuote.source`; provenance is guaranteed by this closed composition but cannot be reconstructed from the result alone.
- Shared outputs across recipes are requested once per recipe because Step 2F remains sequential and no cache is introduced.
- Existing authoritative `output_market_hash_name` is used unchanged. This phase does not solve the pre-existing possibility that a wear-qualified metadata name and computed `output_wear` could disagree.
- BUFF aggregate sell price is not an executable listing or guaranteed net proceeds and receives no slippage/liquidity haircut.
- Source offer IDs are preserved, but A3 does not pin their originating pool observations during asynchronous valuation.

## Exclusions

Do not modify existing SteamDT client, aggregate service, BUFF policy/provider, generic price contracts, Step 2F live valuation, recipe/construction/solver, trade-up engine, EV/risk logic, SteamApis, BUFF Phase 12, cache/Redis/limiter, scheduler/runtime, Discord, FastAPI, Docker/database, configuration, dependencies, README, or roadmap.

Do not commit, push, run live smokes, make network requests, or begin Step 2M-A4.
