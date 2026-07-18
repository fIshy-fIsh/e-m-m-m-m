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
- This phase validates a local/test Redis server only. It does not deploy the cache, add a factory, read production cache settings, or wire provider, selector, valuation, pipeline, scheduler, FastAPI, refresh, warming, or background work.
- Namespace SCAN remains non-linearizable with concurrent writers and is not claimed to be Redis-Cluster-global.
- `price_avg=10/min` remains an internal project safety cap and is not a confirmed official SteamDT quota.

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
