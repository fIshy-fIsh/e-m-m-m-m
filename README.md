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

### SteamDT typed errors and retry classification
- SteamDT client errors are classified into transport, HTTP status, API wrapper, rate-limit, and response-parse errors.
- Retried automatically: transport failures and HTTP 5xx, bounded by `max_retries`.
- Not retried automatically: HTTP 400 / 401 / 403 / 404 / 429, SteamDT wrapper `errorCode=4005`, other `success=false` wrapper errors, and parser/schema/Decimal conversion errors.
- Observed `errorCode=4005` means the SteamDT interface request limit was reached; stop manual smoke requests instead of retrying aggressively.
- Error text must remain redacted: no API key, no Authorization header, no full raw payload.

### SteamDT endpoint-specific in-memory limiter
- `SteamDTHttpClient` uses endpoint-specific, process-local buckets for SteamDT requests.
- Current buckets: `price_single`, `price_batch`, `price_avg`, `base`, `kline`, and `wear`.
- The limiter is fail-fast: it raises `SteamDTRateLimitError` instead of silently sleeping for a long window.
- Every real HTTP attempt consumes that endpoint's request budget, including attempts that later timeout, return HTTP 5xx, or fail parsing.
- Transport and HTTP 5xx retries still obey the endpoint budget; a retry may be blocked locally before another HTTP request is sent.
- Batch price uses the confirmed 1/min quota plus a project 5-second safety buffer.
- Avg price defaults to 10/min as an internal safety cap; 10/min is an internal safety cap, not a confirmed official SteamDT limit.
- The limiter is in-memory only. Different CLI processes do not share bucket state, so Phase 12C will handle Redis shared limiting.
- This limiter is not connected to pipeline / scheduler and does not add price cache behavior.
- It does not implement automatic buying, automatic login, browser automation, cookie scraping, captcha bypass, risk-control bypass, hidden endpoints, or any non-official evasion technique.

### SteamDT Redis shared limiter core
- `RedisSteamDTRateLimiter` provides a shared limiter core for callers that explicitly inject an already-created async Redis client.
- It does not read env, call `Redis.from_url()`, own the Redis connection, or close the injected client.
- It uses Redis Lua scripts so each acquire / server-cooldown decision is atomic across CLI, API, and scheduler processes.
- The Lua acquire path uses Redis server `TIME`, a per-endpoint sorted set, and non-sensitive UUID request members.
- Redis keys are endpoint-scoped and versioned; they do not contain API keys, Authorization headers, market hash names, Redis passwords, or full URLs.
- Redis backend failures raise `SteamDTRateLimitBackendError` and fail closed before a SteamDT HTTP request is sent.
- There is no automatic fallback to in-memory limiting; fallback must be an explicit future composition decision.
- `SteamDTHttpClient` still defaults to `InMemorySteamDTRateLimiter`; Redis limiter composition wiring is not enabled in this phase.
- This Redis limiter core is not connected to pipeline / scheduler, does not add price cache behavior, and does not run real SteamDT requests.

### SteamDT Rate Limiter Composition Factory
- `STEAMDT_RATE_LIMIT_BACKEND` selects the explicit SteamDT limiter backend for factory-created runtimes: `inmemory` by default, or `redis` when intentionally enabled.
- Direct `SteamDTHttpClient(...)` construction remains compatible and still defaults to the in-memory endpoint limiter.
- The factory/runtime layer creates `InMemorySteamDTRateLimiter` or `RedisSteamDTRateLimiter` from already-parsed settings and injects it into `SteamDTHttpClient`; the lower-level limiter/client classes do not read env.
- Redis backend reuses the normal `REDIS_URL` setting and `STEAMDT_RATE_LIMIT_REDIS_NAMESPACE` (default `steamdt-rate-limit-v1`); the Phase 12C2 test variables are only for integration tests, not formal composition.
- Redis backend never silently falls back to in-memory. Missing Redis URL, unsupported backend, or invalid namespace fail during composition.
- Factory-created Redis clients are owned by the runtime and closed by `await runtime.aclose()`; externally injected Redis clients are not closed unless explicit ownership is requested.
- This composition entrypoint is still not wired into pipeline / scheduler / FastAPI startup / price cache, and it does not call SteamDT by itself.
- SteamDT batch request control remains endpoint-specific with the existing 1/minute policy plus project safety buffer.

### Phase 12D1 Price Cache Domain and In-Memory Core
- Phase 12D1 defines an async cache protocol and an instance-local in-memory core only; it is not wired into `PriceProvider`, `ValuationService`, pipeline, scheduler, FastAPI, alerts, or any production runtime.
- The cached payload is the normalized multi-platform SteamDT candidate snapshot before selector policy is applied. Preferred-platform, liquidity, fallback, and avg-sanity policy changes therefore reuse the same observation without cache-key collisions.
- State boundaries are exact: fresh while `now < fresh_until`, stale while `fresh_until <= now < stale_until`, stale-grace while `stale_until <= now < expires_at`, and expired at `now >= expires_at`.
- Reads default to fresh-only. Stale data requires `ALLOW_STALE`; stale-grace requires the explicit `ALLOW_STALE_GRACE` policy.
- Freshness is always based on `observed_at`, never a caller-declared storage time; `InMemoryPriceCache.put()` rejects future observations and stamps `stored_at` from its injected UTC clock. Rewriting an old observation cannot make it fresh again, and an older observation cannot replace a newer one.
- The core uses immutable models, stable/versioned keys, UTC timestamps, string-preserved Decimal values, an injectable clock, and an `asyncio.Lock` without real sleeps or background tasks.
- There is currently no Redis price cache, refresh planner, background refresh, cache warming, runtime configuration, or changed SteamDT request behavior.
- The existing `price_avg=10/min` value remains a project-internal safety cap, not a confirmed official SteamDT limit.

### Phase 12D2A Redis Price Cache Codec and Atomic Core
- `RedisPriceCache` is an isolated core that receives an externally owned async Redis client; it does not read env, call `Redis.from_url()`, ping, close the client, or create a background task.
- Redis entry keys use only the explicit namespace and `PriceCacheKey.stable_digest()` in `{steamdt-price-cache-v1:<digest>}:snapshot` form. Full market names and credentials are not included in keys.
- The versioned Redis Hash codec keeps ordering/time metadata separate from deterministic candidate JSON. Decimal values remain strings, timestamps and TTLs retain microsecond precision, and provider candidate order is preserved.
- Atomic put/get/purge Lua scripts use Redis server `TIME`. Put compares observed seconds then microseconds, stamps authoritative `stored_at`, and leaves equal/older payload, storage time, and expiry unchanged.
- Physical cleanup uses absolute `PEXPIREAT` derived from the observation-based logical expiry, rounded upward to milliseconds plus a 5-second cleanup grace. That grace does not change fresh/stale/grace state.
- Get computes logical state with Redis time and atomically deletes an expired hash. During cleanup grace the first read can report `EXPIRED`; after natural Redis removal the result is a normal miss.
- Corrupt stored data raises `PriceCacheCodecError`; Redis call or response-contract failures raise `PriceCacheBackendError` and fail closed without an in-memory fallback.
- `clear()` and `purge_expired()` use paged, namespace-scoped `SCAN` plus local exact-key validation. They never use `KEYS`, `FLUSHDB`, or `FLUSHALL`; SCAN administration is not claimed to be linearizable or Redis-Cluster-global.
- Phase 12D2A uses fake Redis clients only. The Lua atomic contract has not yet been validated against real Redis; that is reserved for Phase 12D2B.
- This core is not wired into provider, selector, valuation, pipeline, scheduler, FastAPI, refresh, warming, configuration, or application lifecycle, and it does not call SteamDT.
- The existing `price_avg=10/min` value remains a project-internal safety cap, not a confirmed official SteamDT limit.

### SteamDT Redis Limiter Integration Harness
- `scripts/steamdt_redis_limiter_smoke.py` is an opt-in harness for validating the Redis limiter and Lua contract against a real test Redis server.
- It is disabled by default; it only runs when `STEAMDT_RUN_REDIS_INTEGRATION_TESTS=true` is explicitly set.
- It does not create or call `SteamDTHttpClient`, does not call SteamDT, and does not implement automatic buying or login.
- Use an isolated Redis database such as `/15` and a test namespace such as `steamdt-rate-limit-integration-v1`; do not use production Redis.
- The harness uses short test-only policies so it does not wait for official 60-second windows; these policies are not official SteamDT limits and do not change default policies.
- Cleanup uses paged `SCAN` for the exact test namespace and does not execute `FLUSHDB` or `FLUSHALL`.
- Default pytest skips the real Redis integration tests unless the same opt-in env var is set.
- Both direct and module entrypoints are supported:
  - `python scripts/steamdt_redis_limiter_smoke.py`
  - `python -m scripts.steamdt_redis_limiter_smoke`
- Manual local example without a password:
  - `STEAMDT_RUN_REDIS_INTEGRATION_TESTS=true STEAMDT_TEST_REDIS_URL=redis://localhost:6379/15 STEAMDT_TEST_REDIS_NAMESPACE=steamdt-rate-limit-integration-v1 python -m scripts.steamdt_redis_limiter_smoke`
- Redis limiter composition wiring is still not enabled for pipeline / scheduler.

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