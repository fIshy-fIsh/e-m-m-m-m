# BUFF Anonymous Read-only Compatibility Notes

## Status and authority

This project includes a disabled-by-default research harness for one empirical compatibility probe:

```text
GET https://buff.163.com/api/market/goods/sell_order
game=csgo
goods_id=<explicit nonsecret input>
page_num=1
sort_by=default
```

This is **not official BUFF OpenAPI**, not a production API mapping, and not a guarantee that the endpoint, anonymous access, query, or response schema will remain available. The probe is intentionally separate from the unimplemented `BuffHttpClient` and from the synthetic Phase 12 fixture schema. Official and production-mapping uncertainties remain tracked in `docs/BUFF_API_NOTES.md`.

## Anonymous and read-only boundary

`scripts/run_live_buff_anonymous_sell_order_schema_smoke.py` runs only when inherited `BUFF_RUN_ANONYMOUS_SELL_ORDER_SCHEMA_SMOKE` is explicit normalized `true` and inherited `BUFF_READONLY_SMOKE_GOODS_ID` is a nonblank string. It does not load `.env`, derive or search for a goods ID, or read any BUFF key, secret, Cookie, browser, login, device, CSRF, proxy, or session state.

The request is one anonymous bodyless GET through one owned HTTPX client. Redirects and inherited environment proxies are disabled. A pre-send guard enforces the exact host/path/query/header contract and blocks a second attempt before transport. There is no retry, fallback, second page, pagination loop, filter expansion, random or rotating User-Agent, proxy rotation, browser simulation, CAPTCHA/Cloudflare/risk-control bypass, login, purchase preview, purchase, or marketplace write.

If anonymous access is rejected or unavailable, the correct outcome is a fixed safe failure. The harness does not add browser-like headers or attempt circumvention.

## Historical Phase 13B probe evidence

The original Step 2B probe inspected exactly the first returned item, ignored later items, and recorded only passive first-item presence for asset ID and seed. Its one authorized manual run proved a compatible first-item ID, positive price, bounded paintwear, non-null asset ID, and absent/null seed at that moment. That historical evidence did not establish all-item coverage, asset type, or long-term field availability.

Phase 13C supersedes the script-local first-item parser with the reusable provider below. The current smoke now validates the complete returned item list atomically, requires every item to carry a nonblank string asset ID, and keeps only paint seed optional. It still requests no second page and calls no enrichment endpoint.

## Output and data retention

Success output contains only fixed anonymous/read-only/page/schema-validity flags, optional-field presence flags, and request count. It never prints or documents concrete:

- goods, listing, seller, account, asset, or market identity;
- price, float, seed, or market name;
- request URL/query, response body, provider message, headers, or cookies;
- exception type/message/repr/cause or traceback.

The raw response is not retained as a fixture, production expectation, or provider mapping.

## Exclusions and limitations

The smoke does not construct `BuffListingObservation`, qualify a listing, build `CandidateListing`, invoke metadata/solver/EV/ROI/risk, connect SteamDT or SteamApis, use Redis, schedule work, alert, open a browser, or execute a transaction. Success proves only that one anonymous response currently matches the narrow first-item schema probe.

It does not prove:

- complete marketplace inventory or pagination;
- listing freshness, removal, or continued availability;
- authoritative goods/listing identity beyond the observed compatibility field;
- price currency, acquisition fees, settlement behavior, or executable cost;
- manual purchase URL or safe purchase handoff;
- production readiness of direct BUFF ingestion.

All automated tests use fake runtimes or local HTTPX transports and perform zero real network. Implementation and offline validation do not execute the live smoke; a later manual run requires an explicit user decision after commit.

## Phase 13D-0 goods identity bridge status

The anonymous listing request consumes an explicit caller-provided `goods_id`; it does not discover that ID and the response parser does not extract or verify a canonical `market_hash_name`. `BuffListing.market_hash_name` therefore remains `None`.

A repository audit found no verified live `market_hash_name ↔ goods_id` mapping. Phase 13D-0 adds only the immutable `BuffItemIdentity` shape and asynchronous `BuffItemIdentityResolver` protocol. `None` is the normal unresolved outcome. There is no concrete resolver, mapping table, fixture, endpoint, configuration, cache, or provider integration, and no identity is derived from listing ID, asset ID, SteamDT platform IDs, SteamApis compatibility IDs, URLs, hashes, seeds, or item-name syntax.

A later implementation may satisfy the resolver only after separately verified mapping evidence exists. Until then, the anonymous provider remains keyed by a pre-known goods ID and cannot be invoked authoritatively from a market name.

## Phase 13C reusable listing provider

Phase 13C extracts the empirical request and response logic into one shared anonymous client and one provider. `BuffListingProvider.get_listings(goods_id)` performs one borrowed-client call and returns an ordered list of immutable `BuffListing` values. The parser validates every returned item atomically; any malformed item rejects the complete page, while an exact empty item list returns an empty list.

The mapped fields are deliberately narrow:

- `listing_id` comes from exact `items[].id`;
- `goods_id` comes from the explicit validated request context;
- `price_cny` is the positive finite `items[].price` under a project-facing CNY interpretation, not an official currency or fee guarantee;
- `paintwear` comes from finite `[0,1]` `items[].asset_info.paintwear`;
- required `asset_id` comes from a nonblank string `items[].asset_info.assetid`;
- absent/null `items[].asset_info.paintseed` becomes `None`, while a valid present integer is retained;
- `market_hash_name` remains `None` because no response name path has been verified;
- `source` is fixed to `buff`.

Unknown names, quantity-like values, seller/account fields, links, raw payload, and transaction data are discarded. The provider does not implement Phase 12 qualification, facts, `CandidateListing`, scanner, solver, EV/ROI/risk, pagination, cache, scheduling, or production wiring.

The current client constructs the absolute request independently from the injected HTTPX client's base URL, default query, headers, cookies, authentication, and redirect setting. It validates an exact request/header allowlist before dispatch, explicitly disables per-send authentication and redirects, and borrows rather than mutates or closes caller-owned HTTP state. `BuffListingProvider.get_listings()` is the only boundary that strips external goods-ID padding; the client request validator, direct parser, DTO, listing ID, optional market name, and asset ID require exact already-canonical strings.

The historical schema smoke and the independently gated provider smoke both reuse the same client, provider, and one-request runtime. They remain anonymous, no-Cookie, no-login, no-auth, no-retry, first-page-only, and disabled by default. Phase 13C automated validation does not execute either live smoke and does not retain a live response fixture.
