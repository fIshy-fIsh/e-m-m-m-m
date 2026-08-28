# Phase 13A Step 2M-A5-PRE1 — Requirements

## Purpose

Provide one formal, versioned, deterministic synthetic recipe fixture for a later SteamDT BUFF full-valuation smoke. PRE1 stops at `LiveRecipeConstructionResult`; it performs no pricing, valuation, EV, ROI, risk evaluation, or network operation.

The authoritative construction chain is:

```text
fixed synthetic CandidateListing values
+ complete synthetic SkinMetadata topology
→ construct_recipe_selections(...)
→ existing build_output_candidates_by_collection(...)
→ existing calculate_tradeup_results(...)
→ engine-derived ConstructedRecipe / TradeupResult
→ existing public live classification/construction DTOs
```

## Public API

`app/services/steamdt_buff_live_recipe_fixture.py` exports exactly:

```python
SteamDTBuffLiveRecipeFixtureError
SteamDTBuffLiveRecipeFixture
build_steamdt_buff_live_recipe_fixture
```

The result contract is:

```python
@dataclass(frozen=True, kw_only=True, repr=False)
class SteamDTBuffLiveRecipeFixture:
    construction_result: LiveRecipeConstructionResult
    solver_config: RecipeSolverConfig
    risk_config: RiskFilterConfig
```

The builder contract is:

```python
def build_steamdt_buff_live_recipe_fixture(
    *,
    output_market_hash_name: str,
) -> SteamDTBuffLiveRecipeFixture: ...
```

The output name must be an exact nonblank `str`, already free of surrounding whitespace, and distinct from the fixed input name. It is not stripped, case-folded, remapped, parsed, or given a wear suffix.

## Deterministic synthetic topology

Use exactly:

- one fixed synthetic collection;
- one fixed `Restricted`, non-StatTrak, non-Souvenir input `SkinMetadata`;
- one caller-named `Classified`, non-StatTrak, non-Souvenir output `SkinMetadata` in that collection;
- ten fixed candidates for the one input skin;
- one fixed aware UTC scan timestamp;
- exact positive Decimal prices `1.00` through `10.00`;
- exact input float `0.0625`;
- paint seeds `1001` through `1010`;
- `inspect_link=None` and `raw=None`;
- no provider or marketplace payload.

The metadata list passed to the solver contains only that input and output record, so the complete next-rarity pool contains exactly one output. Do not create extra outputs and delete them after solving.

The output-name parameter may enter only the output `SkinMetadata.market_hash_name`. It must not be copied into an input candidate, input metadata, preconstructed output model, name mapping, or handwritten result.

## Production geometry authority

Call public `construct_recipe_selections()` exactly once. It must invoke the existing output-candidate builder and trade-up engine normally. PRE1 must not directly construct or import:

- `InputItem`;
- `OutputCandidate`;
- `ConstructedRecipe`;
- `TradeupResult`;
- probability;
- output float;
- output wear;
- estimated output price;
- expected-value contribution.

Do not call `calculate_tradeup_results()` directly. Do not call any private solver/live-construction helper.

Require one exact `ConstructedRecipeSelection`, ten unique selected listing IDs, and a complete retained mapping for those IDs. Use the returned `selection.recipe` unchanged as the live recipe geometry.

## Solver and risk configuration

The deterministic solver configuration is normal-mode `Restricted`, exactly ten inputs, configured sell fee `0.025`, and a ten-candidate collection cap. It is stored for future valuation but no fee or metric is calculated in PRE1.

Return a fresh deterministic `RiskFilterConfig` on every build. It exists only as future A5 input; do not call `evaluate_opportunity()`. No risk decision belongs in the fixture result.

## One-output and future-budget invariants

The returned fixture must fail closed unless it has:

```text
recipe_count = 1
input_count = 10
selected synthetic provenance count = 10
canonical distinct output count = 1
```

Also require:

- one classification bucket and no rejected candidate;
- ten eligible bindings and ten globally unique selected tokens;
- selected provenance order aligned to unmodified solver listing order;
- one synthetic input name and collection;
- solver rarity/mode alignment;
- positive input total cost;
- deterministic compact paint seeds;
- engine-derived probability total exactly one within the existing contract;
- finite output float in `[0, 1]`;
- nonblank engine-derived wear;
- existing construction placeholder `estimated_price_cny == 0`;
- existing construction placeholder `expected_value_contribution == 0`.

Canonical output identities are derived directly from `recipe.tradeup_results`; no second output mapping or stored request-budget field is allowed. The future A3 request budget is therefore one provider lookup. PRE1 performs zero provider lookups and zero requests.

The engine computes `output_wear` separately from the metadata market name. PRE1 does not prove or repair semantic agreement between a future wear-qualified real name and the derived wear.

## Synthetic compatibility provenance

Current `LiveCandidateBinding` validation requires:

```text
source_offer_id = 64 lowercase hexadecimal characters
candidate.goods_id = candidate.listing_id = "steamapis:buff163:" + source_offer_id
candidate.source = "steamapis:buff163"
```

PRE1 uses fixed tokens encoding integers 1 through 10 in that required shape. They are **synthetic compatibility provenance only**:

- not a real SteamApis source-offer ID;
- not a real BUFF listing ID;
- not an observed marketplace event;
- not provider identity;
- not purchase provenance;
- not joinable to a pool observation or purchase link.

The builder retains an explicit listing-ID-to-token map created with the candidates. It must not parse, slice, split, hash, or infer source tokens from IDs, URLs, names, prices, floats, or seeds.

No `SteamApisListingObservation`, pool, snapshot, WebSocket payload, parser, adapter, marketplace event, or purchase link may be constructed or imported.

## Determinism and safety

Equivalent exact input names must produce structurally equal detached results with identical candidate order, timestamps, configs, source tokens, selected order, recipe geometry, and output identities.

The module must not use:

- current time or default `CandidateListing.scanned_at`;
- random, UUID, process hash, secrets, or environment;
- file reads/writes;
- network/client/runtime behavior;
- cache, Redis, scheduler, task, thread, logging, or database;
- API keys, cookies, raw responses, account data, or URLs.

`MemoryError` propagates. Invalid names, malformed collaborator returns, unknown/duplicate/partial selection identities, alignment failures, or contradictory topology produce one fixed redacted `SteamDTBuffLiveRecipeFixtureError` with no nested cause or supplied value.

## Construction-only boundary

PRE1 must not import or invoke:

- `SteamDTBuffPriceProvider` or any `PriceProvider`/`PriceQuote`;
- `ValuationService`;
- `value_live_recipes_with_steamdt_buff_prices()`;
- `value_live_recipes()`;
- `calculate_opportunity_metrics()`;
- `evaluate_opportunity()`;
- SteamDT or SteamApis clients;
- any live smoke script.

No fake output price, real output price, valuation result, risk decision, purchase link, or request counter is stored.

## Tests

Offline tests must cover:

1. exact public exports, DTO fields, and keyword-only builder;
2. exact nonblank already-trimmed output names and fixed redacted failures;
3. deterministic repeated builds and defensive detachment;
4. exactly one recipe, ten inputs, one output;
5. ten unique valid synthetic compatibility tokens;
6. exact compatibility candidate identity and no observation/purchase provenance;
7. deterministic solver-selected order, prices, floats, seeds, and fixed timestamp;
8. deterministic solver and risk configs;
9. output name enters only output metadata;
10. real `construct_recipe_selections()` is called once;
11. real `calculate_tradeup_results()` is reached once indirectly;
12. final outputs equal captured real engine results;
13. engine-derived probability, float, and wear;
14. existing zero output-price/contribution placeholders;
15. derived future budget equals one;
16. malformed selection returns and identity mapping fail atomically;
17. process-control behavior;
18. AST proof of no handwritten trade-up models or geometry;
19. no provider, valuation, EV, risk execution, observation/payload, env, network, randomness, current time, file I/O, task, scheduler, cache, or purchase behavior;
20. protected authorities do not reverse-import the fixture.

## Allowed files

New:

- `app/services/steamdt_buff_live_recipe_fixture.py`
- `tests/test_steamdt_buff_live_recipe_fixture.py`
- `specs/2026-08-15-steamdt-buff-live-recipe-fixture/plan.md`
- `specs/2026-08-15-steamdt-buff-live-recipe-fixture/requirements.md`
- `specs/2026-08-15-steamdt-buff-live-recipe-fixture/validation.md`

Modified:

- `docs/STEAMDT_API_NOTES.md`

No other path may change.

## Exclusions

Do not modify any solver, trade-up engine, live metadata/construction, market candidate, SteamDT provider/policy/client, valuation, EV/risk, SteamApis, BUFF, cache/Redis, scheduler, Discord, FastAPI, Docker/database, config, environment, dependency, or runtime file.

Do not run a live smoke, connect to any service, commit, push, or begin A5-PRE2.
