# CS2 BUFF Trade-up Opportunity Scanner — Technical Specification

## 1. 项目目标
本项目的目标是构建一个后端优先、可 24h 无人值守运行的 CS2 trade-up 机会扫描系统，用于持续发现并提醒高质量 BUFF 炼金机会。

系统需要完成以下闭环：
1. 定时扫描 BUFF 市场上的候选炼金材料
2. 获取并保留价格、float、goods_id、挂单上下文等市场数据
3. 结合 CS2 metadata 归一化得到 collection、rarity、min_float、max_float 与可产出结果池
4. 计算 trade-up 输出概率、输出 float、EV、ROI、worst-case loss 与 profit probability
5. 使用保守高质量策略过滤低质量机会
6. 通过 Discord Webhook 发送提醒

V1 的定位是 **notification-only scanner**，不进行任何交易执行。

## 2. 非目标
V1 明确不做：
- 自动购买
- 自动登录
- Cookie 抓取
- 验证码绕过
- BUFF 风控绕过
- 浏览器模拟购买
- 非官方规避检测 / 反风控技术
- Telegram 或多渠道提醒
- 多数据源自动切换
- 资金管理、自动仓位分配、组合层回测

## 3. 技术栈
- Python 3.12
- FastAPI
- PostgreSQL
- Redis
- SQLAlchemy 2.0
- Alembic
- Pydantic
- httpx
- APScheduler
- pytest
- ruff
- mypy
- Docker Compose

技术栈原则：
- modular monolith 架构
- 外部依赖通过 client/provider abstraction 隔离
- 核心公式、过滤规则与配置分离
- 所有 secret 从 `.env` 读取，不允许硬编码

## 4. 系统架构
建议采用以下逻辑分层：

### 4.1 API / Ops Layer
职责：
- FastAPI 健康检查
- 最近扫描状态查询
- 最近机会与提醒记录查询
- 运维/调试接口（如手动触发一次扫描）

### 4.2 Scheduler Layer
职责：
- APScheduler 负责周期任务注册与编排
- 扫描任务、metadata refresh、清理任务的调度
- 防重入、失败记录、心跳管理

### 4.3 Client / Provider Layer
职责：
- `BuffClient`：封装 BUFF 市场数据访问
- `MetadataProvider` / `MetadataClient`：封装 CS2 metadata 来源
- `DiscordWebhookClient`：封装提醒发送

### 4.4 Service Layer
职责：
- `scan_service`：扫描、解析、落库 listing snapshots
- `metadata_service`：provider -> internal normalized metadata
- `opportunity_service`：组织计算、过滤、持久化与提醒
- `alert_service`：提醒格式化、去重、发送、失败重试

### 4.5 Engine Layer
职责：
- `tradeup_engine`：输出池与概率
- `float_engine`：trade-up float 计算
- `pricing_engine`：材料成本与结果估值汇总
- `ev_engine`：EV / ROI / worst-case / profit probability
- `risk_filter`：高质量机会筛选

### 4.6 Data Layer
职责：
- PostgreSQL：主存储
- Redis：缓存、锁、重复提醒抑制、短期状态

## 5. 数据来源

### 5.1 BUFF 市场数据
目标数据：
- materials listings
- price
- goods_id
- float
- listing metadata / raw payload
- availability / quantity if available

注意：
- 当前 BUFF endpoint、签名、字段仍有未确认项
- 所有未确认细节必须记录在 [docs/BUFF_API_NOTES.md](docs/BUFF_API_NOTES.md)
- 文档阶段不编造 endpoint 和字段

### 5.2 CS2 Metadata 数据
V1 采用统一 metadata interface：
- 上层 engine 只依赖统一 `MetadataProvider` / `MetadataClient`
- 默认规划可优先接入外部 metadata 数据源，例如 ByMykel CSGO-API
- 保留 `LocalJsonMetadataProvider` 作为 fallback 或测试数据源
- `metadata_service` 负责 normalize，不允许把外部 provider 字段直接写死到业务逻辑

### 5.3 估值与提醒数据
- 输出结果价格可来自后续扩展的市场价格源或同一市场数据抽象
- Discord Webhook 作为 V1 唯一提醒通道

## 6. 核心模块
1. **BUFF Scan Module**
   - 获取 candidate materials
   - 解析 listing snapshots
   - 持久化原始市场数据

2. **Metadata Normalize Module**
   - provider abstraction
   - collection / rarity / float range normalize
   - result pool 所需 metadata 组装

3. **Trade-up Engine Module**
   - 输入合法性校验
   - 输出池构建
   - 输出概率计算
   - 输出 float 计算

4. **Economics Module**
   - 成本聚合
   - 卖出价保守估值
   - EV / ROI / worst-case / profit probability

5. **Risk Filter Module**
   - 阈值过滤
   - 流动性过滤
   - 异常价格过滤
   - 数量/可执行性过滤

6. **Alert Module**
   - Discord payload formatting
   - dedupe / cooldown
   - retry / failure logging

7. **Scheduler & Ops Module**
   - 24h recurring jobs
   - health checks
   - observability / run history

## 7. 数据模型草案
以下为 V1 建议的核心实体草案：

### 7.1 scan_runs
字段建议：
- id
- started_at
- finished_at
- status
- source
- listing_count
- error_count
- notes

### 7.2 market_listings
字段建议：
- id
- scan_run_id
- source_market
- listing_id
- goods_id
- market_hash_name
- display_name
- price_cny
- float_value
- available_quantity
- currency
- raw_payload_json
- observed_at
- parse_status
- parse_error

### 7.3 item_metadata
字段建议：
- id
- item_key
- provider_name
- provider_version
- weapon_name
- skin_name
- collection_name
- rarity
- min_float
- max_float
- normalized_payload_json
- source_payload_json
- refreshed_at

### 7.4 tradeup_candidates
字段建议：
- id
- candidate_key
- input_rarity
- target_rarity
- collection_name
- input_count
- total_cost_cny
- avg_input_float
- market_snapshot_at
- metadata_version

### 7.5 tradeup_outputs
字段建议：
- id
- candidate_id
- output_item_key
- probability
- estimated_output_float
- conservative_sale_price_cny
- liquidity_score
- is_profitable

### 7.6 opportunities
字段建议：
- id
- opportunity_key
- candidate_id
- ev_cny
- roi_pct
- expected_profit_cny
- worst_case_loss_cny
- worst_case_loss_pct
- profit_probability
- liquidity_score
- filter_status
- filter_reason
- created_at

### 7.7 alert_events
字段建议：
- id
- opportunity_id
- channel
- dedupe_key
- payload_json
- send_status
- retry_count
- sent_at
- error_message

说明：
- 以上为逻辑草案，不代表最终字段完全锁定
- 未确认的外部字段需通过 raw payload + normalize 模式吸收，而不是直接污染上层模型

## 8. BUFF Client 设计
`BuffClient` 负责外部市场数据获取，其设计要求：

### 8.1 设计原则
- 所有 BUFF 请求统一通过该 client 发出
- 上层只依赖内部 listing snapshot 模型
- endpoint、签名、字段不确定项不得在设计中伪造
- 请求层与解析层分离

### 8.2 抽象职责
- fetch candidate listings
- parse confirmed fields into internal DTO
- preserve raw payload for unknown fields and replay
- classify errors: timeout / rate limit / parsing / upstream failure
- expose retry-safe interface to services

### 8.3 不确定项处理
- 未确认 endpoint、签名、参数、字段必须写入 [docs/BUFF_API_NOTES.md](docs/BUFF_API_NOTES.md)
- 可先定义最小 listing DTO：
  - goods_id
  - listing_id
  - price
  - float if available
  - quantity if available
  - observed_at
  - raw payload
- 不将假设字段写死为正式 domain 契约

## 9. Metadata Client 设计
V1 采用 provider 抽象：

### 9.1 核心原则
- trade-up engine 只依赖统一 metadata interface
- `metadata_service` 负责 normalize
- 不允许在业务逻辑中直接绑定某个外部 provider 的原始字段结构

### 9.2 设计建议
- `MetadataProvider`：定义按 item key / collection / rarity 查询的接口
- `ExternalMetadataProvider`：面向外部 API
- `LocalJsonMetadataProvider`：面向本地 JSON fallback / test source
- `metadata_service`：把 provider 输出转换为统一 internal metadata model

### 9.3 统一内部 metadata 模型
建议至少包含：
- item_key
- weapon_name
- skin_name
- collection_name
- rarity
- min_float
- max_float
- output_pool linkage
- provider provenance

## 10. Trade-up Engine 设计
trade-up engine 的职责是从标准化输入构造出可计算的 recipe 与输出池。

### 10.1 输入
- 10 个可用于同一 trade-up 规则的输入材料
- 每个输入的：
  - item identity
  - collection
  - rarity
  - input float
  - acquisition cost

### 10.2 核心步骤
1. 校验输入数量、稀有度一致性与 trade-up 合法性
2. 识别涉及 collection 集合
3. 按 collection 规则构造可能输出池
4. 计算每个输出的概率
5. 传递输入平均 float 给 float engine
6. 结合估值模块得到最终经济性结果

### 10.3 结果要求
输出对象至少应包含：
- candidate summary
- output items
- probability per output
- output float estimate
- pricing inputs used
- economics result
- filter decision context

## 11. Float 计算设计
V1 需要把 trade-up 输出 float 作为一等公民处理。

### 11.1 输入
- 10 个输入材料 float
- 输出皮肤 min_float / max_float

### 11.2 设计原则
- 使用可审计、可测试的标准 trade-up float 公式
- 采用高精度数值处理策略，避免隐藏精度误差
- 对接近边界值的输入（接近 0 或 1）必须有测试覆盖

### 11.3 输出
- 每个候选输出的估算 float
- 结果 float 是否落入特定 wear band 的衍生能力可作为后续扩展，但不是 V1 强制项

## 12. EV / ROI / Worst Case / Profit Probability 设计

### 12.1 成本侧
输入成本必须包含：
- 10 个材料采购成本汇总
- 任何显式费用（若有）

### 12.2 收益侧
输出估值必须采用保守口径：
- 必须考虑手续费
- 必须考虑滑点
- 必须采用保守卖出价，而不是理想最高成交价
- 应结合流动性和可成交性做保守折扣

### 12.3 指标定义
- **EV**：所有可能输出的概率加权净收益期望值
- **ROI**：期望净收益 / 总成本
- **Worst Case Loss**：最差输出结果下的净亏损
- **Profit Probability**：净利润大于 0 的输出概率总和

### 12.4 边界要求
- 需明确定义“盈利”的判断标准
- 需定义手续费、滑点、保守卖出价配置来源
- 需对 0 利润、负 EV、极低概率大收益场景进行单独测试

## 13. Risk Filter 设计
V1 默认采用保守高质量策略。

### 13.1 默认过滤目标
优先减少假阳性，只提醒高置信、高流动性、可复算、可执行的机会。

### 13.2 默认规则
建议默认阈值：
- `min_roi >= 5%`
- `min_expected_profit_cny >= 20`
- `profit_probability >= 35%`
- `worst_case_loss_pct <= 25%`
- result liquidity score 达标

### 13.3 必须过滤的情况
- 低流动性结果皮肤
- 买不齐材料 / 数量不足
- BUFF 价格异常
- 孤立挂单
- 明显低成交量
- 仅因单个异常价导致的虚高 EV

### 13.4 设计要求
- filter 应输出明确 reason code / reason text
- 阈值必须配置化
- 后续可扩展 balanced / research mode，但 V1 默认只提供保守策略

## 14. Discord Webhook Alert 设计

### 14.1 发送原则
- V1 唯一提醒通道为 Discord Webhook
- Webhook URL 必须从 `.env` 读取
- 不允许硬编码到代码、测试夹具、日志或文档示例中

### 14.2 alert 内容
每条提醒至少包含：
- 机会标识
- 输入材料摘要
- 总成本
- 输出池摘要
- EV
- ROI
- worst-case loss
- profit probability
- 关键风险说明
- 手续费 / 滑点 / 价格时间戳等核心假设

### 14.3 工程要求
- formatter 与 sender 分离
- 支持 dedupe / cooldown
- 支持失败重试
- 失败不应导致整个扫描主流程崩溃

## 15. Scheduler 24h 运行设计

### 15.1 任务类型
建议至少规划：
- market scan job
- metadata refresh job
- opportunity evaluation job
- alert dispatch job
- cleanup / housekeeping job

### 15.2 运行要求
- 支持 24h 无人值守
- 调度频率配置化
- 防重入/并发保护
- 单任务失败不阻塞后续周期
- 记录每轮运行状态和错误计数

### 15.3 Redis 用途
- 分布式锁或互斥控制
- cooldown 与 dedupe key
- 短期缓存
- 临时状态保存

## 16. 测试策略

### 16.1 测试层级
- 单元测试：engine、filter、formatter、parser、settings
- 集成测试：service orchestration、db、redis、scheduler
- mock external API tests：BUFF、metadata provider、Discord webhook
- 少量端到端链路测试：scan -> enrich -> compute -> filter -> alert

### 16.2 质量门禁
- `ruff check .` 通过
- `mypy app` 通过
- `pytest` 通过
- 核心公式测试不可跳过

### 16.3 外部 API 测试原则
- 不真实请求 BUFF
- 不依赖第三方 metadata 服务在线
- Discord 使用 mock endpoint
- mock 场景需覆盖超时、429、5xx、字段缺失、结构变化

### 16.4 核心计算测试重点
- float 公式
- 输出概率总和约等于 1
- EV / ROI / worst-case / profit probability 样例
- 手续费、滑点、保守卖出价已纳入结果

## 17. MVP Roadmap

### Phase 1 — Specification and Project Skeleton
交付：
- global specs
- feature specs
- `docs/SPEC.md`
- `docs/BUFF_API_NOTES.md`

### Phase 2 — Foundation and Environment
交付：
- FastAPI skeleton
- settings / logging / db / redis / scheduler
- Docker Compose
- lint / type / test baseline

### Phase 3 — Market Ingestion
交付：
- BUFF client abstraction
- listing fetch + persistence
- scan run tracking

### Phase 4 — Metadata Enrichment
交付：
- metadata provider abstraction
- normalization pipeline
- collection / rarity / float range mapping

### Phase 5 — Trade-up Engine
交付：
- output pool
- probability
- float
- EV / ROI / worst-case / profit probability

### Phase 6 — Risk Filtering and Opportunity Selection
交付：
- conservative filters
- liquidity / anomaly / quantity checks
- opportunity persistence

### Phase 7 — Alerting and Operations
交付：
- Discord webhook alerting
- dedupe / cooldown
- recurring scheduler jobs

### Phase 8 — Hardening and Release
交付：
- integration tests
- failure handling improvements
- MVP deployment readiness

## 18. 验收标准

### 18.1 规格阶段验收
- 范围与非目标清晰
- 架构与模块边界清晰
- 数据模型草案可支持后续实现
- BUFF 不确定项已显式记录，不存在编造字段

### 18.2 实现阶段验收
- 能周期性获取候选材料 listing
- 能完成 metadata 归一化与 trade-up 计算
- 能输出 EV / ROI / worst-case / profit probability
- 能按保守策略过滤低质量机会
- 能通过 Discord 发送提醒
- `ruff` / `mypy` / `pytest` 全部通过
- mock external API tests 覆盖关键路径
- 不包含任何自动购买、自动登录、Cookie 抓取、验证码绕过、BUFF 风控绕过或浏览器模拟购买能力

## 19. 当前未确认 API 假设
当前仍存在以下未确认点：
- BUFF listing endpoint
- BUFF 请求签名 / 认证要求
- BUFF 响应字段命名与稳定性
- float 是否直接由 listing 接口返回
- 订单深度 / 流动性字段是否官方可得

这些内容已经被要求记录在 [docs/BUFF_API_NOTES.md](docs/BUFF_API_NOTES.md) 中，后续在获得正式细节前不得编造成正式实现契约。