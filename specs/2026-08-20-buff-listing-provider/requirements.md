# Phase 13C — Requirements

## Purpose

Promote the manually validated anonymous BUFF sell-order compatibility probe into a reusable, read-only listing-provider abstraction:

```text
explicit goods_id
→ one anonymous first-page GET
→ strict all-item parser
→ list[BuffListing]
```

This phase does not scan a watchlist, qualify listings, construct solver candidates, run trade-up calculations, value outputs, evaluate EV/ROI/risk, schedule work, connect SteamApis, alter SteamDT, or perform any transaction.

The endpoint remains unofficial empirical compatibility evidence, not BUFF OpenAPI or a stable production guarantee.

## Frozen decisions

- `market_hash_name` is optional and this parser sets it to `None`; no response name field was verified.
- `asset_id` is required as a nonblank string for every listing.
- Any invalid item rejects the complete page atomically.
- Missing or null `paintseed` maps to `None`; present invalid seed rejects the page.
- The requested DTO uses `price_cny`; this is a project-facing interpretation and not proof of official currency or fee semantics.
- Goods ID comes from validated request context, not the response.
- Empty exact `items` returns `[]`.
- Page size remains omitted because its wire contract is unverified.

## Public client contract

`app/clients/buff_anonymous_listing_client.py` exports:

```python
BUFF_ANONYMOUS_BASE_URL
BUFF_ANONYMOUS_SELL_ORDER_PATH
BUFF_ANONYMOUS_USER_AGENT
BuffAnonymousListingRequestError
BuffAnonymousListingPayloadClient
BuffAnonymousListingHttpClient
validate_buff_anonymous_listing_request
```

`BuffAnonymousListingPayloadClient` provides:

```python
async def fetch_sell_order_payload(self, goods_id: str) -> bytes: ...
```

The concrete client borrows an injected `httpx.AsyncClient`, owns no lifecycle, and performs one bodyless GET per call with exact ordered query:

```text
game=csgo
goods_id=<canonical exact string>
page_num=1
sort_by=default
```

It sends no page size, float/seed/price filter, search, second page, retry, fallback, Cookie, Authorization, API key, session, Device-Id, CSRF, Referer, X-Requested-With, browser state, proxy, or transaction request. A 2xx response returns detached bytes. Ordinary transport or non-2xx failures raise one fixed cause-less request error. Process-control values propagate.

The request validator checks exact method, scheme, host, port, path, ordered query, empty body, fixed User-Agent/Accept, no URL userinfo, and no sensitive/browser/session headers.

## Listing DTO

`app/services/buff_listing_provider.py` exports:

```python
BuffListing
BuffListingProviderError
parse_buff_listing_response
BuffListingProvider
```

`BuffListing` is frozen, keyword-only, and repr-suppressed:

```python
listing_id: str
goods_id: str
market_hash_name: str | None
price_cny: Decimal
paintwear: Decimal
asset_id: str
paintseed: int | None
source: str
```

Validation requires:

- exact nonblank already-trimmed strings for listing, goods, and asset IDs;
- market name `None` or exact nonblank already-trimmed string;
- exact finite positive Decimal price;
- exact finite Decimal paintwear in inclusive `[0,1]`;
- seed `None` or exact nonnegative integer excluding bool;
- source exactly `buff`.

No raw payload, quantity, seller/account, URL, inspect data, timestamp, auth, or transaction field enters the DTO.

## Parser contract

```python
parse_buff_listing_response(
    payload: bytes,
    *,
    goods_id: str,
) -> list[BuffListing]
```

The parser:

- requires exact bytes and canonical request-context goods ID;
- strictly decodes JSON with fractional numbers as Decimal;
- rejects duplicate keys and bare nonstandard constants;
- requires exact top-level object, exact `code == "OK"`, exact object `data`, and exact list `data.items`;
- maps every item in provider order;
- preserves duplicate listing occurrences;
- uses item `id`, `price`, `asset_info.paintwear`, required `asset_info.assetid`, and optional `asset_info.paintseed` only;
- ignores apparent name, quantity, unknown, seller, URL, and other fields;
- sets `market_hash_name=None` and `source="buff"`;
- returns `[]` for an empty exact item list;
- builds privately and returns no partial list when any item is invalid.

Accepted price/wear lexical forms are exact nonblank already-trimmed strings, JSON fractional Decimals, or exact integers excluding bool. Price must be finite and positive; wear must be finite and `[0,1]`. Asset ID is an exact nonblank string. Missing/null seed maps to `None`; present seed must be exact nonnegative integer.

`BuffListingProviderError` has one fixed message, a stable allowlisted reason, and optional zero-based item index. It exposes no payload, value, ID, price, URL, provider message, nested exception, or original cause.

## Provider contract

```python
class BuffListingProvider:
    def __init__(self, client: BuffAnonymousListingPayloadClient) -> None: ...

    async def get_listings(self, goods_id: str) -> list[BuffListing]: ...
```

The provider borrows the client, owns no lifecycle/config/task/cache, validates and strips goods ID before I/O, calls the client exactly once, calls the parser exactly once, and returns an independently constructed ordered list. It adds no qualification, solver, valuation, retry, pagination, fallback, enrichment, or partial-result behavior.

## Shared smoke runtime

`scripts/buff_listing_smoke_utils.py` owns one `httpx.AsyncClient` with:

```text
timeout=10
follow_redirects=False
trust_env=False
Accept=application/json
fixed transparent User-Agent
```

It exposes a runtime containing the shared payload client and exact attempted/dispatched/budget-exceeded state. A pre-send hook blocks attempt two before transport and validates attempt one with the public request validator. The runtime closes the owned client; providers borrow it.

Both BUFF live smoke scripts must use this utility. Application code never imports scripts.

## Historical schema smoke refactor

The existing anonymous schema smoke retains its gate, goods-ID guards, fixed output/failure vocabulary, cleanup, one-request budget, and direct/module entrypoints, but delegates both request and parsing to `BuffListingProvider`.

It no longer owns HTTP or JSON/Decimal field parsing. It validates the complete page atomically, requires a nonempty list, and derives only safe flags from the first typed DTO. Missing seed remains success. Missing/invalid required asset ID or invalid later item is now a schema failure.

The historical manually observed first-item result remains documentation evidence and is not converted into fixture data or a permanent provider expectation.

## Provider smoke

`scripts/run_live_buff_listing_provider_smoke.py` is independently gated by:

```text
BUFF_RUN_LISTING_PROVIDER_SMOKE=false
```

It reuses `BUFF_READONLY_SMOKE_GOODS_ID`, inherited process environment only, and the shared runtime/provider. It calls the provider once, requires at least one listing, and prints only:

```text
live_smoke_executed: yes
result: success
listing_count: <nonnegative count>
first_listing_id_present: yes
first_listing_price_valid: yes
first_listing_paintwear_valid: yes
BUFF requests sent: 1
```

The count is the only collection value disclosed. It never prints goods/listing/asset IDs, market name, price, wear, seed, source record, body, headers, URL, provider message, exception type/message, repr, or traceback.

It remains anonymous, read-only, no-Cookie, no-login, no-auth, one-request, no-retry, no-page-two, no-fallback, and disabled by default. Implementation validation does not execute it.

## Fixture and tests

Add one synthetic provider-shaped fixture containing two valid ordered records: one with a valid seed and one without seed. It is project-owned, not a captured live response. Unknown name/quantity-like fields prove those values are ignored.

Offline tests cover:

- exact client request and no forbidden params/headers/retry;
- request errors and process control;
- borrowed client lifecycle;
- exact DTO validation, immutability, repr, fixed source;
- precise Decimal mapping and request-context goods ID;
- nullable market name, required asset ID, optional seed;
- strict JSON, all envelope/item failures, duplicate keys/nonfinite constants;
- atomic invalid-later-item rejection, order and duplicates, empty list;
- one provider client call and no lifecycle ownership;
- refactored schema smoke provider delegation and existing safety contracts;
- provider smoke guards, safe output, count/request/lifecycle/error behavior;
- direct/module disabled entrypoints and socket/DNS block;
- no scanner, CandidateListing, qualification, solver, SteamDT, SteamApis, valuation, EV/risk, scheduler, Redis, purchase/login/browser/evasion behavior;
- protected modules do not reverse-import the new provider/smokes.

## Configuration

Only `.env.example` adds the independent provider-smoke gate. No app `Settings`, enabled provider setting, or page-size variable is added because the provider is not pipeline-wired and page-size semantics are unverified. Existing behavior remains unchanged and disabled.

## Documentation

Update anonymous compatibility notes and official-unknown BUFF notes to distinguish:

- empirically validated anonymous fields versus official guarantees;
- request-context goods ID;
- nullable/unverified market name;
- required string asset ID as Phase 13C's fail-closed parser contract;
- optional seed;
- project-facing CNY naming without official currency/fee guarantee;
- atomic complete-page validation;
- no production wiring, pagination, rate limit, freshness, facts, purchase handoff, or raw retention.

## Protected scope

Do not modify legacy `BuffHttpClient`, Phase 12 BUFF domain/parser/facts/qualification/adapters, `CandidateListing`, scanner, pipeline, scheduler, app config, solver, engine, valuation, EV/risk, SteamDT, SteamApis, Redis, Discord, database, Docker, dependencies, or purchase/account behavior.

## Commit

All implementation/tests/docs/specs form one cohesive change. After offline validation, stage once and create exactly one commit after `04ba133818e227744f1fa091d5a571f2518d6c66`:

```text
add buff listing provider abstraction
```

Do not push or run either live BUFF smoke.
