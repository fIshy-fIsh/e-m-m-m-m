# Phase 13A Step 2M-A5-PRE2 — Requirements

## Purpose

Freeze one exact output identity that was manually query-verified through the real `SteamDTBuffPriceProvider` as the controlled default for a future A5 end-to-end valuation-plumbing smoke:

```text
M4A4 | Desolate Space (Factory New)
```

PRE2 does not repeat that query, retain its dynamic observed price, implement a valuation smoke, or change the deterministic synthetic fixture topology established in PRE1.

## Manual query-verification provenance

The user reported this completed manual verification:

```text
date: 2026-08-15
provider path: SteamDTBuffPriceProvider
source: steamdt:buff
request count: 1
result: success
```

This establishes only that the exact market hash name succeeded through that provider path in that historical run. It is not an official permanent SteamDT guarantee and does not establish current price, future query success, listing availability, executable proceeds, or profitability.

The historical observed price must not appear in production fixture code, expected test data, or fixture state. No API key, Authorization value, raw response, provider platform record, account data, or secret may be recorded.

## Public API

`app/services/steamdt_buff_live_recipe_fixture.py` must export exactly:

```python
SteamDTBuffLiveRecipeFixtureError
SteamDTBuffLiveRecipeFixture
STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME
build_steamdt_buff_live_recipe_fixture
build_verified_steamdt_buff_live_recipe_fixture
```

The constant contract is:

```python
STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME = (
    "M4A4 | Desolate Space (Factory New)"
)
```

It is a stable direct string constant. It is not stripped, normalized, case-folded, aliased, parsed, assembled, selected by price, loaded from environment or file, or refreshed through a network call.

The verified builder contract is:

```python
def build_verified_steamdt_buff_live_recipe_fixture(
) -> SteamDTBuffLiveRecipeFixture: ...
```

It accepts no arguments. Its only executable statement must return exactly one call to the generic PRE1 builder with exactly one keyword argument:

```python
return build_steamdt_buff_live_recipe_fixture(
    output_market_hash_name=(
        STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME
    )
)
```

It must return the delegated object unchanged. It adds no validation, exception handling, branch, local topology, metadata, candidates, configuration, parsing, suffix repair, solver call, provider call, or post-processing.

## Generic builder remains authoritative

The existing public generic API remains unchanged:

```python
def build_steamdt_buff_live_recipe_fixture(
    *,
    output_market_hash_name: str,
) -> SteamDTBuffLiveRecipeFixture: ...
```

It must continue accepting other exact nonblank already-trimmed caller-provided names. It remains the single source of truth for:

- the ten deterministic synthetic candidates;
- input and output metadata construction;
- synthetic collection and rarity topology;
- prices, floats, seeds, source tokens, and timestamp;
- solver and risk configurations;
- production solver/engine invocation;
- live construction DTO assembly;
- invariant and failure validation.

The verified wrapper must not copy any of this behavior.

## Exact identity and wear consistency

The exact full constant already contains the suffix `(Factory New)`. The generic builder places the entire unchanged value in the output metadata, after which the existing output-candidate, solver, and trade-up engine authorities propagate the identity into the final `TradeupResult`.

The production engine independently derives:

```text
output_float = 0.0625
output_wear = Factory New
```

PRE2 requires this exact name/wear agreement for this fixture. Production code must not parse the market hash name, append or repair a suffix, or import/call a wear parser solely for PRE2. A narrow test may assert that the constant ends with `(Factory New)` and that the independently derived result wear equals `Factory New`; this is not a general market-hash-name parser.

## Existing deterministic invariants

The verified fixture must preserve PRE1's exact contract:

```text
recipe count = 1
input count = 10
canonical distinct output count = 1
future provider lookup budget = 1
```

It also preserves:

- one classification bucket and no rejected candidates;
- ten eligible bindings and ten unique selected source tokens;
- production-derived output name, probability, float, and wear;
- construction placeholders `estimated_price_cny == 0` and `expected_value_contribution == 0`;
- deterministic repeated builds and detached result/config objects;
- the existing fixed `steamapis:buff163` compatibility-shaped synthetic provenance.

The future request budget is derived from canonical unique `TradeupResult.output_market_hash_name` values, not stored as a second field. PRE2 performs zero provider lookups and zero requests.

## Critical synthetic-topology disclaimer

This contract is exactly:

```text
verified real output marketHashName + synthetic fixture topology
```

Only the output query identity was manually verified. All PRE1 fixture input skins, collection, prices, floats, paint seeds, source provenance, rarity topology, timestamp, and candidate identities remain synthetic.

The fixture is suitable only as controlled input for a future end-to-end valuation-plumbing smoke. It must not be described or used as proof that:

- `M4A4 | Desolate Space (Factory New)` belongs to the synthetic collection;
- the ten synthetic inputs can produce that real skin;
- the synthetic rarity topology matches the real item;
- the inputs are current marketplace listings or are buyable;
- the output is currently available or queryable;
- the current price is stable;
- the recipe is executable, profitable, recommended, or within acceptable risk.

The synthetic compatibility tokens remain neither real SteamApis source-offer IDs nor BUFF listing IDs, observations, pool entries, purchase provenance, or purchase links.

## Construction-only and offline boundary

The production fixture module must not import, construct, call, or store:

- `PriceQuote`, a real/fake output price, or the historical observed price;
- `SteamDTBuffPriceProvider`, a SteamDT client, HTTP runtime, or request count;
- `ValuationService` or live recipe valuation composition;
- EV, ROI, profit, fee application, or risk evaluation;
- SteamApis observations, pools, snapshots, WebSocket events, payloads, or purchase links;
- environment/file reads, network access, cache/Redis, scheduler/task/thread, database, Discord, FastAPI, or purchase behavior.

No A4 provider smoke or A5 live valuation smoke may be run during implementation or validation.

## Offline tests

Tests must cover:

1. exact verified constant value;
2. exact public export set;
3. zero-argument verified builder signature;
4. verified wrapper delegates exactly once to the generic builder with only the exact constant keyword;
5. delegate return identity is preserved;
6. generic builder still accepts another synthetic output name;
7. exactly one verified recipe;
8. exactly ten inputs;
9. exactly one canonical output;
10. final derived output identity equals the verified constant;
11. derived output wear equals `Factory New`;
12. verified constant ends with `(Factory New)` without a general parser;
13. repeated verified builds are deterministic and detached;
14. construction output price/contribution placeholders remain zero;
15. the historical observed dynamic price is absent from production fixture code;
16. no `PriceQuote`, provider call, SteamDT client, environment read, file/network access, valuation/EV/ROI/risk execution, or SteamApis observation/pool/purchase link;
17. synthetic compatibility provenance is unchanged;
18. future request budget remains one;
19. AST proof that the wrapper contains only the required delegation and no copied topology;
20. existing production solver/engine authority and protected reverse-import boundaries remain intact.

All automated tests are offline.

## Allowed files

Modified:

- `app/services/steamdt_buff_live_recipe_fixture.py`
- `tests/test_steamdt_buff_live_recipe_fixture.py`
- `docs/STEAMDT_API_NOTES.md`

New:

- `specs/2026-08-15-steamdt-buff-live-recipe-verified-output/plan.md`
- `specs/2026-08-15-steamdt-buff-live-recipe-verified-output/requirements.md`
- `specs/2026-08-15-steamdt-buff-live-recipe-verified-output/validation.md`

No other path may change.

## Exclusions

Do not modify solver, trade-up engine, metadata, live construction, pool construction, SteamDT price policy/provider/client/valuation, valuation service, EV/risk, SteamApis, BUFF Phase 12, cache/Redis/limiter, scheduler, Discord, FastAPI, Docker/database, config, dependencies, `.env.example`, or runtime code.

Do not run real SteamDT, connect SteamApis, execute valuation/EV/ROI/risk, stage, commit, push, or begin the A5 live valuation smoke.
