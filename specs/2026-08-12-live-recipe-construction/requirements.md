# Phase 13A Step 2E — Requirements

## Scope

The only approved implementation scope is:

- `app/services/live_recipe_construction.py`
- `tests/test_live_recipe_construction.py`
- `README.md`
- `docs/STEAMAPIS_MARKET_DATA_NOTES.md`
- this spec directory's `plan.md`, `requirements.md`, and `validation.md`
- the minimal provenance enhancement in `app/services/recipe_solver.py`
- its compatibility coverage in `tests/test_recipe_solver.py`

No prior SteamApis parser, adapter, pool, or metadata-classification module may change. No market scanner, engine, metadata model/provider/service, Phase 12 BUFF module, SteamDT/Redis/config/environment/dependency file, runtime, pipeline, scheduler, Discord, FastAPI, Docker, or database module may change.

## Confirmed solver provenance gap

`construct_recipes(
    candidates: list[CandidateListing],
    skins: list[SkinMetadata],
    solver_config: RecipeSolverConfig,
) -> list[ConstructedRecipe]` currently returns an immutable three-field `ConstructedRecipe(input_items, tradeup_results, paint_seeds)`.

`InputItem` retains no `CandidateListing.listing_id` or equivalent source identity. The internal selected candidate is discarded after input construction. Consequently, a construction result cannot unambiguously distinguish two selected listings with identical name, price, float, and paint seed but different listing IDs.

Identity must never be guessed back from market name, price, float, seed, `InputItem`, URL, or dictionary iteration order.

## Source-agnostic construction provenance

Add exactly one thin public wrapper:

```python
@dataclass(frozen=True, kw_only=True, repr=False)
class ConstructedRecipeSelection:
    recipe: ConstructedRecipe
    selected_listing_ids: tuple[str, ...]
```

Add:

```python
def construct_recipe_selections(
    candidates: list[CandidateListing],
    skins: list[SkinMetadata],
    solver_config: RecipeSolverConfig,
) -> list[ConstructedRecipeSelection]:
    ...
```

Requirements:

- `selected_listing_ids` has exactly ten exact nonblank strings.
- Its order is one-to-one with `recipe.input_items`.
- IDs come directly from the same selected internal candidate pairs used to build the recipe.
- Construction eligibility, sorting, collection cap, output-pool building, trade-up calculation, empty behavior, and exception behavior have one authoritative path.
- `calculate_tradeup_results()` executes at most once for one construction attempt.
- Existing `ConstructedRecipe` fields, `construct_recipes()` signature/result/behavior, and `solve_recipes()` signature/result/evaluation behavior remain compatible.
- The core solver knows only `CandidateListing.listing_id`; it introduces no SteamApis-specific namespace, source ID, or URL rule.

## Live public contract

The module exports only:

```text
LiveRecipeConstructionError
LiveConstructedRecipe
LiveRecipeConstructionResult
construct_live_recipes
```

Public API:

```python
@dataclass(frozen=True, kw_only=True, repr=False)
class LiveConstructedRecipe:
    recipe: ConstructedRecipe
    selected_source_offer_ids: tuple[str, ...]

@dataclass(frozen=True, kw_only=True, repr=False)
class LiveRecipeConstructionResult:
    classification: LiveCandidateClassification
    recipes: tuple[LiveConstructedRecipe, ...]

def construct_live_recipes(
    *,
    snapshot: SteamApisOfferPoolSnapshot,
    catalog: SkinMetadataCatalog,
    solver_config: RecipeSolverConfig,
) -> LiveRecipeConstructionResult:
    ...
```

All DTOs are exact frozen, keyword-only, repr-suppressed values backed by tuples. Public values are defensively reconstructed. The fixed public error is `invalid live recipe construction contract`; ordinary errors suppress nested chaining, while `MemoryError` and non-`Exception` control-flow failures propagate unchanged.

## Offline integration behavior

The function performs only:

```text
SteamApisOfferPoolSnapshot
→ classify_steamapis_snapshot() exactly once
→ eligible exact rarity/StatTrak/Souvenir buckets
→ construct_recipe_selections()
→ exact selected source_offer_id mapping
→ immutable result
```

Requirements:

1. Use only Step 2D eligible bindings; rejections never enter construction.
2. Process classification buckets in their existing deterministic order.
3. Match `solver_config.input_rarity` exactly.
4. An explicit target StatTrak/Souvenir boolean must match the bucket. `None` matches both values, but each exact bucket is constructed independently and modes are never merged.
5. Collection is not a bucket identity; multiple collections in the same exact rarity/mode bucket reach one solver call.
6. Input metadata comes from `catalog.get_by_solver_bucket_key(bucket.key)`.
7. Next rarity comes only from the existing `get_next_rarity()` authority.
8. Output metadata comes from the exact next-rarity key with the same StatTrak and Souvenir values. Opposite-mode metadata does not enter the call.
9. The per-bucket solver config preserves input count, fee, and collection cap while pinning mode to the exact bucket.
10. Valid empty/no-construction cases return no live recipe: empty/all-rejected/unmatched snapshot, fewer than ten candidates, terminal rarity, missing output geometry, or normal solver empty result.
11. Unsupported rarity, invalid collaborator output, or inconsistent provenance fails the entire call atomically.

## Exact provenance mapping

For each exact bucket, build one `candidate.listing_id -> LiveCandidateBinding` mapping before consuming solver output. Duplicate candidate listing IDs fail closed.

Every selected listing ID must:

- be an exact string from the solver trace;
- have exactly one binding in that same bucket;
- map to the binding's explicit `source_offer_id`;
- remain in solver-selected order;
- contribute to exactly ten unique selected source IDs.

Unknown, repeated, partial, cross-bucket, too-short, or too-long selected identity fails closed. The live integration does not strip or parse the `steamapis:buff163:` prefix and does not derive identity from a purchase link or candidate economics.

`purchase_link` stays only on the original observation/pool. The result stores no observation or URL. The selected source IDs must remain joinable through the original pool's `get_observation()` and `get_purchase_link()` methods.

## Construction acceptance

The synthetic end-to-end scenario contains at least twelve observations, at least ten eligible candidates in one exact bucket, at least two input collections, corresponding input and next-rarity output metadata, at least one explicit rejection, and at least two identical-economics candidates with distinct source IDs.

It must produce exactly one live recipe with:

- exactly ten input items;
- nonempty trade-up results;
- engine-contract probability sum;
- existing derived total input cost;
- compact paint-seed behavior unchanged and full alignment when all synthetic seeds are non-null;
- exactly ten selected source IDs in exact solver selection order;
- successful join from every selected source ID to a nonempty pool purchase link without copying that link into the result.

## Explicit exclusions

This step does not:

- install or connect a WebSocket;
- connect SteamApis, BUFF, SteamDT, Redis, Discord, or another external service;
- call `solve_recipes()`;
- call opportunity metrics, risk evaluation, valuation service/provider, or compute final EV, ROI, profit, or risk;
- infer source IDs or metadata from URLs, names, prices, floats, seeds, or trade locks;
- read providers, files, environment, credentials, or runtime configuration;
- add network/retry/reconnect/client behavior;
- create tasks, threads, timers, schedulers, pipelines, FastAPI/database behavior, browser/login/purchase behavior, or automatic buying;
- commit, push, or begin Step 2F.
