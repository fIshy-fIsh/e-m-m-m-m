# Phase 13A Step 2L-PIVOT-R1 — Requirements

## Purpose

Make SteamDT the current MVP primary source for item/platform aggregate market data and valuation input. Preserve all completed SteamApis code as optional future listing-level infrastructure; do not connect or modify it in this phase.

## Official provider facts and project interpretation

Current official SteamDT documentation identifies:

- base URL `https://open.steamdt.com`;
- `Authorization: Bearer {API_KEY}` authentication;
- `GET /open/cs2/v1/price/single` with `marketHashName`;
- `POST /open/cs2/v1/price/batch` with `marketHashNames`;
- aggregate records containing `platform`, `platformItemId`, `sellPrice`, `sellCount`, `biddingPrice`, `biddingCount`, and `updateTime`.

The current official documentation does not explicitly guarantee the currency of `sellPrice` or `biddingPrice`. The user nevertheless explicitly authorizes this project interpretation:

```text
SteamDT sellPrice and biddingPrice are treated as CNY/RMB by this project.
```

This assumption permits continued use of existing `sell_price_cny`, `bidding_price_cny`, and selected `PriceQuote.price_cny` contracts. It must never be described as an explicit current SteamDT documentation guarantee. No currency-neutral migration or exchange-rate conversion is part of this phase.

## Aggregate market-data boundary

The new service must reuse the existing `SteamDTPlatformPrice` rather than duplicate it. Its immutable result contains one exact canonical requested market hash name and provider-ordered platform quotes.

The service must:

- require an exact nonblank string without surrounding whitespace;
- invoke one injected `get_price_single_candidates()` method exactly once;
- accept an ordered sequence containing only exact `SteamDTPlatformPrice` values;
- preserve exact platform spelling/case and duplicate platform records;
- preserve optional platform-local item ID, CNY-interpreted sell/bid values, counts, and opaque update time;
- reconstruct every quote with `raw=None`;
- preserve an empty provider result as an empty tuple;
- retain provider order without sorting or deduplication.

It must not select a platform, synthesize a purchase URL or listing ID, parse an ID, expose raw provider mappings, access cache/Redis, or import SteamApis, BUFF, valuation, EV, risk, recipe, scheduler, or runtime boundaries.

## Listing-level limitation

The documented SteamDT price endpoints provide item/platform aggregate records, not a proven individual buyable listing feed. This phase must not claim or synthesize:

- individual listing identity;
- purchase links;
- per-listing float or inspect link;
- seller/account provenance;
- authoritative BUFF identity.

`platform_item_id` remains an opaque provider platform-local item identity only.

## Live smoke guards

The live market smoke must reuse exactly:

```text
STEAMDT_RUN_PRICE_SNAPSHOT_SMOKE
STEAMDT_API_KEY
STEAMDT_SMOKE_MARKET_HASH_NAME
```

Only trimmed, case-insensitive exact `true` enables the smoke. Gate evaluation precedes key, market name, base URL, client, and network access. Missing or blank key or market name exits safely with zero network. Values come only from the inherited current process environment; the script must not load `.env`, search files/history, prompt for credentials, or add a second key/gate/input name.

## One-request runtime

One enabled process must construct:

- one owned `httpx.AsyncClient` with redirects disabled;
- one existing `SteamDTHttpClient`;
- `SteamDTClientConfig(max_retries=0, dry_run=False)`;
- one aggregate service invocation;
- one `GET /open/cs2/v1/price/single` request for one trimmed market hash name.

The HTTP request hook must attest exactly one outbound attempt. No command-level retry, loop, sleep, fallback, second item, background task/thread, scheduler, Redis, official batch, base, avg, kline, or wear call is allowed. Existing single-endpoint in-memory rate limiting remains client-owned.

Owned HTTP resources must close on success, ordinary failure, cancellation, memory failure, and process-control failure. Ordinary failures use fixed safe output and a safe exception type only. Process-control exceptions propagate after cleanup.

## Live outcomes and output

Disabled or missing-guard output reports only:

```text
live_smoke_executed: no
reason: <fixed category>
SteamDT requests sent: 0
```

A parsed empty result is a failure with `reason: no_platform_records`; it must not retry.

Success requires a nonempty result and exactly one attempted request. Output may include only:

```text
live_smoke_executed: yes
result: success
market_hash_name_requested: yes
platform_count: N
platform: <escaped/redacted exact provider value>
platform_item_id_present: yes/no
sell_price_cny: <value or missing>
sell_count: <value or missing>
bidding_price_cny: <value or missing>
bidding_count: <value or missing>
update_time_present: yes/no
SteamDT requests sent: 1
```

Platform blocks must follow provider response order. The script must not output the requested name itself, platform item ID, update-time value, API key, Authorization/header data, base URL, raw JSON/response, raw mapping, Cookie/account/seller data, nested exception text, traceback, purchase URL, or listing identity. It must write no file, log, database, Redis state, or cache.

## Provider assumption test

One offline test in `tests/test_steamdt_market_data.py` must exercise an official-shaped single response through the existing HTTP client and `SteamDTPriceProvider`, confirming the user-approved project interpretation reaches `PriceQuote.price_cny` with source `steamdt`. The test name and comments must state this is a project assumption, not proof of an official provider currency guarantee. Production provider and valuation code remain unchanged.

## Documentation and source priority

Documentation must state:

- SteamDT is now the current primary aggregate market-data and valuation source;
- SteamApis is retained unchanged as an optional future listing-level source;
- the CNY meaning is user-approved project interpretation, not an explicit current provider documentation guarantee;
- platform strings are preserved exactly;
- the smoke uses only one single-price request with no retries;
- the smoke calls no batch/base/avg/kline/wear endpoint;
- full Step 2F live valuation runtime wiring is deferred to Step 2M;
- no automatic purchase, login, Cookie acquisition, browser automation, CAPTCHA/risk-control bypass, or marketplace write is added;
- this phase is not production-ready.

## Scope

Allowed paths are:

```text
app/services/steamdt_market_data.py
tests/test_steamdt_market_data.py
scripts/run_live_steamdt_market_smoke.py
tests/test_live_steamdt_market_smoke.py
README.md
docs/STEAMDT_API_NOTES.md
docs/STEAMAPIS_MARKET_DATA_NOTES.md
specs/2026-08-14-steamdt-market-data-cny-assumption/plan.md
specs/2026-08-14-steamdt-market-data-cny-assumption/requirements.md
specs/2026-08-14-steamdt-market-data-cny-assumption/validation.md
```

`.env.example` already contains all required variables and must remain unchanged. Core SteamDT client/parser/provider/valuation, caches/limiters, all SteamApis/BUFF modules, runtime/scheduler/FastAPI/Discord, dependencies, Docker, and database files must remain unchanged.

No commit, push, or Step 2M work is allowed.
