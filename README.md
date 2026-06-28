# CS2 BUFF Trade-up Opportunity Scanner

## 项目简介
这是一个面向 CS2 炼金机会发现的后端项目骨架。目标是在 V1 中实现只读扫描、metadata 标准化、trade-up 计算、风险过滤和 Discord Webhook 提醒。

**V1 明确不做自动购买。** 也不做自动登录、Cookie 抓取、验证码绕过、BUFF 风控绕过或浏览器模拟购买。

## 本地开发步骤
1. 安装 Python 3.12
2. 创建虚拟环境并激活
3. 安装依赖：
   - `pip install -e .[dev]`
4. 复制环境变量模板：
   - `cp .env.example .env`
5. 启动本地 API：
   - `uvicorn app.main:app --reload`

## 环境变量说明
关键变量示例见 [.env.example](.env.example)。包括：
- 应用运行环境
- PostgreSQL / Redis 连接
- BUFF / metadata 基础配置
- Discord Webhook 配置
- 调度频率
- 风险过滤阈值

所有 secret 必须从 `.env` 读取，不允许硬编码。

## 如何运行测试
- `ruff check .`
- `mypy app`
- `pytest`

## 如何使用 Docker Compose 启动
1. 先准备 `.env`
2. 执行：
   - `docker compose up --build`
3. 服务包括：
   - `api`
   - `scanner`
   - `postgres`
   - `redis`

## Mock / Dry-Run 运行方式
### 运行 mock pipeline
- `python scripts/run_mock_pipeline.py`

### 运行 scheduler once
- `python scripts/run_scheduler_once.py`

### 启动 scheduler
- `python -m app.jobs.scheduler`

当前 scheduler 默认 **dry-run**：
- 不真实请求 BUFF
- 不真实发送 Discord
- 不自动购买

在接入真实 BUFF API 之前，必须先补全 [docs/BUFF_API_NOTES.md](docs/BUFF_API_NOTES.md) 中的 TODO。

## 当前骨架说明
当前阶段仅包含：
- 最小 FastAPI app
- `/health` endpoint
- 配置加载
- 数据库/调度占位结构
- 外部 client 占位模块
- metadata normalize / trade-up / EV / risk filter / mock pipeline / alert / scheduler 基础逻辑

当前阶段**不**包含：
- 真实 BUFF API mapping
- 自动购买相关能力
- 真实 Discord Webhook 发送
- 数据库持久化调度状态

## 安全说明
禁止实现：
- 自动购买
- 自动登录
- Cookie 抓取
- 验证码绕过
- BUFF 风控绕过
- 浏览器模拟购买

如果 BUFF API endpoint、签名方式、请求参数、response 字段不确定，必须写入 [docs/BUFF_API_NOTES.md](docs/BUFF_API_NOTES.md) 的 TODO，不允许编造。