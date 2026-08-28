# Phase 13A Step 2J — Requirements

## Scope

Add only a synchronous current-state construction boundary:

```text
SteamApisOfferPool
→ snapshot() exactly once
→ existing construct_live_recipes() exactly once
→ LivePoolRecipeConstructionResult
```

This function answers “construct recipes from the caller-owned pool state now.” It does not run or wait for a WebSocket session, schedule recomputation, value recipes, or connect to any provider.

## Existing authoritative contracts

- `SteamApisOfferPool.snapshot()` owns clock validation, lazy TTL eviction, immutable deterministic snapshot construction, and pool errors.
- `construct_live_recipes()` owns Step 2D classification, bucket filtering, construction-only solver invocation, complete eligible/rejected/bucket results, recipe order, and exact selected source provenance.
- `SkinMetadataCatalog` remains a caller-owned detached read-only lookup service under its existing public contract; this boundary does not clone or strengthen its mechanical immutability.
- `RecipeSolverConfig` remains validated by Step 2E. Current zero-or-one recipe per matching mode bucket behavior is not promoted into a new recipe-count cap.

The new boundary must not reproduce or override any of these rules.

## Public API

```python
class LivePoolRecipeConstructionError(RuntimeError):
    ...

@dataclass(frozen=True, kw_only=True, repr=False)
class LivePoolRecipeConstructionResult:
    snapshot_observation_count: int
    construction: LiveRecipeConstructionResult

def construct_live_recipes_from_pool(
    *,
    pool: SteamApisOfferPool,
    catalog: SkinMetadataCatalog,
    solver_config: RecipeSolverConfig,
) -> LivePoolRecipeConstructionResult:
    ...
```

The fixed public error message is:

```text
Live pool recipe construction failed
```

The result is frozen, keyword-only, and repr-hidden. It contains no snapshot, observation, candidate, duplicate provenance DTO, link, raw payload, market name, or economic field.

## Result validation

`snapshot_observation_count` must be an exact nonnegative built-in integer. Booleans, integer subclasses, non-integers, and negative values fail closed.

`construction` must be an exact `LiveRecipeConstructionResult` and must be defensively reconstructed through that DTO’s public constructor.

The following completeness invariant is mandatory:

```text
snapshot_observation_count
== len(construction.classification.eligible)
 + len(construction.classification.rejected)
```

This proves that Step 2E’s complete classification accounts for every observation in the unique snapshot. The wrapper must not flatten or copy selected source IDs beyond the existing `LiveConstructedRecipe` values.

## Authoritative flow

The implementation must perform exactly:

```text
snapshot = pool.snapshot()
construction = construct_live_recipes(
    snapshot=snapshot,
    catalog=catalog,
    solver_config=solver_config,
)
return wrapper using len(snapshot.observations)
```

Requirements:

- `pool.snapshot()` is called exactly once;
- `construct_live_recipes()` is called exactly once;
- that exact captured snapshot is passed to Step 2E;
- caller-provided catalog and solver config are passed through;
- no second snapshot or post-construction pool access occurs.

The module must not directly call or implement:

- `classify_steamapis_snapshot()`;
- candidate adaptation or metadata lookup;
- `construct_recipe_selections()` or `solve_recipes()`;
- Added/Updated, timestamp, TTL, or capacity policy;
- pool ingest, observation lookup, source-ID join, or purchase-link access;
- recipe valuation, EV, risk, or alerting.

## Snapshot and pool mutation semantics

This boundary is read-only at the orchestration level except for the existing side effect of `pool.snapshot()`:

```text
now - observation.message_timestamp >= ttl
→ lazy removal from the caller-owned pool
```

Therefore:

- snapshot count is post-TTL-eviction count;
- expired observations do not enter classification or construction;
- TTL eviction remains if later construction fails;
- the boundary performs no custom eviction or rollback;
- capacity-evicted and older-ignored historical observations cannot be recovered because only current pool state is captured.

The snapshot represents a point in time. Later clock advancement may make selected source IDs no longer joinable through the pool; this boundary provides no pinning or durable purchase-link guarantee and does not copy links into its result.

## Empty and no-recipe outcomes

An empty pool is valid when a valid nonempty catalog and config are supplied. It returns count zero, empty classification, and no recipes.

A rejected-only pool is also valid. Complete rejection details remain in Step 2E classification while recipes are empty.

Fewer than ten eligible inputs, unmatched modes, terminal rarity, or other existing Step 2E no-recipe outcomes are not wrapper errors.

## Failure behavior

Ordinary `Exception` failures from pool snapshot, Step 2E construction, malformed collaborator output, result validation, or unexpected collaborators become one fixed unchained `LivePoolRecipeConstructionError`.

No partial wrapper result is returned. Nested exception text and the following values must not enter public errors or repr:

- purchase or inspect links;
- source or listing IDs;
- market names;
- price, float, or seed values;
- raw payloads;
- API keys, tokens, Authorization values, or Cookies.

The boundary must not catch `MemoryError`, `asyncio.CancelledError`, `KeyboardInterrupt`, or other non-`Exception` `BaseException` values. They propagate unchanged.

If construction fails after snapshot lazy TTL eviction, that eviction remains. The boundary does not copy, clear, recreate, transaction-wrap, or restore the pool.

## Session and runtime separation

The module must not import or invoke:

- `SteamApisWebSocketClient`;
- Step 2I `run_steamapis_offer_session()`;
- `websockets`;
- retry/reconnect/session lifecycle code.

A real WebSocket session may remain open indefinitely; recipe construction must not be coupled to session close. Future runtime policy may independently let a session mutate the pool and trigger current-state evaluation at chosen times.

The function is synchronous, foreground, and single-shot. It contains no task, thread, queue, executor, scheduler, sleep, backoff, retry, loop, debounce, cache, background manager, or database operation.

## Architecture exclusions

The new production module must not directly import or call:

- listing parser or candidate adapter;
- metadata classifier/lookup implementation;
- recipe solver functions;
- live recipe valuation, `ValuationService`, `PriceProvider`, SteamDT, opportunity metrics, or risk evaluation;
- BUFF, Redis, Discord, FastAPI, scheduler, database, Docker, config, environment, logging, browser, login, marketplace write, or purchase behavior.

## Offline integration acceptance

At least one test must use:

```text
real SteamApisOfferPool
+ real SkinMetadataCatalog
+ real current-pool boundary
+ real Step 2D classifier
+ real Step 2E construction
```

The synthetic current pool must include at least ten eligible observations in one solver bucket across at least two collections, complete input/output metadata, and one rejected observation. It must produce one recipe with ten selected source IDs and an exact snapshot count equal to eligible plus rejected.

Focused integration tests must also prove:

- newer current economics are used after pool replacement;
- older ignored input does not resurface;
- TTL-expired current state is removed by the unique snapshot;
- capacity-evicted history does not resurface;
- equivalent repeated evaluations with fixed clock/current state are deterministic.

## File scope

Allowed changed paths are exactly:

```text
app/services/live_pool_recipe_construction.py
tests/test_live_pool_recipe_construction.py
README.md
docs/STEAMAPIS_MARKET_DATA_NOTES.md
specs/2026-08-13-live-pool-recipe-construction/plan.md
specs/2026-08-13-live-pool-recipe-construction/requirements.md
specs/2026-08-13-live-pool-recipe-construction/validation.md
```

Pool, listing, candidate adapter, metadata catalog, Step 2E construction, solver, session runner, valuation/core/provider/runtime/config/dependency modules, all previous specs/tests, and all SteamDT/BUFF/Redis/Discord/FastAPI/database/Docker files remain unchanged.

## Persistent blocker and stop boundary

Official SteamDT documentation still does not establish that batch `sellPrice` / `biddingPrice` are CNY/RMB. Step 2G remains blocked; no SteamDT, `PriceQuote.price_cny`, or `PriceProvider` currency semantic may change, and no UI currency display may be promoted into an OpenAPI contract.

This step makes no real SteamApis, SteamDT, BUFF, Redis, Discord, or PostgreSQL connection, creates no live smoke, performs no trade action, remains not production-ready, and stops before staging, commit, push, or Step 2K.
