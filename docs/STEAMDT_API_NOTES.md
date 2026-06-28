# SteamDT API Notes

## Source Links

* https://www.steamdt.com/
* https://github.com/Kir4kami/mcp-steamdt
* https://doc.steamdt.com/

## Confirmed Information

### Base URL
- `https://open.steamdt.com`

### Authentication 方式
- Bearer token authentication.

### API key 如何传递
- `Authorization: Bearer {API_KEY}`

### 是否需要 signature
- Confirmed from documentation page: no signature mechanism is required.

### 请求 headers
- `Authorization: Bearer {API_KEY}`
- `Content-Type: application/json` is shown in the curl example.

### rate limit
- TODO: Not confirmed yet.

### price single endpoint
- TODO: Not confirmed yet.

### price batch endpoint
- TODO: Not confirmed yet.

### base item info endpoint
- TODO: Not confirmed yet.

### kline / historical price endpoint
- TODO: Not confirmed yet.

### wear endpoint
- Confirmed: `POST /open/cs2/v1/wear`
- Example full URL shown in docs: `https://open.steamdt.com/open/cs2/v1/wear`

### request params
- Confirmed for wear endpoint example body:
  - `inspectUrl`
  - `notifyUrl`
- Other endpoint request params:
  - TODO: Not confirmed yet.

### response fields
- Confirmed response wrapper fields shown in docs:
  - `success`
  - `errorCode`
  - `errorMsg`
  - `data`
  - `errorData`
  - `errorCodeStr`
- Endpoint-specific business response fields:
  - TODO: Not confirmed yet.

### error response format
- Confirmed: docs show failed responses include `success`, `errorCode`, `errorMsg`.
- Additional error fields may include `errorData` and `errorCodeStr`.

### timestamp 格式
- TODO: Not confirmed yet.

### currency 字段
- TODO: Not confirmed yet.

### price 字段精度
- TODO: Not confirmed yet.

### item name / market_hash_name 字段
- TODO: Not confirmed yet.

### 是否支持批量查询
- TODO: Not confirmed yet.

### 是否支持饰品基础信息
- TODO: Not confirmed yet.

### 是否支持历史价格
- TODO: Not confirmed yet.

### 是否支持 inspect / wear 查询
- Confirmed: documentation exposes a wear endpoint.

### protocol / encoding
- Confirmed: HTTPS.
- Confirmed: UTF-8 is stated for requests and responses.

## Internal Mapping Plan

### 1. SteamDTPriceQuote
Potential future mapping:
- `market_hash_name`
  - TODO: Not confirmed yet.
- `price_cny`
  - TODO: Not confirmed yet.
- `source`
  - Internal constant recommendation: `"steamdt"`
- `raw`
  - Preserve full raw payload.

### 2. SteamDTBatchPriceResult
Potential future mapping:
- `quotes`
  - TODO: Not confirmed yet.
- `missing`
  - TODO: Not confirmed yet.
- `raw`
  - Preserve full raw payload.

### 3. SteamDTBaseItemInfo
Potential future mapping:
- `market_hash_name`
  - TODO: Not confirmed yet.
- `raw`
  - Preserve full raw payload.

### 4. SteamDTHistoricalPricePoint
Potential future mapping:
- `market_hash_name`
  - TODO: Not confirmed yet.
- `timestamp`
  - TODO: Not confirmed yet.
- `price_cny`
  - TODO: Not confirmed yet.
- `raw`
  - Preserve full raw payload.

### 5. SteamDTWearInfo
Potential future mapping:
- `inspect_link`
  - Likely source request field: `inspectUrl`
  - TODO: response-side field mapping is not confirmed yet.
- `float_value`
  - TODO: Not confirmed yet.
- `paint_seed`
  - TODO: Not confirmed yet.
- `raw`
  - Preserve full raw payload.

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
