# Phase 13A Step 2M-A2 — Requirements

## Scope

Implement one standalone, offline adapter:

```text
market_hash_name
→ get_steamdt_market_data(...)
→ select_buff_output_price(...)
→ PriceQuote.price_cny
```

The adapter must structurally satisfy the existing `PriceProvider` protocol without modifying it or the existing generic `SteamDTPriceProvider`.

## Public API

`app/services/steamdt_buff_price_provider.py` exports exactly:

- `SteamDTBuffPriceProvider`

The class has:

```python
def __init__(self, client: SteamDTMarketDataClient) -> None: ...

async def get_price(self, market_hash_name: str) -> PriceQuote: ...

async def get_prices(
    self,
    market_hash_names: list[str],
) -> PriceLookupResult: ...
```

The injected narrow client is borrowed. The provider creates, closes, configures, or owns no HTTP client, limiter, cache, runtime, task, or other lifecycle resource.

## Single-item composition

`get_price()` must:

1. pass the exact supplied name unchanged to `get_steamdt_market_data(client=..., market_hash_name=...)`;
2. pass the returned `SteamDTMarketDataResult` to `select_buff_output_price(market_data=...)`;
3. return a fresh exact `PriceQuote` with:
   - `market_hash_name` from the selected output;
   - `price_cny` equal to the selected exact BUFF gross `sell_price_cny`;
   - fixed `source="steamdt:buff"`;
   - `raw=None`.

The provider must not scan aggregate quotes, compare platforms, contain a BUFF selection literal, reproduce sell-price validation, read bid fields, use the generic SteamDT selector, or call client selected-price/batch APIs.

Single aggregate, A1 policy, client, ordinary, and process-control exceptions propagate unchanged. The adapter does not stringify, log, wrap, or expose nested data on this path.

## Source and price meaning

- `steamdt:buff` is a fixed, stable, lowercase, non-secret source string meaning SteamDT aggregate data selected by the exact BUFF policy.
- It is provenance, not a purchase/listing identity.
- `PriceQuote.price_cny` is the positive finite gross BUFF aggregate sell price under the project-approved CNY interpretation.
- This is not an official current currency guarantee, executable listing price, guaranteed proceeds, buy order, recent sale, or special-condition order.
- No bidding price, fee, exchange rate, net proceeds, EV, ROI, profit, risk, or probability is calculated.

## Batch input semantics

`get_prices()` accepts the existing declared `list[str]` shape and must:

1. require an exact list and exact string elements;
2. strip each string;
3. drop empty or whitespace-only names;
4. stable-deduplicate canonical names by first occurrence;
5. process each canonical unique name sequentially through `get_price()` exactly once.

No task, concurrency, batch endpoint, retry, fallback, sleep, cache, or request-volume optimization is added. Empty canonical input returns exact `PriceLookupResult(quotes={}, missing=[], errors=[])` with zero client calls.

## Batch success and alignment

For every successful item:

- insert one exact `PriceQuote` under the canonical name;
- require the dict key and `PriceQuote.market_hash_name` to agree exactly;
- preserve successful-item order as the successful projection of canonical input order;
- omit it from `missing` and `errors`.

A complete success has exact `dict` / `list` / `list` containers and empty missing/errors, making it compatible with the existing strict downstream contract without wiring or invoking `ValuationService`.

## Batch ordinary-failure semantics

Every ordinary per-item failure:

- creates no quote;
- appends the canonical name once to `missing`;
- appends exactly one safe error to `errors` at the same failed-item position;
- continues with later canonical unique names.

For `SteamDTBuffPriceSelectionError`, use exactly:

```text
STEAMDT_BUFF_PRICE_SELECTION_FAILED: item_index=N, reason=<reason.value>
```

For every other ordinary `Exception`, use exactly:

```text
STEAMDT_BUFF_PRICE_LOOKUP_FAILED: item_index=N
```

`N` is the zero-based index in the canonical unique-name list, not the original raw input index or failure-list index. `missing` and `errors` are one-to-one and ordered by failed canonical item.

Error strings must not include market names, exception text/repr/type, prices, platform data, opaque IDs/times, API keys, Authorization values, headers, raw responses, or nested errors.

## Process-control failures

- `MemoryError` propagates immediately and is not converted to an item error.
- `asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit`, and all other non-`Exception` values propagate naturally.
- No later item starts after a process-control failure.
- No partial `PriceLookupResult` is returned and earlier borrowed-client effects are not rolled back.

## Offline tests

At minimum cover:

1. one name with exact BUFF sell price returns a quote;
2. source is exactly `steamdt:buff`;
3. exact Decimal value/precision is preserved;
4. a higher BUFF bid does not replace sell price;
5. no BUFF produces no batch quote and a reason-bearing safe error;
6. duplicate BUFF produces no batch quote;
7. missing BUFF sell produces no batch quote;
8. zero BUFF sell produces no batch quote;
9. valid non-BUFF sell with missing BUFF does not fallback;
10. higher STEAM sell is ignored;
11. much higher YOUPIN bid is ignored;
12. multiple canonical names preserve deterministic order/alignment;
13. a middle failure does not shift or block a later success;
14. exact canonical market names are preserved in keys and quotes;
15. aggregate helper then A1 policy is the actual composition path;
16. the fake client is called once per canonical unique name;
17. no network/runtime client construction;
18. no env/key access;
19. no SteamApis dependency;
20. no Redis/cache/limiter;
21. no valuation/EV/ROI/risk;
22. no fee/net proceeds;
23. no purchase URL/listing synthesis;
24. ordinary batch errors are fixed and redact hostile nested data;
25. `MemoryError`, cancellation, keyboard interruption, and system exit propagate per contract.

Also cover exact list/string validation, empty input, blank dropping, whitespace stripping, stable duplicate collapse, duplicated failing names reported once, all-failure ordering, exact result container types, structural protocol signatures, no raw retention, and no protected reverse import.

## Allowed files

- New: `app/services/steamdt_buff_price_provider.py`
- New: `tests/test_steamdt_buff_price_provider.py`
- New: `specs/2026-08-15-steamdt-buff-price-provider/plan.md`
- New: `specs/2026-08-15-steamdt-buff-price-provider/requirements.md`
- New: `specs/2026-08-15-steamdt-buff-price-provider/validation.md`
- Modified: `docs/STEAMDT_API_NOTES.md`

No other file may change.

## Exclusions

Do not modify or wire:

- `app/clients/steamdt_client.py`;
- `app/services/steamdt_market_data.py`;
- `app/services/steamdt_buff_price_policy.py`;
- existing `SteamDTPriceProvider`, `PriceProvider`, `PriceQuote`, or `PriceLookupResult`;
- `ValuationService`, live recipe valuation, recipe, EV, ROI, risk, or solver;
- SteamDT cache, Redis, limiter, refresh, scheduler, smoke, or runtime;
- SteamApis, direct BUFF integration, Discord, FastAPI, Docker, database, config, environment, or dependencies.

Do not perform network requests, run live smokes, commit, push, or begin Step 2M-A3.
