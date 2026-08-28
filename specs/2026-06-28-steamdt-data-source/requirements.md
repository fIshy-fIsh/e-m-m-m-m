# SteamDT Data Source Requirements

## Functional Requirements

### 1. SteamDTClientConfig
配置应至少包含：
- `base_url`
- `api_key`
- `timeout_seconds`
- `max_retries`
- `dry_run`
- rate limits

### 2. SteamDTClient Protocol
协议应至少包含：
- `get_price_single`
- `get_price_batch`
- `get_base_item_info`
- `get_kline`
- `get_wear_info`

### 3. SteamDTHttpClient
要求：
- REST API skeleton
- timeout
- retry
- rate limit
- dry-run guard
- safe error handling
- public methods may still remain `NotImplementedError` until parser implementation phase if endpoint/field mapping is not fully reviewed

### 4. MockSteamDTClient
要求：
- deterministic test data
- no real request

### 5. DryRunSteamDTClient
要求：
- no real request
- safe empty / missing responses

### 6. PriceProvider Protocol
要求：
- `get_price`
- `get_prices`

### 7. SteamDTPriceProvider
要求：
- uses SteamDTClient
- returns `Decimal price_cny`
- can first be implemented with `MockSteamDTClient` and `SteamDTPriceProvider` in mock-only mode before real parser implementation

### 8. ValuationService
要求：
- takes `TradeupResult` list
- applies prices from `PriceProvider`
- returns updated `TradeupResult` list or valuation result
- does not change probabilities or floats

### 9. HistoricalPriceProvider
- optional future phase

### 10. MetadataProvider fallback
- optional future phase

### 11. WearProvider
- optional future phase

## Safety Requirements

- `STEAMDT_API_KEY` 只从 `.env` 读取
- 不硬编码 API key
- 不在 repr / logs / exceptions 里泄露 API key
- `DRY_RUN=true` 时不真实请求 SteamDT
- `dry_run=False` 必须显式配置 API key
- 不自动购买
- 不自动登录
- 不抓 Cookie
- 不绕过验证码
- 不绕过风控
- 不使用浏览器自动化
- 不把 SteamDT secret commit 到 git

## Architecture Requirements

- SteamDT 不耦合进 Trade-up Engine
- SteamDT 不耦合进 EV Service
- Trade-up Engine 只负责 probability / output float
- EV Service 只消费已经带 `estimated_price_cny` 的 `TradeupResult`
- ValuationService 负责价格注入
- Pipeline 可选接入 ValuationService
- 缺失价格必须有明确 fallback 策略
- 所有金额使用 `Decimal`
- 时间必须 timezone-aware
- 所有网络 client 必须可 mock

## Confirmed Endpoint Coverage for Future Phases

当前已确认的未来接口覆盖范围：
- `GET /open/cs2/v1/price/single`
- `POST /open/cs2/v1/price/batch`
- `GET /open/cs2/v1/base`
- `GET /open/cs2/v1/price/avg`
- `POST /open/cs2/item/v1/kline`
- `POST /open/cs2/v1/wear`

但需要明确：
- 本阶段不要实现 parser。
- 本阶段不要实现真实 endpoint mapping。
- 后续 parser implementation 应在单独阶段完成，并在 review 后接入真实 HTTP public methods。

## Future Parser Requirements

未来应单独实现以下 parser：
1. `parse_price_single_response`
2. `parse_price_batch_response`
3. `parse_avg_price_response`
4. `parse_base_info_response`
5. `parse_wear_response`
6. `parse_kline_response`

这些 parser 未来需要：
- 将 SteamDT raw response 映射到内部模型
- 保留 raw payload
- 处理缺失字段和空列表
- 严格遵守 Decimal / timezone-aware 规则

## Fallback Strategy

当 SteamDT price 缺失时，可选策略包括：
1. 保留原 `estimated_price_cny`
2. 标记 missing price
3. 使用 0 但 risk filter 必须拦截
4. 丢弃该 recipe
5. 后续由 config 控制

### V1.1 Recommended Default
推荐默认策略：
- 保留原值并记录 missing
- 如果 SteamDT price 缺失，则保留原 `TradeupResult.estimated_price_cny`
- 同时记录 missing market hash name 或 valuation warnings
- 如果 output price 大量缺失，risk filter 应保持保守
- 不因为单个 price 缺失导致整个 pipeline 崩溃

## Phase Boundary Constraint

当前阶段只同步文档事实，不进入真实 parser / pipeline 接入实现：
- 不实现真实 SteamDT endpoint parser
- 不实现真实 SteamDTHttpClient public endpoint mapping
- 不接入 PriceProvider 到 Pipeline
- 不接入 ValuationService 到 Recipe Solver
- 不真实请求 SteamDT
- 不真实发送 Discord
