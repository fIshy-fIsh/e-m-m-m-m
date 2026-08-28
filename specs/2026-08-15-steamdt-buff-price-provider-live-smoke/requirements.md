# Phase 13A Step 2M-A4 — Requirements

## Scope

Add one explicitly opted-in manual smoke harness for exactly this chain:

```text
one inherited market_hash_name
→ one real SteamDT GET /open/cs2/v1/price/single attempt
→ get_steamdt_market_data(...)
→ select_buff_output_price(...)
→ SteamDTBuffPriceProvider.get_price(...)
→ PriceQuote(price_cny, source="steamdt:buff")
```

The smoke is standalone operator tooling. It is not application, scheduler, cache, valuation, recipe, or purchase wiring.

## Public and CLI contract

`scripts/run_live_steamdt_buff_price_provider_smoke.py` supports direct-file and module execution and exposes:

```python
async def async_main(
    environ: Mapping[str, str] | None = None,
    *,
    printer: Callable[[str], None] = print,
    runtime_factory: SteamDTBuffProviderSmokeRuntimeFactory | None = None,
) -> int: ...


def main() -> None: ...
```

There are no CLI arguments. The runtime factory is the only test injection seam. The provider, aggregate helper, and selector cannot be replaced through the public API.

## Environment and guard order

Reuse exactly:

```text
STEAMDT_API_KEY
STEAMDT_SMOKE_MARKET_HASH_NAME
STEAMDT_BASE_URL
```

Add one independent gate only:

```text
STEAMDT_RUN_BUFF_PROVIDER_SMOKE=false
```

Read inherited process environment in this strict order:

1. gate;
2. API key;
3. market hash name;
4. base URL;
5. runtime/network.

Only `raw.strip().lower() == "true"` enables the harness. The key and market name are stripped before use. The harness does not load `.env`, inspect files or shell history, prompt for values, use application settings, or print values.

Guard outcomes are:

```text
live_smoke_executed: no
reason: opt_in_disabled | api_key_missing | market_hash_name_missing
SteamDT requests sent: 0
```

Gate off exits 0. Missing key or name after opt-in exits 1. All guard outcomes perform zero network and create no runtime.

## One-request runtime

One enabled process owns:

- one `httpx.AsyncClient`;
- redirects disabled;
- one request-count event hook;
- one existing `SteamDTHttpClient`;
- `SteamDTClientConfig(max_retries=0, dry_run=False)`;
- the existing client-owned in-memory endpoint limiter;
- one `SteamDTBuffPriceProvider`;
- one `provider.get_price(market_hash_name)` invocation.

The provider borrows the client and owns no lifecycle. The harness closes every owned HTTP resource after success, ordinary failure, or process-control failure. If SteamDT client construction fails after HTTP client construction, the HTTP client is still closed.

The only allowed request is one application-level attempt to:

```text
GET /open/cs2/v1/price/single
query item count: 1 marketHashName
```

The request hook must attest exactly one attempt. Zero, more than one, invalid, or unreadable counts fail closed. There is no command retry, fallback, loop, second item, provider batch call, official batch/base/avg/kline/wear call, redirect follow, task, thread, scheduler, or background operation.

## BUFF-only price contract

The harness must construct the real `SteamDTBuffPriceProvider` and call its single-item method. It must not call the aggregate helper or selector directly and must not duplicate HTTP parsing, exact-platform selection, sell-price validation, or quote construction.

The inherited authorities require:

- exact case-sensitive `platform == "BUFF"`;
- exactly one exact BUFF record;
- exact finite positive `Decimal sell_price_cny`;
- fixed `PriceQuote.source == "steamdt:buff"`;
- `PriceQuote.raw is None`.

`bidding_price_cny` never participates. STEAM, YOUPIN, C5, HALOSKINS, every other platform, and metadata zero never provide fallback. The selected gross aggregate sell value is interpreted as CNY/RMB under the explicit project assumption, not an official current SteamDT currency guarantee. It is not an executable listing or guaranteed proceeds.

## Success contract

Success requires a valid returned `PriceQuote`, exact requested identity, exact positive finite Decimal price, fixed source/raw contract, and exactly one attempted request. Output is exactly:

```text
live_smoke_executed: yes
result: success
market_hash_name_requested: yes
source: steamdt:buff
price_quote_present: yes
price_cny: <exact Decimal value>
SteamDT requests sent: 1
```

The actual market name is never printed.

## Ordinary failure contract

A `SteamDTBuffPriceSelectionError` exposes only its existing allowlisted enum value:

```text
invalid_market_data
buff_record_missing
duplicate_buff_records
buff_sell_price_missing
buff_sell_price_non_finite
buff_sell_price_non_positive
```

All other ordinary provider/runtime failures use one fixed reason. Invalid returned quote/count and close failures also use fixed reasons:

```text
live_smoke_executed: yes
result: failed
reason: <selection reason | price_provider_failed | provider_result_invalid | request_count_invalid | close_failed>
SteamDT requests sent: <nonnegative integer | unavailable>
```

No ordinary output includes exception type, message, repr, arguments, cause, traceback, response body, raw mapping, provider records, actual market name, API key, Authorization/header data, base/request URL, platform item ID, update time, bid, account/listing data, or purchase link. Result lines are buffered until owned cleanup completes; an ordinary close failure replaces pending output with `close_failed`.

If any readable count exceeds one, `request_count_invalid` takes precedence. A successful provider result also requires count exactly one.

## Process-control contract

`MemoryError`, `asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit`, and other non-ordinary `BaseException` values propagate by identity after cleanup. They produce no partial summary, begin no later request, and return no result. A process-control cleanup failure propagates. An ordinary cleanup failure cannot suppress an already-active process-control exception.

## Offline tests

Automated tests perform zero real network requests and at minimum cover:

1. gate off and false-like gates with zero runtime/network;
2. missing/blank key with zero network;
3. missing/blank market name with zero network;
4. strict environment-read order and trimming;
5. success through real provider/aggregate/policy with one fake client call;
6. exact `steamdt:buff` source and BUFF sell Decimal precision;
7. higher BUFF bid ignored;
8. higher other-platform values ignored;
9. no BUFF;
10. duplicate BUFF;
11. missing, nonfinite, zero, and negative BUFF sell;
12. no cross-platform or bid fallback;
13. request count exactly one and invalid-counter failures;
14. `max_retries=0`, redirects disabled, one exact single endpoint request through local HTTPX transport;
15. representative 500, 429, and malformed response make one attempt only;
16. no batch/base/avg/kline/wear, SteamApis, Redis/cache, EV/ROI/risk, scheduler, or background path;
17. secret, raw response, actual market name, IDs, bids, and nested ordinary errors absent from output;
18. cleanup on every ordinary path;
19. process-control propagation by identity;
20. direct and module disabled entrypoints are zero-network safe.

## Allowed files

New:

- `scripts/run_live_steamdt_buff_price_provider_smoke.py`
- `tests/test_live_steamdt_buff_price_provider_smoke.py`
- `specs/2026-08-15-steamdt-buff-price-provider-live-smoke/plan.md`
- `specs/2026-08-15-steamdt-buff-price-provider-live-smoke/requirements.md`
- `specs/2026-08-15-steamdt-buff-price-provider-live-smoke/validation.md`

Modified:

- `.env.example`
- `docs/STEAMDT_API_NOTES.md`

No other path may change.

## Exclusions

Do not modify any client, aggregate service, BUFF selector/provider, A3 composition, `PriceQuote`/`PriceProvider`, valuation, recipe, EV/ROI/risk, SteamApis, Redis/cache/limiter, scheduler, Discord, FastAPI, Docker/database, dependency, or application configuration file.

Do not perform a real SteamDT request during implementation or ordinary validation. Do not connect SteamApis, commit, push, or begin Step 2M-A5.
