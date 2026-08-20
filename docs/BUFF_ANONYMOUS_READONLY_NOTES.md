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

## Probed response shape

For current compatibility only, the harness checks:

```text
code == "OK"
data.items is a nonempty list
items[0].id is a present compatible sell-order identifier
items[0].price is finite and greater than zero
items[0].asset_info.paintwear is finite and within [0,1]
```

It optionally reports only whether `asset_info.assetid` and `asset_info.paintseed` are present. It inspects exactly the first item, ignores later items and unknown fields, requests no second page, and calls no wear or other enrichment endpoint.

Third-party behavior evidence indicates `items[].id` is used as a sell-order ID. This harness tests that current compatibility behavior only; it does not establish official BUFF identity semantics. Price and paintwear acceptance prove only parseable first-item fields, not confirmed currency, fee inclusion, availability at purchase time, or transaction actionability.

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
