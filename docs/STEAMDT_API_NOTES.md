# SteamDT API Notes

## Source Links

* https://www.steamdt.com/
* https://github.com/Kir4kami/mcp-steamdt
* https://doc.steamdt.com/
* https://doc.steamdt.com/273806087e0

## Confirmed Information

### Base URL
- `https://open.steamdt.com`

### Authentication 方式
- Confirmed from the SteamDT general documentation page: Bearer token authentication.

### API key 如何传递
- Confirmed from the SteamDT general documentation page: `Authorization: Bearer {API_KEY}`

### 是否需要 signature
- Confirmed from the SteamDT general documentation page: no signature mechanism is currently required.

### 请求 headers
- Confirmed from the SteamDT general documentation page:
  - `Authorization: Bearer {API_KEY}`
  - `Content-Type: application/json` appears in curl examples

### rate limit
- TODO: Not confirmed yet.

### price single endpoint
- Confirmed endpoint name: `通过 marketHashName 查询饰品价格`
- Method: `GET`
- Path: `/open/cs2/v1/price/single`

### price batch endpoint
- Confirmed endpoint name: `通过 marketHashName 批量查询饰品价格`
- Method: `POST`
- Path: `/open/cs2/v1/price/batch`

### base item info endpoint
- Confirmed endpoint name: `获取 steam 饰品基础信息`
- Method: `GET`
- Path: `/open/cs2/v1/base`

### kline / historical price endpoint
- Confirmed endpoint name: `查询 steam 饰品 K 线数据`
- Method: `POST`
- Path: `/open/cs2/item/v1/kline`

### wear endpoint
- Confirmed endpoint name: `通过检视链接查询磨损度相关数据`
- Method: `POST`
- Path: `/open/cs2/v1/wear`
- Example full URL shown in docs: `https://open.steamdt.com/open/cs2/v1/wear`

### request params
- Confirmed for price single endpoint:
  - `marketHashName`
- Confirmed for price batch endpoint body:
  - `marketHashNames: list[str]`
- Confirmed for 7-day average price endpoint query:
  - `marketHashName`
- Confirmed for kline endpoint body:
  - `marketHashName`
  - `type`
  - `platform`
  - `specialStyle`
- Confirmed for wear endpoint body:
  - `notifyUrl`
  - `inspectUrl`
- Other endpoint params:
  - TODO: Not confirmed yet.

### response fields
- Confirmed common response wrapper fields shown in docs:
  - `success`
  - `data`
  - `errorCode`
  - `errorMsg`
  - `errorData`
  - `errorCodeStr`
- Confirmed endpoint-specific fields:
  - price single `data[]`:
    - `platform`
    - `platformItemId`
    - `sellPrice`
    - `sellCount`
    - `biddingPrice`
    - `biddingCount`
    - `updateTime`
  - price batch `data[]`:
    - `marketHashName`
    - `dataList`
  - price batch `dataList[]`:
    - `platform`
    - `platformItemId`
    - `sellPrice`
    - `sellCount`
    - `biddingPrice`
    - `biddingCount`
    - `updateTime`
  - 7-day average price `data`:
    - `marketHashName`
    - `avgPrice`
    - `dataList`
  - 7-day average price `dataList[]`:
    - `platform`
    - `avgPrice`
  - wear `data`:
    - `sync`
    - `success`
    - `taskId`
    - `itemPreviewData`
  - wear `itemPreviewData`:
    - `assetId`
    - `defindex`
    - `paintindex`
    - `rarity`
    - `quality`
    - `paintwear`
    - `floatWear`
    - `paintseed`
    - `stickers`
    - `keychains`
  - wear `stickers[]`:
    - `stickerId`
    - `slot`
    - `wear`
  - wear `keychains[]`:
    - `id`
    - `pattern`
  - base item info `data[]`:
    - `name`
    - `marketHashName`
    - `platformList`
  - base item info `platformList[]`:
    - `name`
    - `itemId`
  - kline `data`:
    - TODO: exact point fields are not confirmed yet; docs example appears as nested array only.

### error response format
- Confirmed: response wrapper contains `success`, `errorCode`, `errorMsg`, `errorData`, `errorCodeStr`.
- Confirmed: failed responses use the same wrapper shape.

### timestamp 格式
- TODO: Not confirmed yet.

### currency 字段
- TODO: Not confirmed yet.

### price 字段精度
- TODO: Not confirmed yet.

### item name / market_hash_name 字段
- Confirmed on batch and avg/base endpoints: `marketHashName` appears explicitly.
- Confirmed on base endpoint: `name` appears explicitly.
- Price single response item-level `marketHashName` is not clearly shown; request `marketHashName` may need to be echoed internally.

### 是否支持批量查询
- Confirmed: yes, via `/open/cs2/v1/price/batch`

### 是否支持饰品基础信息
- Confirmed: yes, via `/open/cs2/v1/base`

### 是否支持历史价格
- Confirmed: kline/history-like endpoint exists via `/open/cs2/item/v1/kline`
- TODO: exact field-level historical price semantics are not confirmed yet.

### 是否支持 inspect / wear 查询
- Confirmed: yes, via `/open/cs2/v1/wear`

### 7-day average price endpoint
- Confirmed endpoint name: `通过 MarketHashName 查询所有平台近 7 天均价`
- Method: `GET`
- Path: `/open/cs2/v1/price/avg`
- Query params:
  - `marketHashName`
- Confirmed response data shape:
  - `marketHashName`
  - `avgPrice`
  - `dataList`
  - `dataList[].platform`
  - `dataList[].avgPrice`

### protocol / encoding
- Confirmed: HTTPS.
- Confirmed: UTF-8 is stated for requests and responses.

## Price Single Endpoint

### Name
- `通过 marketHashName 查询饰品价格`

### Method
- `GET`

### Path
- `/open/cs2/v1/price/single`

### Query params
- `marketHashName`

### Purpose
- 获取全平台饰品价格、求购等数据。

### Confirmed response data shape
- `data` is a list of platform price records:
  - `platform`
  - `platformItemId`
  - `sellPrice`
  - `sellCount`
  - `biddingPrice`
  - `biddingCount`
  - `updateTime`

### Internal mapping notes
- `market_hash_name` should come from request `marketHashName`, because the single response item does not clearly show `marketHashName`.
- Price candidate fields:
  - `sellPrice` may map to sell price candidate
  - `biddingPrice` may map to buy order / bid price candidate
  - `platform` may map to platform source
  - `updateTime` may map to quote timestamp if timestamp unit is confirmed
- TODO: timestamp unit is not confirmed yet.
- TODO: currency is not confirmed yet.

## Price Batch Endpoint

### Name
- `通过 marketHashName 批量查询饰品价格`

### Method
- `POST`

### Path
- `/open/cs2/v1/price/batch`

### Body
- `marketHashNames: list[str]`

### Purpose
- 批量查询饰品价格、求购等数据。

### Confirmed response data shape
- `data` is a list of batch price records:
  - `marketHashName`
  - `dataList`
- `dataList` contains platform price records:
  - `platform`
  - `platformItemId`
  - `sellPrice`
  - `sellCount`
  - `biddingPrice`
  - `biddingCount`
  - `updateTime`

### Internal mapping notes
- `marketHashName` maps to internal `market_hash_name`.
- `dataList` contains platform-level price candidates.
- For V1.1 valuation, the conservative selected price should not be decided in `SteamDTClient`.
- Price selection should be handled later in `PriceProvider / ValuationService`.
- Possible future strategy:
  - choose lowest positive `sellPrice`
  - or choose platform-weighted / liquidity-aware `sellPrice`
  - or use avg endpoint for sanity check
- Selection strategy remains TODO until PriceProvider phase.

## Item Kline Endpoint

### Name
- `查询 steam 饰品 K 线数据`

### Method
- `POST`

### Path
- `/open/cs2/item/v1/kline`

### Body
- `marketHashName`
- `type`
- `platform`
- `specialStyle`

### Purpose
- 查询饰品 K 线数据。
- 文档说明不包含成交数据。

### Confirmed response
- wrapper fields confirmed
- `data` appears as nested array in example

### TODO
- exact kline point fields
- timestamp field
- price field
- volume / OHLC field meaning
- `type` enum meaning
- `platform` enum
- `specialStyle` values
- timestamp unit

### Internal mapping
- Future `HistoricalPriceProvider` may use this endpoint.
- Do not implement parser until data fields are confirmed.

## 7-Day Average Price Endpoint

### Name
- `通过 MarketHashName 查询所有平台近 7 天均价`

### Method
- `GET`

### Path
- `/open/cs2/v1/price/avg`

### Query params
- `marketHashName`

### Confirmed response data shape
- `data`:
  - `marketHashName`
  - `avgPrice`
  - `dataList`
- `dataList`:
  - `platform`
  - `avgPrice`

### Internal mapping notes
- `avgPrice` may be useful for sanity check.
- platform-level `avgPrice` may help detect abnormal current `sellPrice`.
- It should not replace executable listing price.
- Useful for `RiskFilter` extension or `HistoricalPriceProvider`.

### TODO
- currency
- average calculation method
- whether `avgPrice` includes outliers
- whether `avgPrice` is based on listing price or transaction price
- whether `avgPrice` includes fees

## Base Item Info Endpoint

### Name
- `获取 steam 饰品基础信息`

### Method
- `GET`

### Path
- `/open/cs2/v1/base`

### Confirmed notes
- 文档说明所有接口数据都基于该接口返回的 `marketHashName`。
- 文档说明该接口每天只能调用一次，需要保存返回信息。

### Confirmed response data shape
- `data` is a list of base item records:
  - `name`
  - `marketHashName`
  - `platformList`
- `platformList`:
  - `name`
  - `itemId`

### Internal mapping
- `marketHashName` maps to internal `market_hash_name`.
- `name` may map to display/localized name.
- `platformList` can map platform name -> platform item id.
- This endpoint is useful for `MetadataProvider` fallback and cross-platform ID mapping.

### TODO
- exact daily reset timezone
- whether data includes rarity / collection / float min/max
- whether platform item id can help map BUFF goods_id
- whether names are localized or Steam official names

## Wear by Inspect URL Endpoint

### Name
- `通过检视链接查询磨损度相关数据`

### Method
- `POST`

### Path
- `/open/cs2/v1/wear`

### Body
- `notifyUrl`
- `inspectUrl`

### Confirmed response data shape
- `data`:
  - `sync`
  - `success`
  - `taskId`
  - `itemPreviewData`
- `itemPreviewData`:
  - `assetId`
  - `defindex`
  - `paintindex`
  - `rarity`
  - `quality`
  - `paintwear`
  - `floatWear`
  - `paintseed`
  - `stickers`
  - `keychains`
- `stickers`:
  - `stickerId`
  - `slot`
  - `wear`
- `keychains`:
  - `id`
  - `pattern`

### Internal mapping
- `floatWear` likely maps to `SteamDTWearInfo.float_value`, but string/number conversion must be handled carefully.
- `paintseed` maps to `SteamDTWearInfo.paint_seed`.
- `paintindex` may be useful as `paint_index`.
- `rarity` / `quality` / `defindex` may be useful for metadata sanity check.
- `raw` should preserve full response.

### TODO
- whether `floatWear` is always string
- whether `paintwear` and `floatWear` differ
- whether `sync=false` means async task required
- how to use `taskId`
- `notifyUrl` behavior
- failure states
- retry / polling behavior
- whether API key is required for this endpoint in all environments

## Internal Mapping Plan

### 1. SteamDTPriceQuote
Potential future mapping:
- `market_hash_name`
  - from batch response `marketHashName`
  - from single response request `marketHashName`
- `price_cny`
  - TODO: exact selection rule among `sellPrice` / `avgPrice` / platform records is not confirmed yet.
- `source`
  - internal constant recommendation: `"steamdt"`
- `raw`
  - preserve full raw payload

### 2. SteamDTBatchPriceResult
Potential future mapping:
- `quotes`
  - likely `marketHashName -> SteamDTPriceQuote`
  - TODO: exact quote selection strategy not confirmed yet.
- `missing`
  - names missing from batch response or with empty `dataList`
  - TODO: exact missing semantics not confirmed yet.
- `raw`
  - preserve full raw payload

### 3. SteamDTBaseItemInfo
Potential future mapping:
- `market_hash_name`
  - from `marketHashName`
- `raw`
  - preserve full raw payload

### 4. SteamDTHistoricalPricePoint
Potential future mapping:
- `market_hash_name`
  - from request `marketHashName`
- `timestamp`
  - TODO: not confirmed yet.
- `price_cny`
  - TODO: not confirmed yet.
- `raw`
  - preserve full raw payload

### 5. SteamDTWearInfo
Potential future mapping:
- `inspect_link`
  - from request `inspectUrl`
- `float_value`
  - likely from `floatWear`
  - TODO: exact type conversion and semantics not fully confirmed.
- `paint_seed`
  - from `paintseed`
- `raw`
  - preserve full raw payload

## Parser Status

当前已新增 parser skeleton：
- `parse_price_single_response`
- `parse_price_batch_response`
- `parse_avg_price_response`
- `parse_base_item_info_response`
- `parse_wear_response`
- `parse_kline_response` placeholder

说明：
- parser 当前只覆盖文档中已经确认的字段。
- `kline` point-level field mapping 仍然是 TODO。
- `SteamDTHttpClient` public methods 仍然保持 `NotImplementedError`。
- 当前仍然不真实请求 SteamDT。
- parser 尚未接入 production HTTP flow。
- price selection strategy 仍留给后续 provider/parser integration phase。

## Phase 6A Official Read-only Smoke Test

- Only `get_price_single` supports an official read-only smoke request at this stage.
- Default remains `DRY_RUN=true`, which prevents real SteamDT requests.
- Real requests are only allowed when `STEAMDT_DRY_RUN=false` and `STEAMDT_API_KEY` is explicitly provided.
- The only enabled official endpoint is:
  - `GET /open/cs2/v1/price/single`
- No non-official evasion techniques are used.
- No cookie scraping.
- No browser automation.
- No captcha bypass.
- No risk-control bypass.
- No hidden endpoints.
- No automated purchase.
- No automated login.
- Current temporary selection strategy is `lowest_positive_sell_price`.
- Parser skeleton already covers confirmed fields for:
  - `parse_price_single_response`
  - `parse_price_batch_response`
  - `parse_avg_price_response`
  - `parse_base_item_info_response`
  - `parse_wear_response`
  - `parse_kline_response` placeholder
- `kline` point mapping is still TODO.
- `SteamDTHttpClient` public methods other than `get_price_single` remain `NotImplementedError`.
- Parser is still not connected to production HTTP flow beyond the single official smoke request.
- Final price selection strategy remains a later provider/parser integration concern.

## Phase 6B Official Batch Price Smoke Test

- `get_price_batch` supports an official read-only smoke request at this stage.
- Endpoint: `POST /open/cs2/v1/price/batch`
- Request body: `marketHashNames`
- Default remains `DRY_RUN=true`, which prevents real SteamDT requests.
- Real requests are only allowed when `STEAMDT_DRY_RUN=false` and `STEAMDT_API_KEY` is explicitly provided.
- Current temporary selection strategy is `lowest_positive_sell_price` per requested `marketHashName`.
- Missing names do not raise; they are returned in `missing`.
- This smoke path does not integrate with pipeline / scheduler / alerts.
- No non-official evasion techniques are used.
- No cookie scraping.
- No browser automation.
- No captcha bypass.
- No risk-control bypass.
- No hidden endpoints.
- No automated purchase.
- No automated login.

## Phase 7 Liquidity-aware Price Selection

- Price selection strategy has been extracted from `SteamDTHttpClient` into a dedicated selector module.
- Supported strategies:
  - `lowest_positive_sell_price`
  - `liquidity_aware_sell_price`
- The liquidity-aware strategy can consider:
  - `sellPrice`
  - `sellCount`
  - `biddingPrice`
  - `biddingCount`
  - optional sell/bid spread
  - optional avg sanity check
- `avg` sanity check only consumes a provided `avg_price_cny`; it does not request the avg endpoint by itself.
- Current selector work is still isolated from pipeline / scheduler / alerts.
- Current implementation continues to avoid non-official evasion techniques.

## Phase 8A Official Avg Price Smoke Test

- `get_avg_price` supports an official read-only smoke request at this stage.
- Endpoint: `GET /open/cs2/v1/price/avg`
- Query param: `marketHashName`
- Default remains `DRY_RUN=true`, which prevents real SteamDT requests.
- Real requests are only allowed when `STEAMDT_DRY_RUN=false` and `STEAMDT_API_KEY` is explicitly provided.
- `avgPrice` is treated only as a future sanity-check input.
- It does not directly replace `sellPrice`-based valuation.
- This smoke path does not integrate with pipeline / scheduler / alerts.
- No non-official evasion techniques are used.
- No cookie scraping.
- No browser automation.
- No captcha bypass.
- No risk-control bypass.
- No hidden endpoints.
- No automated purchase.
- No automated login.

## Phase 8B Avg Sanity Check in Smoke Flow

- Avg sanity check is only used when a smoke script explicitly enables it.
- It uses the official endpoint: `GET /open/cs2/v1/price/avg`.
- `avgPrice` is passed into the selector as `avg_price_cny`.
- `max_price_to_avg_ratio` is used to reject obviously high `sellPrice` values.
- Avg sanity is disabled by default.
- Enabling it causes additional official read-only avg requests.
- `avgPrice` does not directly replace `sellPrice` valuation.
- Current smoke flows still do not integrate with pipeline / scheduler / alerts.
- No non-official evasion techniques are used.
- No cookie scraping.
- No browser automation.
- No captcha bypass.
- No risk-control bypass.
- No hidden endpoints.
- No automated purchase.
- No automated login.

## Phase 9 SteamDTPriceProvider Selector Integration

- `SteamDTPriceProvider` supports an injected `selection_config` for liquidity-aware price selection.
- Optional avg sanity check is supported at the provider layer.
- Avg sanity remains disabled by default.
- When enabled, the provider requests avg price through the injected client only.
- `avgPrice` is passed as sanity-check input and does not directly replace `sellPrice` valuation.
- The provider does not create a SteamDT HTTP client.
- The provider does not read environment variables.
- The current provider integration remains isolated from pipeline / scheduler / alerts.
- No non-official evasion techniques are used.
- No cookie scraping.
- No browser automation.
- No captcha bypass.
- No risk-control bypass.
- No hidden endpoints.
- No automated purchase.
- No automated login.

## Phase 10A SteamDTPriceProvider Manual Smoke Flow

- A manual `scripts/steamdt_provider_price_smoke.py` flow validates the provider layer with an injected `SteamDTHttpClient`.
- The flow uses official read-only SteamDT endpoints through the injected client only.
- Default remains dry-run; it does not make real SteamDT requests unless manually run with `STEAMDT_DRY_RUN=false` and an API key.
- Single and batch provider smoke modes are supported.
- Optional avg sanity check is supported through `SteamDTPriceProviderConfig`.
- `avgPrice` is only a sanity-check input and does not directly replace `sellPrice` valuation.
- `SteamDTPriceProvider` does not read environment variables; env reading stays in the smoke script composition layer.
- `SteamDTPriceProvider` does not create a real client; the smoke script composition layer injects the client.
- The provider smoke flow remains isolated from pipeline / scheduler / alerts.
- No non-official evasion techniques are used.
- No request replay from browser sessions.
- No unofficial reverse-engineered endpoints.
- No automated purchase.
- No automated login.

## Phase 10B SteamDT Real-smoke Readiness Checklist

This checklist is for manual read-only smoke tests only. It is not a production trading workflow. It is not an automated purchase workflow. It does not bypass platform controls.

Before running any real smoke request manually:

1. Confirm working tree is clean.
2. Confirm no real API key is committed.
3. Confirm `STEAMDT_DRY_RUN=false` is intentionally set.
4. Confirm only official endpoint is used.
5. Confirm request is read-only.
6. Confirm market hash names are manually selected.
7. Confirm batch size is `<= 10`.
8. Confirm output redacts API key and Authorization header.
9. Confirm smoke script is not called by scheduler / pipeline.
10. Confirm no non-official evasion techniques are used.

Additional boundaries:
- No cookie scraping.
- No browser automation.
- No captcha bypass.
- No risk-control bypass.
- No hidden endpoints.
- No request replay from browser sessions.
- No unofficial reverse-engineered endpoints.
- No automated purchase.
- No automated login.

## Phase 12A Typed Errors and Retry Classification

Real manual read-only smoke observations completed before this phase:
- Single price endpoint passed: `GET /open/cs2/v1/price/single`.
- Avg price endpoint passed: `GET /open/cs2/v1/price/avg`.
- Batch price endpoint passed: `POST /open/cs2/v1/price/batch`.
- Provider single flow passed with injected SteamDT HTTP client.
- Provider batch smoke observed SteamDT `errorCode=4005` after repeated batch calls within roughly one minute; this is treated as an API rate-limit condition.
- No raw payload or API key is stored in this document.

Typed error classification:
- `SteamDTTransportError`: connect/read timeout, connection reset, and other transport failures. These may be retried within `max_retries`.
- `SteamDTHttpStatusError`: non-rate-limit HTTP status failures. HTTP 5xx may be retried; HTTP 400 / 401 / 403 / 404 are not automatically retried.
- `SteamDTApiError`: SteamDT wrapper `success=false` business/API failures other than known rate-limit code `4005`. These are not automatically retried.
- `SteamDTRateLimitError`: HTTP 429 or SteamDT wrapper `errorCode=4005`. These are not automatically retried.
- `SteamDTResponseParseError`: invalid JSON, unexpected wrapper/data shape, invalid Decimal/int conversion, or parser schema mismatch. These are not automatically retried.

Retry boundaries:
- Retry only transport failures and HTTP 5xx.
- Do not retry HTTP 400 / 401 / 403 / 404 / 429.
- Do not retry SteamDT wrapper `errorCode=4005`.
- Do not retry other `success=false` wrapper errors.
- Do not retry parser/schema/Decimal conversion failures.
- Error strings must not include API keys, Authorization headers, or full raw payloads.

## Phase 12B Endpoint-specific In-memory Rate Limiter

Endpoint policy table:

| Endpoint | Path | Current policy | Source |
| --- | --- | --- | --- |
| `price_single` | `/open/cs2/v1/price/single` | 60 requests / minute | Confirmed official quota |
| `price_batch` | `/open/cs2/v1/price/batch` | 1 request / minute + 5-second project safety buffer | Confirmed official quota plus internal buffer |
| `price_avg` | `/open/cs2/v1/price/avg` | 10 requests / minute | Internal safety cap only |
| `base` | `/open/cs2/v1/base` | 1 request / day | Confirmed official quota |
| `kline` | `/open/cs2/item/v1/kline` | 120 requests / minute | Confirmed official quota |
| `wear` | `/open/cs2/v1/wear` | 36000 requests / hour | Confirmed official quota |

Notes:
- `price_avg` 10/min is an internal safety cap, not a confirmed official SteamDT limit.
- The batch 5-second safety buffer is a project safety margin, not part of the official quota.
- Policies may exist for endpoints whose HTTP methods remain unimplemented; that does not enable new requests.
- The limiter uses monotonic-clock sliding windows and records timestamps per endpoint bucket.
- Fail-fast behavior is intentional: local exhaustion raises `SteamDTRateLimitError` instead of silently sleeping for 60 seconds or longer.
- HTTP 429 and wrapper `errorCode=4005` record a server cooldown for only the affected endpoint.
- If HTTP `Retry-After` is present and numeric, cooldown lasts at least that many seconds; otherwise the endpoint policy safety window is used.
- Transport failures and HTTP 5xx may be retried, but every retry attempt must acquire endpoint budget first.
- A `price_batch` retry after a 5xx can therefore be blocked by the local 1/min budget before sending another HTTP request; this is expected safe behavior.
- Current limiter state is process-local only. Different CLI processes do not share request history or server cooldowns.
- Phase 12C is reserved for Redis/shared limiter behavior across processes.
- No raw payload, API key, Authorization header, or secret is stored by the limiter.
- No Redis connection, price cache, pipeline integration, scheduler integration, automatic purchase, automatic login, browser automation, cookie scraping, captcha bypass, risk-control bypass, hidden endpoint, or non-official evasion technique is added in this phase.

## Phase 12C1 Redis Shared Rate Limiter Core

Why process-local limiting is not enough:
- The in-memory limiter protects only one Python process.
- Separate CLI, API, and scheduler processes can otherwise have independent request histories.
- A Redis-backed limiter lets explicitly wired callers share endpoint budget state across processes.

Redis key schema:
- Each endpoint uses two keys:
  - `{steamdt-rate-limit-v1:<endpoint>}:requests`
  - `{steamdt-rate-limit-v1:<endpoint>}:blocked`
- The `{...}` hash tag keeps one endpoint's request sorted set and blocked marker in the same Redis Cluster slot.
- Different endpoints use different hash tags, so endpoint buckets stay independent.
- Keys use stable endpoint identifiers, not full URLs.
- Keys must not contain SteamDT API keys, Redis passwords, Authorization headers, market hash names, or other user-sensitive data.

Acquire behavior:
- Acquire uses a Redis Lua script to make the read/check/write sequence atomic.
- The script uses Redis server `TIME`, not local monotonic time, so separate processes compare a shared clock.
- The request history is a sorted set scored by Redis server milliseconds.
- Window pruning, count check, and request insertion happen inside one script invocation.
- Python supplies a non-sensitive UUID request member so same-millisecond concurrent requests do not overwrite each other.
- On allow, the script sets a requests-key TTL covering the effective rate-limit window plus Redis cleanup grace.
- Redis cleanup TTL grace only cleans idle Redis state; it does not change the request budget window.

Server cooldown behavior:
- HTTP 429 and wrapper `errorCode=4005` can call `record_server_limit()` on the same limiter protocol.
- Redis server cooldown uses a separate blocked-until key per endpoint.
- The Lua script computes requested blocked-until from Redis server `TIME`.
- Existing and new blocked-until values use max semantics, so shorter new blocks cannot reduce longer existing blocks.
- `retry_after_seconds=None` uses the endpoint policy effective window.
- Negative retry-after values are normalized safely and never create a past cooldown.
- Blocked keys also receive TTL; no background cleanup job is required.

Backend behavior:
- Redis connection, timeout, response, or malformed Lua response errors are converted to `SteamDTRateLimitBackendError`.
- Backend failure is not reported as SteamDT quota exhaustion.
- Backend failure fails closed before a SteamDT HTTP request is sent.
- There is no silent fallback to in-memory limiting.
- Redis limiter code does not read env, call `Redis.from_url()`, save a Redis URL, or own connection shutdown.
- Composition/factory wiring is intentionally left to the next phase.
- `SteamDTHttpClient` still defaults to the in-memory limiter unless a Redis limiter is explicitly injected.

Safety boundaries:
- This phase does not enable Redis limiter by default.
- This phase does not connect pipeline / scheduler / smoke scripts to Redis limiter.
- This phase does not add price cache, refresh service, or Redis connection factory.
- No raw payload is stored in Redis.
- No secrets are included in Redis keys or Lua scripts.
- No non-official evasion techniques, hidden endpoints, automatic purchase, automatic login, cookie scraping, browser automation, captcha bypass, or risk-control bypass are added.

## Phase 12C2 Redis Limiter Integration Harness

Purpose:
- Fake Redis backend unit tests validate control flow, but a real Redis harness is still needed to confirm redis-py 5.x, Lua return parsing, server `TIME`, sorted-set behavior, TTL commands, and cleanup semantics against a real Redis server.
- The harness validates only the `RedisSteamDTRateLimiter` Redis/Lua contract.
- It does not validate SteamDT endpoints and does not call SteamDT.

Opt-in boundary:
- The smoke script and integration pytest are disabled by default.
- They only connect to Redis when `STEAMDT_RUN_REDIS_INTEGRATION_TESTS=true` is explicitly set.
- The test URL comes from `STEAMDT_TEST_REDIS_URL`, not production `REDIS_URL`; the example uses `redis://localhost:6379/15`.
- The test namespace comes from `STEAMDT_TEST_REDIS_NAMESPACE` and defaults to `steamdt-rate-limit-integration-v1`, separate from the production limiter namespace.
- The harness appends a UUID suffix to the namespace for each run to avoid concurrent-run collisions.

Real Redis checks:
- Redis `PING` verifies connectivity before limiter scenarios.
- Two limiter instances sharing one Redis namespace verify shared `price_batch` quota.
- Endpoint independence verifies `price_batch`, `price_single`, and `price_avg` remain separate buckets.
- Short test-only policies verify window recovery without waiting for official 60-second windows; these policies are not official SteamDT limits.
- Server cooldown checks use `record_server_limit()` and Redis server `TIME`.
- Longer-block-wins behavior confirms the Lua max semantics for blocked-until values.
- Requests and blocked keys are checked with positive millisecond TTL values.
- Same-millisecond or near-simultaneous successful acquires confirm UUID request members do not collide.

Cleanup and safety:
- Cleanup uses paged `SCAN` with a narrow pattern for the exact test namespace.
- Cleanup deletes only keys under the current test namespace.
- The harness does not execute `KEYS *`, `FLUSHDB`, or `FLUSHALL`.
- A final scan confirms the current namespace has no residual keys.
- Cleanup failures are reported with redacted messages and can make the smoke fail, but cleanup is still attempted after primary validation failures.
- Redis URL passwords, query secrets, Authorization headers, SteamDT API keys, raw Redis responses, and Lua script bodies are not printed.
- Redis unreachable, timeout, response, Lua, malformed-response, and `SteamDTRateLimitBackendError` failures fail closed and do not fall back to in-memory limiting.
- Composition wiring for pipeline / scheduler remains a later phase.
- No raw payload or secret is saved.
- No non-official evasion techniques, request replay from browser sessions, hidden endpoints, automatic purchase, automatic login, cookie scraping, browser automation, captcha bypass, or risk-control bypass are added.

## Phase 12C3 Explicit Rate Limiter Composition / Factory Wiring

Purpose:
- Factory-created SteamDT runtimes can now explicitly choose `inmemory` or `redis` as the rate-limiter backend.
- Default remains `inmemory`, preserving direct `SteamDTHttpClient(...)` construction and avoiding Redis access unless Redis is explicitly selected.
- This phase only adds configuration, composition, resource ownership, and client construction behavior.

Configuration:
- `STEAMDT_RATE_LIMIT_BACKEND` accepts only `inmemory` or `redis`.
- Unset backend defaults to `inmemory`.
- `STEAMDT_RATE_LIMIT_REDIS_NAMESPACE` defaults to `steamdt-rate-limit-v1` and is only for the SteamDT limiter.
- Redis composition reuses the formal `REDIS_URL` setting rather than `STEAMDT_TEST_REDIS_URL`.
- The Phase 12C2 variables `STEAMDT_RUN_REDIS_INTEGRATION_TESTS` and `STEAMDT_TEST_REDIS_URL` remain test-only and are not used by the formal composition factory.

Factory/runtime behavior:
- The composition layer reads an already-parsed settings object and builds `SteamDTClientConfig` using the existing endpoint-specific policies.
- `backend=inmemory` creates `InMemorySteamDTRateLimiter` and does not create a Redis client.
- `backend=redis` creates or receives an async Redis client, creates `RedisSteamDTRateLimiter`, and injects it into `SteamDTHttpClient`.
- `SteamDTHttpClient`, `InMemorySteamDTRateLimiter`, and `RedisSteamDTRateLimiter` still do not read environment variables.
- Redis client creation does not happen at import time, does not use a global singleton, and does not ping automatically.
- The runtime exposes `aclose()` so owned Redis clients can be closed explicitly and idempotently.
- Factory-created Redis clients are owned by the runtime; externally injected Redis clients are not closed unless ownership is explicitly requested.

Errors and safety:
- Unsupported backend, missing Redis URL for Redis backend, and empty namespace are composition/configuration errors, not quota errors.
- Redis composition never silently falls back to in-memory limiting.
- Error messages must not include Redis passwords, SteamDT API keys, Authorization headers, or full credential-bearing URLs.
- Runtime Redis/Lua failures still use `SteamDTRateLimitBackendError` and fail closed before SteamDT HTTP transport.
- This phase is not wired into pipeline, scheduler, price cache, refresh service, alerts, FastAPI startup, or application lifecycle.
- It does not call SteamDT and does not change endpoint paths, parser behavior, selector behavior, retry behavior, or endpoint policy values.
- `price_avg` remains an internal safety cap, not a documented official SteamDT quota.

## Phase 12D1 Price Cache Domain Model and In-Memory Core

Scope and placement:
- This phase adds only a typed async cache protocol, immutable cache models, and a concurrency-safe in-memory implementation.
- The payload is the normalized multi-platform price-candidate snapshot before selector policy is applied.
- The cache is not connected to `SteamDTPriceProvider`, `ValuationService`, pipeline, scheduler, FastAPI startup, alerts, or application lifecycle.
- No Redis price cache, refresh planner, refresh worker, batch refresh, cache warming, or background task is implemented.
- No production TTL environment variables are added; callers construct an explicit `PriceCachePolicy`.

Identity and payload:
- `market_hash_name` remains the canonical item identifier used by existing provider and valuation contracts.
- A stable cache key also carries game, normalized currency contract, source/provider namespace, snapshot type, and schema version.
- Preferred platform, liquidity thresholds, fallback behavior, and avg-sanity configuration are intentionally absent from the key because cached candidates precede selection.
- Candidate records use immutable tuples and frozen models and omit raw HTTP responses and runtime objects.
- Schema version 1, deterministic JSON key encoding, UTC ISO-8601 timestamps, and Decimal-as-string dumps establish a future Redis serialization boundary without implementing a Redis serializer.

Freshness state machine:
- `fresh_until = observed_at + fresh_ttl`.
- `stale_until = fresh_until + stale_ttl`.
- `expires_at = stale_until + stale_grace_ttl`.
- `FRESH` means `now < fresh_until`.
- `STALE` means `fresh_until <= now < stale_until`.
- `STALE_GRACE` means `stale_until <= now < expires_at`.
- `EXPIRED` means `now >= expires_at`.
- Reads default to `FRESH_ONLY`; stale requires `ALLOW_STALE`, and stale-grace requires explicit `ALLOW_STALE_GRACE`.
- Stale and stale-grace lookups recommend refresh but never start refresh work.

Time and ordering:
- Freshness is calculated from `observed_at`, not `stored_at`, so rewriting old data cannot reset its age.
- Both timestamps must be timezone-aware and are normalized to UTC; the in-memory cache treats its injected UTC clock as the authoritative actual storage time.
- `put()` rejects an observation later than that authoritative clock and replaces the stored snapshot's caller-declared `stored_at` with the actual put time, preventing a future declared storage time from legitimizing a future observation.
- Newer `observed_at` replaces the current entry, older observations are ignored, and equal observations deterministically retain the existing entry; caller-declared `stored_at` never affects ordering.
- Expired entries are never returned and can be removed on lookup or by explicit purge.

Safety boundaries:
- The in-memory cache has instance-local state, one `asyncio.Lock`, and an injectable UTC clock; tests use no real waits.
- This phase does not read environment variables, create Redis or HTTP clients, call SteamDT, or change any endpoint/parser/selector/retry behavior.
- `price_avg=10/min` remains an internal project safety cap and is not a confirmed official SteamDT quota.

## Phase 12D2A Redis Price Cache Codec and Atomic Core

Scope and ownership:
- This phase adds only a strict Redis record codec and an isolated `RedisPriceCache` implementation of the Phase 12D1 protocol.
- The async Redis client is explicitly injected and externally owned. The cache does not read environment variables, call `Redis.from_url()`, ping, close the client, create a singleton, or create a background task.
- No provider, selector, valuation, pipeline, scheduler, FastAPI, refresh, warming, configuration, or application-lifecycle integration is added.

Keys and record codec:
- The default namespace is `steamdt-price-cache-v1`; entry keys use `{steamdt-price-cache-v1:<stable-digest>}:snapshot` and never include the full market hash name or credentials.
- The Redis Hash record is codec-versioned and keeps canonical key identity, split UTC timestamps, exact integer-microsecond TTLs and boundaries, and deterministic candidate JSON in separate fields.
- Candidate JSON uses sorted keys and fixed separators. Decimal prices remain strings, datetimes never pass through float, and provider candidate order and duplicates are preserved.
- Decoding validates exact fields, current schema versions, canonical key/digest agreement, UTF-8/JSON structure, timestamps, durations, boundaries, finite nonnegative Decimal values, exact nonnegative counts, and candidate types.
- A malformed or mismatched stored record raises `PriceCacheCodecError`; corruption is not converted into a cache miss and is not automatically deleted.

Redis time and atomic operations:
- Put/get/purge use one-key Lua scripts and Redis server `TIME` as their cross-process clock authority.
- Put rejects observations later than Redis time and compares observed seconds before observed microseconds; `stored_at`, arrival order, and task completion order do not affect ordering.
- New and newer observations write atomically and stamp `stored_at` from the same Redis `TIME`. Equal and older observations retain the existing payload, storage time, and physical expiry without mutation.
- Lua stores opaque deterministic JSON without `cjson` decoding or re-encoding.
- Logical expiration remains `observed_at + fresh_ttl + stale_ttl + stale_grace_ttl`. Physical cleanup uses absolute `PEXPIREAT`, rounded upward to milliseconds and extended by a 5-second cleanup grace; it never restarts from `stored_at`.
- Get reads the hash, computes state from split microsecond boundaries, and deletes an expired entry in the same Lua call. Policy-blocked and expired lookups never return a snapshot.
- During physical cleanup grace, the first expired read can return `EXPIRED` and atomically delete the record. If Redis removes it naturally first, a later read is indistinguishable from a normal missing key.

Administration and errors:
- Exact-key delete returns the existing protocol boolean.
- `clear()` performs paginated namespace-scoped `SCAN`, locally validates each opaque digest key, and deletes only exact matches. It never uses `KEYS`, `FLUSHDB`, or `FLUSHALL`.
- `purge_expired()` scans only the namespace and runs a Redis-time one-key atomic purge script per exact key; it counts only entries actually deleted by that invocation.
- Namespace SCAN is bounded and scoped but is not linearizable with concurrent writers and is not claimed to provide a Redis-Cluster-global scan.
- Redis availability and malformed response contracts raise `PriceCacheBackendError`, preserve the cause, and fail closed without falling back to in-memory cache.

Validation boundary:
- Phase 12D2A unit tests use fake/scripted Redis clients only and do not connect to Redis or SteamDT.
- Static tests assert Lua command and argument contracts. Phase 12D2B adds separate, explicitly opted-in real Redis validation without changing this core's ownership or wiring boundaries.
- No refresh planner, worker, batch refresh, cache warming, retry loop, production TTL environment configuration, or business wiring exists in this phase.
- `price_avg=10/min` remains an internal project safety cap and is not a confirmed official SteamDT quota.

## Phase 12D2B Real Redis Price Cache Integration

Opt-in and isolation:
- `STEAMDT_RUN_REDIS_PRICE_CACHE_INTEGRATION_TESTS=false` is the default. Neither the pytest module nor either smoke entrypoint creates a Redis client unless the value is explicitly `true`.
- The harness reads `STEAMDT_TEST_REDIS_URL` rather than formal `REDIS_URL`, and reads `STEAMDT_TEST_REDIS_PRICE_CACHE_NAMESPACE` rather than any production namespace. It never reads a SteamDT API key or calls SteamDT.
- The namespace base must start with `steamdt-price-cache-integration-v1`; every run appends a generated lowercase UUID hex suffix. Empty values, surrounding whitespace, controls, glob characters, braces, production namespace, limiter namespace, and missing/invalid UUID suffixes are rejected before connection.
- Cleanup uses paginated SCAN with `{<exact-uuid-namespace>:*}:snapshot`, validates every returned key against the exact namespace and 64-hex digest format in Python, and applies DEL only to verified keys. It is repeatable and runs in `finally`; no `KEYS`, `FLUSHDB`, or `FLUSHALL` is used.

Ownership and safe operation:
- The smoke harness and pytest fixture create two independent redis-py async clients and close both with `aclose()` in `finally`. `RedisPriceCache` remains externally owned and never closes either client.
- Cleanup and close attempts still run after scenario failure. A cleanup error is reported but does not replace the primary scenario exception.
- Full Redis URLs, passwords, query credentials, authorization headers, payload JSON, and key lists are not printed. The smoke output reports only fixed scenario labels and `SteamDT requests sent: 0`.
- Direct and module execution are both supported. With the gate disabled they print a skip message and exit 0 before Redis namespace/client work.

Real Redis contract coverage:
- The harness validates PING, Redis version discovery, Redis `TIME`, bytes tags in Python list Lua replies, flat `HGETALL` field/value data, Redis 7 Lua `TYPE(...)["ok"]`, exact integer delete results, absolute `PEXPIREAT`, and redis-py integer SCAN cursors.
- Basic round-trip preserves exact Decimal strings, aware UTC microseconds, provider order, and duplicate candidates. Redis TIME stamps authoritative `stored_at` between real pre/post TIME reads and ignores caller-declared storage time.
- Two independent clients verify shared namespace visibility, deterministic keys, newer replacement, older/equal no-op preservation, one-microsecond ordering within one Unix second, and concurrent newer/older and equal-observation races.
- Real logical state checks cover fresh, stale, stale-grace, explicit read policies, policy-blocked snapshot isolation, and an expired read that reports EXPIRED once and deletes in the same Lua operation.
- `PEXPIRETIME` is checked against `observed_at + all logical TTLs + five-second cleanup grace`, with microseconds rounded upward. Equal and older writes must not change stored metadata or physical expiry.
- Wrong Redis types and minimally corrupt hashes fail closed for get, put, and purge and remain present until explicit namespace clear. Namespace isolation, real SCAN pagination, and purge counts are also covered.

Boundary:
- This phase validates a local/test Redis server only. It does not deploy the cache or wire the Phase 12D3A composition factory into provider, selector, valuation, pipeline, scheduler, FastAPI, refresh, warming, or background work.
- Namespace SCAN remains non-linearizable with concurrent writers and is not claimed to be Redis-Cluster-global.
- `price_avg=10/min` remains an internal project safety cap and is not a confirmed official SteamDT quota.

## Phase 12D3A Price Cache Factory / Composition

Configuration and selection:
- `STEAMDT_PRICE_CACHE_BACKEND` accepts only `inmemory` or `redis`; the default is `inmemory`, and Redis composition never silently falls back to memory.
- Redis composition reuses formal `REDIS_URL` and `STEAMDT_PRICE_CACHE_REDIS_NAMESPACE` (default `steamdt-price-cache-v1`). It never reads D2B integration-test variables and introduces no second production URL or production TTL settings.
- The factory reuses the cache core's namespace normalization, including its exact `[A-Za-z0-9._:-]+` allowlist. Unsupported backends, missing or malformed required URLs, invalid namespaces, ownership without an injected client, and conflicting or backend-irrelevant arguments fail explicitly.

Construction and ownership:
- The default path constructs only `InMemoryPriceCache` and does not create a Redis client. Redis composition constructs `RedisPriceCache` without PING, EVAL, SCAN, TIME, DELETE, or another Redis command; `Redis.from_url()` remains lazy and does not prove connectivity.
- `RedisPriceCache` continues to be an injected-client core and never owns or closes Redis. A factory-created client is owned by `SteamDTPriceCacheRuntime`; an external client defaults to non-owned and can transfer ownership explicitly.
- Runtime close is asynchronous and at-most-once, including after close failure or concurrent close calls. Only owned clients are closed; modern `aclose()` and compatible `close()` clients are supported.
- If construction fails after an owned client is acquired, cleanup is attempted once. The primary construction exception remains inspectable; if cleanup also fails, a dedicated composition error exposes both exceptions without placing arbitrary credential-bearing messages in public error text or traceback chaining.

Compatibility and boundaries:
- The rate-limiter factory and price-cache factory remain separate and the limiter ownership contract is unchanged. A future application runtime may inject the same external redis-py client into both with ownership false and become the sole closer; both runtimes must not independently own that shared client.
- Phase 12D3A tests use fake Redis clients and do not connect to Redis or SteamDT. Direct `InMemoryPriceCache` and `RedisPriceCache` construction remains compatible.
- The factory is not imported by `PriceProvider`, selector, `ValuationService`, pipeline, scheduler, FastAPI, alerts, or refresh/warming workers. This phase does not claim production deployment and does not modify Lua, codec, cache state, or read/write semantics.

## Phase 12D3B SteamDT Snapshot Adapter and Cache-Backed Quote Resolver

Adapter contract:
- `SteamDTPlatformPrice` maps field-for-field to `NormalizedPriceCandidate`: platform, platform item ID, sell/bid Decimal values, sell/bid counts, and opaque source update time. `update_time` is renamed to `source_update_time`; its unit remains unconfirmed and the adapter does not parse or infer it.
- Prices must remain finite nonnegative `Decimal` values, counts remain exact nonnegative integers, and source update time remains `int | str | None` with ambiguous values such as `bool` rejected explicitly.
- Multi-candidate conversion preserves original order and duplicates. Raw HTTP mappings are deliberately excluded from cache records; reconstruction for the selector sets `raw=None` and does not claim payload round-trip compatibility.
- Snapshot construction accepts an existing D1 `PriceCacheKey`, ordered normalized candidates, explicit aware observation/storage timestamps, and `PriceCachePolicy`. It does not read a clock or write a backend. Adapter invariant failures use a dedicated non-sensitive error rather than backend or codec errors.

Resolver and read policy:
- `SteamDTCachedPriceResolver` depends on a narrow structural cache-reader contract, performs exactly one policy-aware `get()`, and never directly calls put, delete, clear, or purge operations. Existing cache backends may atomically remove an expired record as part of their established `get()` semantics.
- A permitted hit is converted back to selector input and evaluated once with the caller's current `SteamDTPriceSelectionConfig`, optional already-known `avg_price_cny`, and no original payload. The resolver never calls SteamDT or obtains avg data itself.
- Selection strategy, liquidity thresholds, bidding/spread requirements, avg sanity inputs, fallback behavior, and future preferred-platform policy remain absent from `PriceCacheKey`. The same pre-selection snapshot can therefore produce a different result under a later config without a new cache entry.
- The existing selector currently has no preferred-platform setting. D3B validates policy-independent reuse with the supported strategy and liquidity controls instead of adding or simulating that feature.
- Allowed stale and stale-grace hits preserve state, age, and `needs_refresh=true` while remaining selectable. `FRESH_ONLY`, `ALLOW_STALE`, and `ALLOW_STALE_GRACE` retain the exact D1 policy matrix; the resolver does not act on refresh advice.

Results, errors, and boundaries:
- Resolution statuses distinguish `SELECTED`, ordinary `MISS`, `POLICY_BLOCKED`, `EXPIRED`, and selector `SELECTION_FAILURE`. Miss, blocked, expired, and no acceptable candidate are normal typed results and never trigger a live fallback.
- The thin result retains the complete `PriceCacheLookup` plus the existing `SteamDTPriceSelectionResult` when selection ran, and exposes the existing `SteamDTPriceQuote` without duplicating provider-specific `PriceQuote` or batch `PriceLookupResult` behavior.
- `PriceCacheBackendError` and `PriceCacheCodecError` propagate unchanged and fail closed. Adapter invariant errors and unexpected selector errors remain distinct; none is converted to a miss or selection failure.
- D3B directly creates no Redis or HTTP client, reads no environment variables, creates no task, invokes no cache write/administration method, refreshes nothing, and owns no runtime lifecycle. The default selector is local and network-free; externally injected cache readers/selectors retain responsibility for their own side effects. It is not imported by provider, valuation, pipeline, scheduler, FastAPI, or alerts.
- Phase 12D4A adds only the isolated single-item write core below. D3B does not claim production deployment and changes no provider protocol, cache factory, Redis codec/Lua/harness, selector behavior, pipeline, or scheduler behavior.

## Phase 12D4A Single-Item Refresh / Write Service Core

Source contract:
- `SteamDTPriceSnapshotSource` is a narrow async port that receives the canonical `PriceCacheKey.market_hash_name` and returns one `SteamDTFetchedPriceSnapshot`. D4A defines no concrete HTTP implementation and does not modify `SteamDTClient`, `SteamDTHttpClient`, parsers, or `SteamDTPriceProvider`.
- Existing public price methods return already-selected quotes and do not expose both the complete selector-before platform candidate sequence and an explicit observation timestamp, so they do not satisfy this source contract.
- A fetched snapshot contains canonical item/source identity, an aware source-owned `observed_at`, and an ordered tuple of defensive `SteamDTPlatformPrice` clones with `raw=None`. Input order, duplicate candidates, Decimal values, counts, platform IDs, and opaque `update_time` values are retained without preserving mutable HTTP metadata.
- Source `observed_at` defines the snapshot observation. Candidate `updateTime` remains an unconfirmed per-record field and is never parsed, combined, or promoted to cache freshness time.

Refresh/write and time semantics:
- `SteamDTPriceRefreshService.refresh_one()` builds the same version-1 `cs2`/`CNY`/`steamdt`/`platform_prices` key used by D1 and D3B, validates exact returned item/source identity, converts all candidates through the D3B adapter, and submits one nonempty snapshot through a write-only cache port.
- Empty candidate observations return normal `NO_CANDIDATES`, retain key and observation metadata, and do not read the service clock, build an empty snapshot, or call `cache.put()`.
- The service clock is read once only for provisional incoming `stored_at`; it never supplies or changes `observed_at`. If that local clock lags the source observation, the observation is used as the minimum model-valid placeholder so local skew cannot preempt the backend check. The cache backend remains authoritative: in-memory writes stamp their cache clock and Redis writes stamp server `TIME`; either can still reject an observation later than its own authority.
- Freshness and write ordering remain based only on `observed_at`. Candidate source timestamps, candidate payload, policy changes, provisional storage time, arrival order, and task completion order do not make an observation newer.

Results, errors, ordering, and boundaries:
- A nonempty refresh returns `CACHE_PUT_COMPLETED` plus the exact cache result: `CREATED`, `REPLACED`, `IGNORED_OLDER`, or `UNCHANGED_EQUAL`. The status only means `put()` returned normally; ignored/equal outcomes do not claim that incoming data or policy was stored.
- Concurrent calls are neither locked nor coalesced. Each source fetch and put runs independently, while cache atomic ordering preserves the newest observation and equal observations retain the first writer. D4A implements no single-flight behavior.
- Typed source transport/status/API/rate-limit/parser errors, adapter invariant errors, backend errors, codec corruption, and backend future-observation errors propagate without retry, fallback, repair, or false success. Item/source/return-contract mismatches use one fixed non-sensitive refresh validation error.
- D4A runs no selector, constructs no quote, reads/administers no cache entry, creates no Redis or HTTP client, reads no env/config, and starts no task. It is not imported by provider, resolver, valuation, pipeline, scheduler, FastAPI, or alerts.
- There is no concrete SteamDT source, real Redis/SteamDT validation, batch refresh, planner, worker, warming, retry, background refresh, scheduler integration, live fallback, or production deployment. Phase 12D4B adds only the isolated concrete source and manual smoke below.

## Phase 12D4B Concrete Read-Only Snapshot Source and Manual Smoke

Client and source boundary:
- `SteamDTHttpClient.get_price_single_candidates()` now exposes the complete ordered result of the confirmed official `GET /open/cs2/v1/price/single` path before selector policy is applied. A shared private request/parser helper keeps authentication, endpoint-specific limiter acquisition, wrapper-4005 cooldown recording, typed errors, and normal transport/5xx retry ownership in the existing client.
- Existing `get_price_single_with_selection()` reuses that same helper and still passes the exact original response payload into `select_steamdt_price_quote()`. `get_price_single()`, `SteamDTClient`, mock/dry-run clients, and provider-facing behavior remain selected-quote compatible; no request is duplicated and no undocumented endpoint is added.
- `SteamDTSinglePriceSnapshotSource` depends on a narrow candidate-client protocol, borrows rather than closes the client, makes one candidates call, validates the collection, then constructs the D4A fetched snapshot with fixed source `steamdt`. It never selects, reads/writes cache, requests avg price, retries independently, or reads environment/config.

Observation and data semantics:
- Source `observed_at` is the injected aware UTC clock reading taken once after successful HTTP completion and response parsing. It is the local client observation-completion time, not provider publication time.
- Candidate `updateTime` remains opaque `int | str | None` metadata because its unit and semantics are unconfirmed. It is preserved per candidate but never used to infer `observed_at`, ordering, freshness, or TTL.
- The D4A fetched model remains the raw-data boundary: candidate order, duplicates, exact Decimal values, counts, platform IDs, and opaque update times survive, while mutable record `raw` mappings and the full HTTP payload do not enter the fetched/cached snapshot.

Manual smoke safety and flow:
- `scripts/steamdt_price_snapshot_smoke.py` is disabled by default through dedicated `STEAMDT_RUN_PRICE_SNAPSHOT_SMOKE=false`. Only explicit `true` enables this harness; the gate is checked before API-key/base-URL reads or client construction. The supplied D4B command therefore needs no additional `STEAMDT_DRY_RUN=false`; older SteamDT smoke scripts retain their existing gate behavior.
- After opt-in, the smoke requires `STEAMDT_API_KEY` and one `STEAMDT_SMOKE_MARKET_HASH_NAME`. It directly constructs an owned SteamDT HTTP client with the existing default in-memory endpoint limiter, a concrete source, D4A refresh service, one `InMemoryPriceCache`, and D3B cached resolver.
- This quota-sensitive harness sets `max_retries=0` and disables redirects without changing normal client defaults. An HTTPX request hook counts actual outbound attempts, the flow invokes one `refresh_one()` and one cache-only `resolve()`, and output reports `SteamDT requests sent: 1` only when exactly one attempt occurred. A failure is not automatically retried or repeated through the alternate entrypoint.
- Output is restricted to item, candidate count, UTC observation time, exact cache write outcome, cache state, selected platform/price, `needs_refresh`, typed statuses, fixed/redacted error type, and request count. It never prints API keys, Authorization headers, raw candidates, full responses, quote raw data, config/runtime reprs, or traceback payloads. Owned HTTP resources close on success and failure.
- Empty candidate responses remain normal D4A `NO_CANDIDATES`; no empty snapshot is written and cached resolution reports a miss. Typed SteamDT business/transport/parser failures remain distinct internally and are not converted into fallback data.
- Automated D4B tests use fake clients or local HTTPX transports only. The smoke imports neither cache nor limiter Redis composition, connects no Redis, and changes no provider, pipeline, scheduler, FastAPI, alerts, background work, batch refresh, market action, or production deployment wiring.

## Phase 13A Step 2L-PIVOT-R1 Aggregate Market Data and CNY Assumption

Source priority and price interpretation:
- SteamDT is now the current MVP primary source for item/platform aggregate market data and valuation input. Completed SteamApis modules remain unchanged as optional future listing-level infrastructure and are not a required current runtime source.
- Official SteamDT price documentation names `sellPrice` and `biddingPrice` but does not currently make an explicit CNY/RMB guarantee. The user has expressly approved a project interpretation that both fields are treated as CNY/RMB. Existing `SteamDTPlatformPrice.sell_price_cny`, `bidding_price_cny`, selector, and `PriceQuote.price_cny` contracts therefore remain unchanged; this assumption must not be cited as an official provider guarantee and no exchange-rate conversion is added.

Aggregate service contract:
- `get_steamdt_market_data()` borrows a narrow existing single-candidate client, validates one canonical requested `market_hash_name`, calls `get_price_single_candidates()` exactly once, and returns an immutable `SteamDTMarketDataResult` containing defensive `SteamDTPlatformPrice` clones with `raw=None`.
- Provider order, duplicate platform records, exact platform spelling/case, optional platform-local item IDs, CNY-interpreted Decimal values, optional counts, and opaque `update_time` values are preserved. The service does not sort, deduplicate, select, cache, value recipes, or synthesize listing identities or links.
- Documented price records are item/platform aggregates. They do not establish individual buyable listing IDs, purchase links, per-listing float/inspect data, or seller/account provenance. `platformItemId` remains only an opaque provider platform-local identity.

Explicit one-request probe:
- `scripts/run_live_steamdt_market_smoke.py` reuses `STEAMDT_RUN_PRICE_SNAPSHOT_SMOKE`, `STEAMDT_API_KEY`, and `STEAMDT_SMOKE_MARKET_HASH_NAME`. Exact normalized `true` is required before key, item, base URL, runtime, or network access.
- One enabled process creates one owned HTTP client and one existing SteamDT client with `max_retries=0`, invokes the aggregate service once, and attempts exactly one official `GET /open/cs2/v1/price/single` request. It never calls batch, base, avg, kline, or wear, never requires Redis, and has no retry, fallback, second item, scheduler, or background task.
- A parsed empty platform collection is a fixed failure without retry. Success output preserves safely escaped exact platform strings and reports only platform-ID/update-time presence plus aggregate CNY-interpreted price/count values. It omits the requested item text, item IDs, update-time values, key, Authorization/header data, raw response/mapping, and nested exception text.
- Offline tests also exercise the existing `SteamDTHttpClient → SteamDTPriceProvider → PriceQuote.price_cny` chain as the explicit project assumption. This phase does not call Step 2F live recipe valuation, EV, or risk; full valuation runtime wiring remains Step 2M. It adds no automatic buying, login, Cookie handling, browser automation, marketplace write, or production deployment.

## Phase 13A Step 2M-A1 BUFF-only Output Price Policy

Project policy and selection boundary:
- The exact, case-sensitive provider platform literal `BUFF` is the only eligible record for this project policy. The selector does not trim, case-fold, normalize, translate, alias, or match values such as `buff`, `BUFF163`, or `网易BUFF`.
- `select_buff_output_price()` is a synchronous, offline policy over one existing `SteamDTMarketDataResult`. It requires exactly one exact BUFF record and a finite, positive `sell_price_cny`; absent and duplicate exact records fail closed with stable reasons and no cross-platform fallback.
- The returned immutable `SteamDTBuffOutputPrice` retains the requested market identity, exact BUFF platform, gross sell price, optional sell count, opaque platform-local item ID, and opaque update time. It retains no raw provider mapping or source quote.

Price meaning and exclusions:
- The gross sell value continues to use the user-approved project CNY/RMB interpretation; this is not represented as an explicit current provider currency guarantee. No fee, exchange-rate conversion, net proceeds, EV, ROI, profit, or risk calculation occurs here.
- `bidding_price_cny` and `bidding_count` are not read or used. Aggregate bidding data may represent a special-condition order whose requirements are absent from the response, so a bid is never treated as unconditional output value and never substitutes for a missing or unusable sell price.
- The selected aggregate sell price is not an exact executable listing price, guaranteed realized proceeds, buy order, recent sale, or special-condition order. This policy does not modify the generic SteamDT selector/provider and adds no network, cache, Redis, SteamApis, scheduler, live-smoke, valuation-runtime, or Step 2M-A2 wiring.

## Phase 13A Step 2M-A2 BUFF-only PriceProvider Adapter

Composition and provenance:
- `SteamDTBuffPriceProvider` is a standalone offline adapter that borrows the narrow aggregate client and composes `get_steamdt_market_data()` → `select_buff_output_price()` → the existing `PriceQuote`. It does not duplicate exact BUFF matching, sell-price validation, duplicate handling, or no-BUFF policy.
- Successful quotes preserve the canonical requested identity and exact Decimal gross BUFF sell value, use fixed source `steamdt:buff`, and retain `raw=None`. The source describes SteamDT plus the BUFF aggregate policy; it is not a purchase/listing identity.
- The price remains the project-approved CNY interpretation rather than an explicit current provider currency guarantee. The adapter does not read bidding data or calculate fees, net proceeds, EV, ROI, profit, probability, or risk.

Batch and failure contract:
- Batch input follows the existing SteamDT provider convention: strip names, drop blanks, and stable-deduplicate canonical names by first occurrence. Each canonical unique name is resolved sequentially through the same single-item composition once; no official batch endpoint, task/concurrency, retry, sleep, cache, or fallback is used.
- Ordinary per-item failures create no quote, add one aligned missing name, and emit one fixed redacted error with the canonical unique-name index. A1 policy failures expose only the allowlisted reason value; other exceptions expose neither nested text nor type. Later ordinary items continue, while process-control failures propagate without a partial result.
- Tests inject fakes only. The provider owns no HTTP/runtime client, limiter, environment/key access, Redis, scheduler, or lifecycle resource and is not imported by valuation, recipe, FastAPI, Discord, or production runtime. This step does not imply executable proceeds, automatic purchase, live validation, Step 2M-A3, or production readiness.

## Phase 12D5A Batch Refresh Planner, Deduplication, and Chunking Core

Planning and identity contract:
- `SteamDTRefreshPlanner` is a synchronous pure planner over an `Iterable[str]`. It traverses the caller's iterable exactly once and constructs `PriceCacheKey(market_hash_name=raw_item, source=canonical_source)` directly for every encountered entry; it does not duplicate item normalization or pre-validate with a second pass.
- Full canonical key equality defines duplicate identity. Leading/trailing item and source whitespace is therefore stripped by `PriceCacheKey`, while case and all other key dimensions retain existing semantics. The first canonical occurrence establishes output order and a zero-based `first_seen_input_index`; later equivalent occurrences increment that item's exact positive `occurrence_count` and never enter another chunk.
- `steamdt` is the default source, not a planner-specific allowlist. Any nonempty source accepted and canonicalized by `PriceCacheKey` is valid, including for an empty plan. Non-string or blank item/source values fail closed through a planner validation error that records the field and, for items, the zero-based input index without including the raw value.

Immutable plan and chunk invariants:
- `SteamDTRefreshPlanItem`, `SteamDTRefreshPlanChunk`, `SteamDTRefreshPlan`, and the planner are frozen. Collection inputs are defensively converted to tuples. Plan input count is the sum of occurrence counts, unique count is the item tuple length, and duplicate count is their difference; ordered key/name projections are derived rather than independently supplied.
- Public constructors reject contradictory key, source, count, occurrence, first-seen index, chunk index, chunk start, size, order, or flattened-content combinations. Exact integers are required and `bool` is not accepted as an index, count, or chunk size. All plan/input/chunk indices are zero-based.
- Caller-provided `chunk_size` must be positive. Unique items are partitioned continuously in first-seen order; each non-final chunk has exactly that size, the final chunk has at most that size, and an empty input produces zero counts, no items, and no chunks.
- Input errors return no partial plan and invalid entries are never skipped. Infinite iterables are unsupported and are neither detected nor consumed in background work.

Local-only meaning and boundaries:
- A `SteamDTRefreshPlanChunk` is only an in-process partition of possible future work. It is not a request to the confirmed official `POST /open/cs2/v1/price/batch` endpoint, does not call or enable `SteamDTHttpClient.get_price_batch()`, does not imply D5B will use that endpoint, and does not encode or assert an official request-size or quota limit.
- D5A performs no refresh, source/client call, cache read/write/administration, Redis construction, selection, quote creation, avg-price lookup, endpoint limiter action, retry, sleep, concurrency, thread, task, environment/config read, or lifecycle ownership. It changes no parser, HTTP path, authentication, rate limit, or D4A/D4B behavior.
- The planner is not imported by provider, valuation, pipeline, scheduler, FastAPI, alerts, config, factories, clients, sources, refresh services, or dry-run scripts. It is not production wiring. Phase 12D5B may add a controlled executor that consumes these immutable local plans without changing D5A's endpoint-neutral chunk semantics.

## Phase 12D5B Controlled Batch Refresh Executor Core

Input, identity, and ownership contract:
- `SteamDTRefreshExecutor.execute()` accepts only an existing `SteamDTRefreshPlan` and an explicit valid `PriceCachePolicy`; it never accepts raw item names and never canonicalizes, deduplicates, or chunks work again. Every unique plan item is passed at most once to the injected narrow `refresh_one(market_hash_name, policy)` protocol with its canonical name and the same policy object.
- D5A deliberately permits custom `PriceCacheKey.source` values, while the current D4A service always constructs the default version-1 `cs2`/`CNY`/`steamdt`/`platform_prices` key. This SteamDT-specific executor therefore rejects every non-default-source plan, including an empty one, before task creation or collaborator calls; it never discards or rewrites full planned identity.
- The injected refresher is borrowed. The executor creates no source, HTTP client, cache, Redis client, limiter, factory, or runtime; reads no environment/configuration; and neither closes nor otherwise owns any collaborator.

Chunk and concurrency contract:
- Chunks execute in their existing contiguous zero-based order. A per-chunk `asyncio.TaskGroup` with at most `min(max_concurrency, chunk size)` fixed workers is fully joined before the next chunk starts, and no tasks are created in advance for the complete plan. Empty plans return a complete empty report without workers or refresh calls.
- `max_concurrency` must be an exact positive integer and explicitly rejects `bool`. It limits simultaneously active full `refresh_one()` operations only. It is not a request-rate limit, provider batch size, quota, token bucket, or retry policy; the existing SteamDT client endpoint limiter remains the sole authority and every client-owned retry continues to acquire it normally.
- A D5B chunk remains a local execution boundary. The executor never calls or implies use of official `POST /open/cs2/v1/price/batch`, never combines item names into one source request, and encodes no undocumented provider limit.

Ordered result and aggregate contract:
- Frozen `SteamDTRefreshItemExecutionResult` records the original plan item, zero-based chunk and unique-item indices, `SUCCEEDED` or `FAILED`, and exactly one of the original `SteamDTPriceRefreshResult` or ordinary exception. Its canonical key/name are derived from the plan item. An explicit `error_type` exposes only the exception class name, while the actual exception is available to trusted callers but excluded from dataclass repr.
- Frozen `SteamDTRefreshExecutionReport` owns a defensive tuple of item results in plan order, independent of completion order. Public invariants reject missing, extra, duplicate/reordered, wrong-item, wrong-key, wrong-chunk, wrong-index, or contradictory success/failure records.
- `total_count`, success/failure counts, `NO_CANDIDATES`, `CACHE_PUT_COMPLETED`, each `CREATED`/`REPLACED`/`IGNORED_OLDER`/`UNCHANGED_EQUAL` count, chunk count, and completed chunk count are derived. A returned report is complete even when ordinary items fail, so completed chunk count equals plan chunk count. No duration, tracing, or independently supplied parallel counts exist.
- A valid D4A return is retained exactly. `NO_CANDIDATES` remains a normal success without a write result, and ignored/equal cache outcomes never claim incoming data was written. A non-result or wrong-key collaborator return fails closed as an isolated `SteamDTPriceRefreshValidationError`; no fake success is generated.

Failure and cancellation contract:
- Only ordinary `Exception` values are isolated per item. The exact typed SteamDT transport/status/API/rate-limit/parser error, adapter error, cache backend/codec error, refresh contract error, or other ordinary exception remains available by identity; it is not retried, stringified into the public model, replaced by fallback data, or allowed to cancel siblings. Remaining items in that chunk and all later chunks continue.
- `asyncio.CancelledError` is never caught as an item failure. Caller cancellation propagates through the task group, cancels and joins current workers, starts no later chunk, returns no partial report, and leaves no executor-owned detached task. Work that completed its source/cache side effects before cancellation is not rolled back; D5B is not a transaction or single-flight coordinator.

Current boundary and next integration seam:
- D5B performs no cache read, selector/resolver call, quote construction, avg-price lookup, cache-warming policy, retry/backoff/sleep, new limiter, single-flight, metrics, alerts, market operation, scheduler/pipeline/FastAPI/background-worker wiring, or production deployment.
- Automated tests use fake refreshers and existing domain models only; D5B connects neither real SteamDT nor Redis. D5C provides the independent manual composition seam below without changing this executor's local-chunk and borrowed-ownership contract.

## Phase 12D5C Manual End-to-End Refresh Integration Command

Command and orchestration contract:
- `scripts/steamdt_refresh_integration.py` is a standalone manual CLI supporting direct-file and module execution. It accepts repeatable raw `--item` values, `--chunk-size` (default 5), `--max-concurrency` (default 2), and `--mode fake|live` (default fake). At least one item is required.
- The CLI does not trim, filter, deduplicate, or chunk item values. The real D5A planner remains the sole canonicalization and stable-deduplication authority, then D5B runs its local chunks. After the complete executor report exists, one cached resolver reads the same `InMemoryPriceCache` once per unique item in plan order.
- The command composes the existing planner, executor, concrete/live or synthetic/fake snapshot source, D4A refresh service, one shared in-memory cache, and D3B resolver. It does not copy their concurrency, failure-isolation, adapter, cache, or selection logic.

Fake and live safety contract:
- Fake mode is deterministic, completely offline, and visibly marked synthetic. Its script-local source returns two selector-before candidates per item with string-constructed `Decimal` prices. These values are fixtures and do not represent market prices. Fake mode reads no API key or Redis URL and creates no HTTP, SteamDT, or Redis client; its request count is zero.
- Live mode requires both `--mode live` and `STEAMDT_RUN_REFRESH_INTEGRATION=true`. A disabled gate exits 2 before reading the API key or creating runtime/request state. After the gate, a nonblank API key is required.
- Enabled live mode reuses the existing SteamDT client runtime composition with the in-memory endpoint limiter, configured client retry policy, parser, typed errors, and concrete official single-price snapshot source. D5C adds no retry, limiter, sleep, batch request, fake fallback, or live resolver fallback. Every client-owned retry still acquires the existing limiter and counts as an outbound request attempt.
- Both modes always use one process-local `InMemoryPriceCache`; the command never imports or composes the Redis price cache or Redis limiter. The owned live runtime closes on success, ordinary failure, and cancellation. The enabled real online integration was intentionally not executed during D5C validation.

Outcome, output, and cancellation contract:
- `NO_CANDIDATES` remains a successful refresh and resolves to a normal cache miss when no earlier entry exists. Any isolated executor item failure causes command exit 1 after a complete ordered summary; orchestration/runtime/cleanup failure also exits 1. CLI/planner/live-gate validation exits 2; `KeyboardInterrupt` exits 130.
- Cancellation propagates rather than becoming an item or command failure. Current executor children are cancelled and joined, resolution does not start after cancelled execution, the owned live runtime closes, and no partial summary or detached command task is returned.
- Output is an allowlisted aggregate plus per-item plan-order summary. External item/platform text is redacted and JSON-escaped; failures expose only safe exception class names. API keys, Authorization values, Redis URLs/passwords, base URLs, raw payloads/candidates, exception messages, object reprs, and tracebacks are not printed.
- Request count must be an exact nonnegative integer; unreadable or invalid runtime counters are reported as `unavailable` and cause exit 1. `max_concurrency` remains only a bound on active refresh operations and is not a rate limiter or official batch-size rule.
- D5C is the first complete SteamDT manual integration milestone, but it is not production-ready and is not wired into provider, valuation, pipeline, scheduler, FastAPI, Discord, BUFF, or background work. The next product priority returns to real BUFF listing input; D5C does not begin that work.

## BUFF Listing Input Contract

- `app/services/buff_listing.py` establishes only the immutable data boundary from `BuffListingObservation` to `BuffTradableCandidate`. It does not define or guess a BUFF endpoint, request parameter, response mapping, authentication/signature method, or account/session behavior.
- Observations retain normalized listing identity, exact finite `Decimal` CNY price, exact nonnegative quantity, optional bounded Decimal float, optional normalized wear, optional exact paint seed, defensively copied string-pair sticker metadata, and aware UTC observation time. They retain no Cookie, Authorization value, session/account information, seller-private data, URL, raw HTTP response, or raw payload.
- `normalize_buff_listing()` revalidates the public observation and creates a detached immutable candidate. Candidates intentionally omit sticker metadata and all transport/provider data; quantity zero remains valid at this domain-contract boundary.
- Normalization performs no price decision, EV or trade-up calculation, SteamDT call, cache lookup, risk filter, selection, or market operation. Fixed field-only errors and disabled model repr prevent raw listing values or hostile exception text from being exposed.
- `BuffListingSource.fetch_listings()` is a protocol only. This phase implements no BUFF HTTP client, live BUFF connection, real listing data, API authentication, crawler/scraper, login, Cookie capture, captcha handling, risk-control bypass, browser automation, or automatic purchase.
- The contract is not imported by or wired into provider, valuation, pipeline, scheduler, FastAPI, config, Redis, SteamDT, Discord, or background work. It is not production-ready; confirmed official BUFF transport details remain tracked separately in `docs/BUFF_API_NOTES.md`.
- Phase 12E2A offline fixture/parser details now live in `docs/BUFF_LISTING_NOTES.md`; this SteamDT note intentionally does not define that BUFF fixture schema.

## Safety Notes

- Do not implement auto-buying.
- Do not implement auto-login.
- Do not scrape Cookie data.
- Do not bypass captcha.
- Do not bypass risk control.
- Do not use browser-simulated purchasing.
- Do not hardcode `STEAMDT_API_KEY`.
- Do not print the API key in logs.
- `DRY_RUN=true` must prevent real SteamDT requests.

## Planning Notes

- SteamDT is planned as a V1.1 supporting data source.
- SteamDT does not replace BUFF listing scanning.
- BUFF remains responsible for buyable material listings and candidate listing acquisition.
- SteamDT is currently planned for valuation, historical price sanity checks, optional metadata fallback, and optional wear support.
- The `mcp-steamdt` repository may be used as a design/reference source only. It should not become the production dependency of the 24h bot.
- Future production code should use direct SteamDT REST API clients rather than depending on MCP runtime services.
