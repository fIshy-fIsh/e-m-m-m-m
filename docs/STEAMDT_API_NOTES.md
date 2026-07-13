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
