# Feature Requirements — BUFF Trade-up Scanner

## 1. 功能需求

### 1.1 市场扫描
系统必须能够：
1. 周期性扫描 BUFF 市场上的 CS2 trade-up 材料
2. 获取并持久化以下最小字段（若可获得）：
   - goods_id
   - 市场名称 / hash name / display name
   - price
   - float
   - listing_id 或等效挂单标识
   - quantity / available count
   - raw payload snapshot
   - scan timestamp
3. 对同一轮扫描建立 `scan_run` 记录，支持后续审计与回放
4. 支持对异常、缺字段和解析失败 listing 做留档

### 1.2 Metadata 匹配与标准化
系统必须具备统一的 metadata 接口层：
1. trade-up engine 只能依赖统一 `MetadataProvider` / `MetadataClient` interface
2. `metadata_service` 负责把外部或本地 metadata normalize 为内部统一模型
3. 内部统一模型至少需要：
   - skin identifier
   - weapon / skin name
   - collection
   - rarity
   - min_float
   - max_float
   - 可 trade-up 输出候选
4. V1 默认设计可优先接入外部 metadata 源，例如 ByMykel CSGO-API
5. 必须保留 `LocalJsonMetadataProvider` 作为 fallback 或测试数据源设计
6. 不允许把某个外部 provider 的字段结构直接写死进上层业务逻辑

### 1.3 Trade-up 结果计算
系统必须支持：
1. 输入材料组合合法性判断
2. collection / rarity 约束下的输出池计算
3. 每个输出结果的概率计算
4. 基于 trade-up float 规则的输出 float 计算
5. 输出结果市场价格引用
6. EV 计算
7. ROI 计算
8. worst-case loss 计算
9. profit probability 计算

### 1.4 机会筛选
V1 默认采用保守高质量策略，系统必须：
1. 仅提醒 EV 明显为正的机会
2. 显式纳入手续费、滑点、保守卖出价假设
3. 过滤低流动性结果皮肤
4. 过滤最坏亏损过大的配方
5. 过滤材料买不齐或数量不足的配方
6. 过滤 BUFF 价格异常、孤立挂单、明显低成交量机会
7. 支持配置如下默认阈值：
   - `min_roi >= 5%`
   - `min_expected_profit_cny >= 20`
   - `profit_probability >= 35%`
   - `worst_case_loss_pct <= 25%`
   - result liquidity score 达标
8. 支持后续扩展 balanced / research mode，但 V1 默认不启用

### 1.5 提醒
系统必须：
1. 通过 Discord Webhook 发送提醒
2. 每条提醒至少包含：
   - 机会标识
   - 输入材料摘要
   - 输入总成本
   - 输出池摘要
   - EV / ROI
   - worst-case loss
   - profit probability
   - 核心假设（手续费、滑点、价格时间戳）
   - 生成时间
3. 支持重复提醒抑制与 cooldown
4. 支持发送失败重试和失败日志

### 1.6 运维与观测
系统必须：
1. 支持 24h scheduler 周期运行
2. 提供健康检查能力
3. 提供最近扫描状态与最近提醒状态可查询能力
4. 记录错误、重试、跳过原因、过滤原因

## 2. 非功能需求
1. **可复算性**：每次提醒必须可由持久化输入和公式复算
2. **可追踪性**：保存原始 listing snapshot 与 metadata 来源版本/时间戳
3. **可配置性**：阈值、调度频率、超时、重试策略、secret 必须配置化
4. **类型安全**：核心 domain DTO 和 engine 输入输出应具备明确类型边界
5. **稳定性**：调度任务需具备幂等保护、失败重试、锁机制或并发保护
6. **可测试性**：外部 API 层必须可 mock，不依赖真实 BUFF 请求完成测试
7. **可扩展性**：metadata source 和 alert channel 设计允许未来扩展，但 V1 不强制实现多源切换

## 3. 安全要求
1. 不允许实现自动购买
2. 不允许实现自动登录
3. 不允许 Cookie 抓取
4. 不允许验证码绕过
5. 不允许 BUFF 风控绕过
6. 不允许浏览器模拟购买
7. 不允许实现任何非官方风控规避能力
8. 不允许硬编码 API key、cookie、token、Discord Webhook URL
9. 所有 secret 必须从 `.env` 读取
10. 日志中不得泄露 secret、cookie、token、webhook URL
11. 若外部接口细节不确定，必须以 TODO / assumption 形式记录，不得编造

## 4. API 使用要求
1. 所有外部接口访问必须通过显式 client abstraction（如 `BuffClient`, `MetadataClient`, `DiscordWebhookClient`）
2. 所有 client 必须支持：
   - 超时配置
   - 重试策略
   - 错误分类
   - 响应校验
3. 对不确定字段，Pydantic model 应允许可选字段或原始 payload 保留
4. 若 endpoint、签名方式、参数、字段名不确定：
   - 写入 `docs/BUFF_API_NOTES.md`
   - 在 `docs/SPEC.md` 标注 assumption / TODO
   - 不得伪造正式字段 mapping
5. 测试环境中必须使用 mock response，不真实请求 BUFF

## 5. Discord Webhook Alert 要求
1. Webhook URL 必须从 `.env` 读取
2. alert payload 需要可扩展，支持后续 embed 或结构化字段增强
3. alert formatter 必须与发送逻辑解耦
4. 发送前必须做机会去重判定
5. 发送失败应支持有上限的重试与错误日志
6. 单条提醒中应标出该机会的关键风险与保守估值依据
7. V1 仅要求 Discord，不要求 Telegram 或其他渠道

## 6. BUFF API 不确定字段处理要求
1. 未确认 endpoint 必须写入 `docs/BUFF_API_NOTES.md`
2. 未确认签名方式必须写入 `docs/BUFF_API_NOTES.md`
3. 未确认响应字段必须写入 `docs/BUFF_API_NOTES.md`
4. `BuffClient` 可以先定义抽象 interface 和内部领域模型
5. 具体字段 mapping 仅能对已确认字段固化；未确认项必须标注 assumption 或 TODO
6. 原始响应体应保留，以支持后续字段修正与 replay
7. 若字段无法确认，不得阻止规格文档推进，但必须明确其为待确认假设

## 7. 第一版不做自动购买的明确限制
V1 的所有设计必须满足以下限制：
1. 系统只负责扫描、分析、筛选、提醒
2. 系统不得生成下单请求
3. 系统不得控制浏览器完成购买
4. 系统不得尝试登录 BUFF 账户
5. 系统不得抓取或导出用户 cookie
6. 系统不得包含任何验证码处理/规避逻辑
7. 系统不得包含任何风控绕过或模拟真人交易行为的设计
8. 后续即便扩展自动化，也必须作为新 phase、新规格单独评审，不属于本阶段和 V1