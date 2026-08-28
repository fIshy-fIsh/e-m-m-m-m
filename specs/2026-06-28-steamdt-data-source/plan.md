# SteamDT Data Source Integration Plan

## Background

当前 V1 已经完成 dry-run baseline，系统已经具备：
- BUFF Client abstraction / mock / dry-run
- Market Scanner
- Metadata abstraction
- Trade-up Engine
- EV Service
- Risk Filter
- Recipe Solver
- End-to-End Mock Pipeline
- Discord Alert dry-run
- Scheduler
- Docker / 24h dry-run deployment hardening

SteamDT 是 V1.1 的新数据源集成目标。本阶段为 **Phase 1: design-only**，只完成设计文档、API notes、README 与环境变量规划，不进入业务实现代码阶段。

## Why Not Modify V1 Baseline Directly

- V1 baseline 已经稳定并完成 dry-run 验证。
- 当前分支从稳定的 V1 baseline 切出，适合作为 V1.1 设计与实验分支。
- 新数据源会引入新的字段语义、rate limit、价格口径、异常处理和权限边界。
- 如果在 V1 主线上直接引入 SteamDT，后续一旦发现 API 字段或价格口径不适合 EV，会带来更大范围返工。
- 使用独立分支可以降低对主线稳定性的破坏风险。

## Role of SteamDT

**SteamDT 不替代 BuffClient。**

### BUFF 负责
- material listing
- goods_id
- sell orders
- buyable material scanning
- candidate listings

### SteamDT 负责
- output price estimation
- historical price sanity check
- metadata fallback
- wear / inspect support if available
- market valuation support

## Target Architecture

### ListingProvider
- BUFF first
- 负责可购买 listing

### PriceProvider
- SteamDT first
- 负责 `market_hash_name -> price_cny`

### ValuationService
- 用 PriceProvider 给 TradeupResult 注入 `estimated_price_cny`
- 不改变 trade-up probability
- 不改变 float 计算

### HistoricalPriceProvider
- 提供价格历史 / kline
- 未来用于异常价格过滤

### MetadataProvider fallback
- SteamDT 可作为 metadata fallback
- 不替代现有 MetadataProvider

### WearProvider
- 如果 SteamDT 支持 inspect / wear
- 未来用于补全 `float_value` / `paint_seed`

## Recommended Development Phases

### Phase 1: Design docs and API notes
- 只完成：
  - `docs/STEAMDT_API_NOTES.md`
  - `plan.md`
  - `requirements.md`
  - `validation.md`
  - `README.md`
  - `.env.example`
- 不实现任何 SteamDT client / provider / valuation 代码。

### Phase 2: SteamDT Client abstraction
- 实现 `SteamDTClientConfig`
- 实现 `SteamDTClient` Protocol
- 实现 `MockSteamDTClient`
- 实现 `DryRunSteamDTClient`
- 实现 `SteamDTHttpClient` skeleton

### Phase 3: PriceProvider and ValuationService
- 实现 `PriceProvider`
- 实现 `SteamDTPriceProvider`
- 实现 `ValuationService`
- 将 SteamDT 价格注入 `TradeupResult.estimated_price_cny`

### Phase 4: Mock SteamDT valuation in pipeline
- 用 mock SteamDT price 数据接入 pipeline
- 让 output `estimated_price_cny` 不再固定为 0

### Phase 5: Historical price sanity check
- 用 SteamDT 历史价格支持异常价格过滤 / sanity check

### Phase 6: Optional metadata fallback
- 如果文档确认支持，增加 SteamDT 作为 MetadataProvider fallback

### Phase 7: Optional real SteamDT dry-run request
- 在 `DRY_RUN=false` 且经过 review 后，接入真实 SteamDT dry-run 请求

### Phase 8: Production readiness review
- review rate limit
- review price semantics
- review error handling
- review fallback strategy
- review observability and deployment safety

## Out of Scope

- 不做自动购买
- 不做订单执行
- 不替代 BuffClient
- 不改变 Recipe Solver 的 greedy 策略
- 不改变 Trade-up Engine 的 probability / float 逻辑
- 不真实请求 SteamDT
- 不真实请求 BUFF
- 不真实发送 Discord
- 不做浏览器自动化

## Risks and Open Questions

- SteamDT rate limit 是否足够支撑 24h bot
- price 字段口径是否适合 EV
- SteamDT 价格是否含手续费
- SteamDT 价格是否代表可成交价
- currency 是否稳定为 CNY
- `market_hash_name` 是否与 CS2 metadata 一致
- historical price 是否存在异常点
- wear endpoint 是否稳定
- 免费额度 / API 权限限制
- batch price 查询的上限和返回格式是否足够稳定
- metadata / wear 能否真正作为生产 fallback 使用
