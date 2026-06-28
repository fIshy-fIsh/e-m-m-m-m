# Feature Plan — BUFF Trade-up Scanner

## 1. 项目目标
构建一个面向 CS2 trade-up 机会发现的后端系统，能够 24h 定时扫描 BUFF 市场材料，结合 CS2 metadata 进行标准化与 trade-up 计算，筛选高质量机会，并通过 Discord Webhook 发送提醒。

核心目标：
1. 自动获取可用于炼金的 BUFF 材料挂单与价格信息
2. 归一化材料与 CS2 collection / rarity / float 元数据
3. 计算输出池、概率、输出 float、EV、ROI、worst-case loss、profit probability
4. 以保守、高质量策略过滤机会
5. 通过 Discord Webhook 发送可复算、可执行的提醒

## 2. MVP 范围
MVP 仅包含以下能力：
- BUFF 市场材料扫描
- 价格、goods_id、float、挂单上下文采集与落库
- CS2 metadata 标准化与映射
- trade-up 结果池计算
- float / EV / ROI / worst-case / profit probability 计算
- 风险过滤与机会筛选
- Discord Webhook 通知
- 24h scheduler 持续运行
- 基本日志、重试、去重、健康检查

## 3. 非目标
以下内容明确不属于 V1：
- 自动购买
- 自动登录
- Cookie 抓取
- 验证码绕过
- BUFF 风控绕过
- 浏览器模拟购买
- 非官方规避检测或反风控技术
- 多数据源自动切换
- 资产管理、资金分配、回测系统
- Telegram 通知

## 4. 系统架构
采用 Python modular monolith 架构：

1. **clients 层**
   - `BuffClient`：BUFF 数据获取抽象
   - `MetadataClient` / `MetadataProvider`：CS2 metadata 获取抽象
   - `DiscordWebhookClient`：提醒发送抽象

2. **services 层**
   - `scan_service`：发起扫描并持久化原始 listing
   - `metadata_service`：做 metadata normalize 与映射
   - `opportunity_service`：组织引擎计算、过滤、落库、提醒
   - `alert_service`：机会去重与发送

3. **engine 层**
   - `tradeup_engine`：输出池与概率计算
   - `float_engine`：trade-up 输出 float 计算
   - `ev_engine`：EV / ROI / worst case / profit probability 计算
   - `risk_filter`：基于阈值与流动性规则进行筛选

4. **data 层**
   - PostgreSQL：持久化 listings、metadata、recipes、opportunities、alerts、scan_runs
   - Redis：缓存、分布式锁、重复提醒抑制、临时状态

5. **api / ops 层**
   - FastAPI：健康检查、配置查看、机会查询、最近扫描状态、手动触发任务
   - APScheduler：24h 定时调度

## 5. 模块拆分
### 5.1 配置与基础设施
- `.env` 驱动的 settings
- 日志与 tracing 上下文
- 数据库连接
- Redis 连接
- Docker Compose 本地运行环境

### 5.2 BUFF 市场采集模块
- 候选材料扫描入口
- listing 快照采集
- goods_id / 价格 / float / 挂单信息解析
- 原始响应留档
- endpoint/字段未确认项的 TODO 管理

### 5.3 Metadata 标准化模块
- 统一 `MetadataProvider` 接口
- 外部 metadata provider（默认可规划为 ByMykel 类外部源）
- `LocalJsonMetadataProvider` 作为 fallback / test source
- collection / rarity / min_float / max_float / output pool 所需字段 normalize

### 5.4 Trade-up 计算模块
- 输入合法性校验
- collection 内结果池构造
- 输出概率计算
- 输出 float 计算
- EV / ROI / worst-case / profit probability 计算

### 5.5 Risk Filter 模块
默认采用保守高质量策略：
- 仅保留 EV 明显为正机会
- 必须计入手续费、滑点、保守卖出价
- 过滤低流动性结果皮肤
- 过滤材料买不齐、数量不足、价格异常、孤立挂单等情况
- 默认阈值偏保守：
  - min_roi >= 5%
  - min_expected_profit_cny >= 20
  - profit_probability >= 35%
  - worst_case_loss_pct <= 25%

### 5.6 Alert 模块
- 机会摘要格式化
- Discord Webhook 发送
- 去重与 cooldown
- 失败重试与告警日志

### 5.7 Scheduler 与运维模块
- 周期扫描任务
- metadata refresh 任务
- 清理/归档任务
- 心跳、健康检查、失败统计

## 6. 开发阶段顺序
### Stage A — 规格与设计
交付：
- `specs/2026-06-27-buff-tradeup-scanner/plan.md`
- `specs/2026-06-27-buff-tradeup-scanner/requirements.md`
- `specs/2026-06-27-buff-tradeup-scanner/validation.md`
- `docs/SPEC.md`
- `docs/BUFF_API_NOTES.md`

### Stage B — 工程基础设施
交付：
- FastAPI skeleton
- settings / logging / db / redis / scheduler bootstrap
- Docker Compose
- ruff / mypy / pytest / Alembic 基线

### Stage C — BUFF 市场采集
交付：
- `BuffClient` 抽象
- listing scan workflow
- 原始响应记录与 listing 落库
- 基本 retry / backoff / rate-limit guard

### Stage D — Metadata 标准化
交付：
- `MetadataProvider` 接口
- 外部 provider + 本地 JSON provider 设计落地
- normalize pipeline
- item -> collection / rarity / float range 映射

### Stage E — Trade-up Engine
交付：
- recipe / output pool builder
- probability engine
- float calculator
- EV / ROI / worst-case / profit probability calculator

### Stage F — Risk Filter 与机会筛选
交付：
- 保守过滤阈值
- 流动性规则
- 异常价格识别
- 高质量机会落库

### Stage G — Alerting 与调度
交付：
- Discord Webhook client
- alert formatter
- dedupe / cooldown
- APScheduler jobs
- 端到端扫描 -> 计算 -> 提醒链路

### Stage H — 测试与发布准备
交付：
- mock external API test suite
- integration tests
- 关键公式校验样例
- 运维文档与 MVP 验收结果

## 7. 每阶段交付物
| 阶段 | 目标 | 主要交付物 |
|---|---|---|
| A | 定义规格 | 本目录 3 个 spec + `docs/SPEC.md` + `docs/BUFF_API_NOTES.md` |
| B | 建立工程底座 | app skeleton、db、redis、scheduler、tooling |
| C | 采集 BUFF 数据 | `BuffClient`、scan job、listing persistence |
| D | metadata 归一化 | `MetadataProvider`、normalize pipeline |
| E | 炼金引擎 | float / probability / EV calculators |
| F | 机会筛选 | risk filter、opportunity selector |
| G | 发送提醒 | Discord alerts、dedupe、cooldown、scheduled run |
| H | 确认可发布 | tests、验收记录、运行文档 |

## 8. 当前结论
当前应进入：
- **项目规格与技术设计阶段**
- **不是业务代码实现阶段**

本阶段完成后应停止，不写业务实现代码。