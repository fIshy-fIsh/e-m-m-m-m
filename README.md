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
   - `scheduler`
   - `postgres`
   - `redis`

## Mock / Dry-Run 运行方式
### 运行 mock pipeline
- `python scripts/run_mock_pipeline.py`

### 运行 scheduler once
- `python scripts/run_scheduler_once.py`

### 运行 Docker smoke test
- `python scripts/docker_smoke_test.py`

### 启动 scheduler
- `python -m app.jobs.scheduler`

当前 scheduler 默认 **dry-run**：
- 不真实请求 BUFF
- 不真实发送 Discord
- 不自动购买

在接入真实 BUFF API 之前，必须先补全 [docs/BUFF_API_NOTES.md](docs/BUFF_API_NOTES.md) 中的 TODO。

## Planned V1.1: SteamDT Data Source

- SteamDT 将作为估值和历史价格数据源。
- SteamDT 不替代 BUFF listing scanner。
- BUFF 仍负责可购买 listing / material scanning。
- SteamDT 主要用于 output price estimation / historical sanity check / metadata fallback / wear support。
- 当前仍处于设计与受控 dry-run 阶段。
- 当前没有真实请求 SteamDT，除非手动运行官方 smoke script 并显式设置 `STEAMDT_DRY_RUN=false`。
- `STEAMDT_API_KEY` 不应 commit。
- 后续将在 `feature/steamdt-data-source` 分支开发。
- 当前 V1 dry-run baseline 可通过 `v1-dry-run-baseline` tag 回滚。

### SteamDT official read-only smoke scripts
- Single price:
  - 推荐：`python -m scripts.steamdt_price_single_smoke`
  - 也支持：`python scripts/steamdt_price_single_smoke.py`
- Batch price:
  - 推荐：`python -m scripts.steamdt_price_batch_smoke`
  - 也支持：`python scripts/steamdt_price_batch_smoke.py`
- Avg price:
  - 推荐：`python -m scripts.steamdt_avg_price_smoke`
  - 也支持：`python scripts/steamdt_avg_price_smoke.py`
- 当前 smoke request 的价格选择策略已升级为 liquidity-aware，但默认仍然不会真实请求 SteamDT。
- Single / batch smoke 可选启用 avg sanity check，默认关闭。
- 启用后会额外调用 avg endpoint。
- `avg` 只用于 sanity check，不替代 sellPrice valuation。
- 必须手动设置：
  - `STEAMDT_DRY_RUN=false`
  - `STEAMDT_API_KEY`
  - `STEAMDT_SMOKE_MARKET_HASH_NAME`（single / avg）
  - `STEAMDT_SMOKE_MARKET_HASH_NAMES`（batch）
- API key 不要提交到 git。
- 这些 smoke script 不会接入 pipeline / scheduler / alerts。

### SteamDT Manual Smoke Scripts

所有 SteamDT manual smoke scripts 默认不会请求；必须显式设置 `STEAMDT_DRY_RUN=false` 和 `STEAMDT_API_KEY` 才允许官方只读请求。推荐使用 module 方式运行（例如 `python -m scripts.steamdt_price_single_smoke`）；直接文件执行（例如 `python scripts/steamdt_price_single_smoke.py`）也已支持。

1. `scripts/steamdt_price_single_smoke.py`
   - 用途：验证 single price endpoint 和 selector。
   - 需要：`STEAMDT_SMOKE_MARKET_HASH_NAME`。
   - 可选：`STEAMDT_ENABLE_AVG_SANITY_CHECK` / `STEAMDT_MAX_PRICE_TO_AVG_RATIO`。
2. `scripts/steamdt_price_batch_smoke.py`
   - 用途：验证 batch price endpoint 和 selector。
   - 需要：`STEAMDT_SMOKE_MARKET_HASH_NAMES`，逗号分隔，最多 10 个。
   - 可选：`STEAMDT_ENABLE_AVG_SANITY_CHECK` / `STEAMDT_MAX_PRICE_TO_AVG_RATIO`。
3. `scripts/steamdt_avg_price_smoke.py`
   - 用途：验证 avg price endpoint。
   - 需要：`STEAMDT_SMOKE_MARKET_HASH_NAME`。
4. `scripts/steamdt_provider_price_smoke.py`
   - 用途：验证 `SteamDTPriceProvider` + injected `SteamDTHttpClient` flow。
   - 支持 single / batch mode（`STEAMDT_PROVIDER_BATCH_MODE`）。
   - 支持 optional avg sanity check。

安全边界：这些脚本不接入 pipeline / scheduler / alerts，不自动购买，不自动登录，不提交 API key，不使用 non-official evasion techniques，不做 cookie scraping / browser automation / captcha bypass / risk-control bypass / hidden endpoints。

### SteamDT PriceProvider integration
- `SteamDTPriceProvider` 支持注入 selector config，用于 liquidity-aware selection。
- provider 层可以可选启用 avg sanity check，但默认关闭。
- 默认不会额外请求 avg endpoint。
- provider 不读取 env，也不创建真实 SteamDT HTTP client；只使用调用方注入的 client。
- avg price 只作为 sanity check input，不直接替代 sellPrice valuation。
- 当前 provider integration 不接入 pipeline / scheduler / alerts。
- SteamDTPriceProvider manual smoke:
  - 推荐：`python -m scripts.steamdt_provider_price_smoke`
  - 也支持：`python scripts/steamdt_provider_price_smoke.py`
- Provider smoke 默认不会请求 SteamDT；必须显式设置 `STEAMDT_DRY_RUN=false` 和 `STEAMDT_API_KEY`。
- Provider smoke 支持 single / batch mode（`STEAMDT_PROVIDER_BATCH_MODE`）和 optional avg sanity check。
- Provider smoke 只组合 injected `SteamDTHttpClient` + `SteamDTPriceProvider`，不接入 pipeline / scheduler / alerts。
- API key 不要提交到 git。

## Docker dry-run
1. `cp .env.example .env`
2. `docker compose build`
3. `docker compose up scheduler`
4. `docker compose up api`
5. `curl http://localhost:8000/health`

## Safety guarantees in V1
- `DRY_RUN=true` by default
- no real BUFF API requests
- no real Discord sending
- no auto-buying
- no login automation
- no cookie scraping
- no captcha bypass
- no browser automation

## Before enabling real BUFF / Discord
- complete [docs/BUFF_API_NOTES.md](docs/BUFF_API_NOTES.md) TODOs
- confirm official endpoint / auth / fields
- set `DRY_RUN=false` only after review
- never commit `.env`

## Current skeleton status
当前阶段已具备：
- metadata normalize / trade-up / EV / risk filter
- mock pipeline / alert / scheduler
- Docker / 24h dry-run deployment hardening

当前阶段**不**包含：
- 真实 BUFF API mapping
- 真实 SteamDT integration implementation
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