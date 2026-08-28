# Feature Validation — BUFF Trade-up Scanner

## 1. 验证目标
本文件定义 MVP 在实现阶段必须满足的测试与验收要求。当前阶段仅定义验证标准，不实现业务代码。

## 2. 每个模块的测试方式

### 2.1 配置与基础设施模块
验证方式：
- 单元测试 `.env` -> settings 映射
- 校验缺失必填 secret 时系统启动失败
- 校验日志配置不会输出 secret 原文
- 校验数据库与 Redis 配置对象正确构造

### 2.2 BUFF Client 模块
验证方式：
- 使用 mock HTTP 响应测试请求构造、超时、重试、错误分类
- 测试已确认字段的解析逻辑
- 测试字段缺失、字段类型异常、响应结构变化时的容错行为
- 测试原始 payload snapshot 是否完整保留
- 测试未确认字段不会被错误写死到业务逻辑

### 2.3 Metadata Provider / Metadata Service 模块
验证方式：
- 使用 mock provider 响应测试 normalize 逻辑
- 测试外部 provider 到内部统一 metadata model 的映射
- 测试 `LocalJsonMetadataProvider` 作为测试源或 fallback 的行为
- 测试 collection / rarity / min_float / max_float 映射正确性
- 测试 provider 字段缺失时的降级和错误记录

### 2.4 Trade-up Engine 模块
验证方式：
- 针对固定输入材料样例进行 deterministic 计算测试
- 校验输出池构造正确性
- 校验概率总和为 1（允许定义微小浮点误差容忍）
- 校验输入非法时返回明确错误或拒绝计算
- 校验不同 collection / rarity 组合下结果边界

### 2.5 Float Calculation 模块
验证方式：
- 针对已知样例测试 trade-up 输出 float 计算
- 覆盖 min_float / max_float 边界
- 覆盖接近 0 与接近 1 的极端浮点输入
- 覆盖输出 float 被目标皮肤 float range 截断/限制的情形
- 使用高精度断言避免隐藏数值误差

### 2.6 EV / ROI / Worst Case / Profit Probability 模块
验证方式：
- 固定价格与概率样例下校验 EV 数值
- 校验 ROI = (expected_profit / total_cost) 的一致性
- 校验 worst-case loss 的定义与实现一致
- 校验 profit probability 为盈利输出概率之和
- 校验手续费、滑点、保守卖出价已进入计算
- 测试零利润、负 EV、单一高价值输出、低概率大收益等边界场景

### 2.7 Risk Filter 模块
验证方式：
- 针对默认保守阈值编写阈值边界测试
- 测试低流动性结果被过滤
- 测试异常价格、孤立挂单、数量不足被过滤
- 测试高 EV 但高 worst-case loss 配方是否按规则排除
- 测试过滤结果带有可解释原因码/原因文本

### 2.8 Opportunity Service 模块
验证方式：
- 测试从 listing + metadata 到 opportunity 的完整组装流程
- 测试重复机会识别
- 测试同一机会在 cooldown 窗口内不会重复提醒
- 测试失败情况下的状态落库与重试行为

### 2.9 Discord Webhook 模块
验证方式：
- 使用 mock webhook endpoint 验证请求格式
- 测试 alert formatter 生成的文本/结构是否包含关键字段
- 测试 webhook 失败重试逻辑
- 测试 secret 不进入日志
- 测试发送成功与失败的审计记录

### 2.10 Scheduler 模块
验证方式：
- 单元测试 job 注册与 cron/interval 配置
- 集成测试扫描 -> enrich -> calculate -> filter -> alert 编排顺序
- 测试 job 幂等与重复运行保护
- 测试任务失败后重试或下次调度不被阻塞
- 测试长时间运行下状态清理/锁释放逻辑

## 3. ruff / mypy / pytest 验证要求
实现阶段的最低验证命令基线必须明确包含：
1. `ruff check .`
2. `mypy app`
3. `pytest`

补充要求：
1. `ruff check .` 必须通过，无未处理 lint 错误
2. `mypy app` 必须通过，至少覆盖核心 domain / engine / client / service 层
3. `pytest` 必须通过，核心计算模块测试不可跳过
4. 对数值计算、字段映射、外部 API 契约的测试必须纳入默认测试集
5. 如存在暂未确认的外部字段，测试中应以 mock 假设明确标注

## 4. 外部 API mock 测试要求
1. BUFF 测试不得依赖真实线上请求
2. Metadata provider 测试不得依赖第三方服务在线可用
3. Discord Webhook 测试必须使用 mock endpoint
4. mock response 需要覆盖：
   - 正常响应
   - 字段缺失
   - 结构变化
   - 超时
   - 429 / 5xx / 网络错误
5. 原始 payload 保存与错误留档行为必须可测试

## 5. float / EV / probability 核心计算测试要求
1. 为每个核心公式建立独立样例测试
2. 使用可人工复核的小样本 fixture
3. 概率测试必须验证总和接近 1
4. float 计算必须覆盖 trade-up 标准公式与结果 float range 限制
5. EV 测试必须覆盖手续费、滑点、保守卖出价假设
6. profit probability 测试必须明确“盈利”的定义阈值
7. worst-case loss 测试必须定义采用的最坏结果场景与计算口径
8. 所有核心数值计算需定义浮点误差容忍区间

## 6. Discord Webhook 测试要求
1. 测试 payload 包含机会摘要、成本、EV、ROI、worst-case、profit probability、时间戳
2. 测试格式化层与发送层分离
3. 测试 webhook URL 仅从配置读取
4. 测试 webhook 异常不会导致整个扫描流程崩溃
5. 测试重复机会不会因重试机制而产生重复提醒风暴

## 7. 24h Scheduler 验证要求
1. 必须验证调度任务能持续注册并执行
2. 必须验证调度周期可配置
3. 必须验证进程重启后的恢复策略或首次启动行为
4. 必须验证并发执行保护，避免同一任务重叠跑多次
5. 必须验证失败任务不会阻断后续周期运行
6. 必须验证长时间运行中缓存、锁、临时状态不会无界增长
7. 必须提供至少一种本地或测试环境的加速验证方案，用于模拟 24h 持续运行场景

## 8. MVP 最终验收基线
实现阶段完成后，应至少满足：
1. 模块级单元测试通过
2. 外部 API mock 集成测试通过
3. 关键数值计算样例通过人工复核
4. Discord mock alert 端到端链路通过
5. scheduler 编排链路通过
6. `ruff`, `mypy`, `pytest` 全部通过
7. 不包含任何自动购买、自动登录、Cookie 抓取、验证码绕过、BUFF 风控绕过或浏览器模拟购买实现