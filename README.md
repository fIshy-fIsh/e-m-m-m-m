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
- 当前没有真实请求 SteamDT，除非手动运行显式启用的只读 smoke / integration command。
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
- Phase 12D2A was validated with fake Redis clients only; Phase 12D2B provides the separate opt-in real Redis harness below.
- This core is not wired into provider, selector, valuation, pipeline, scheduler, FastAPI, refresh, warming, configuration, or application lifecycle, and it does not call SteamDT.
- The existing `price_avg=10/min` value remains a project-internal safety cap, not a confirmed official SteamDT limit.

### Phase 12D2B Real Redis Price Cache Integration Harness
- `scripts/steamdt_redis_price_cache_smoke.py` and `tests/test_redis_price_cache_integration.py` validate the Phase 12D2A Lua/hash contract against an explicitly selected test Redis server. They are disabled unless `STEAMDT_RUN_REDIS_PRICE_CACHE_INTEGRATION_TESTS=true`.
- The harness reads only `STEAMDT_TEST_REDIS_URL` (default `redis://localhost:6379/15`) and `STEAMDT_TEST_REDIS_PRICE_CACHE_NAMESPACE`. It never reads the formal `REDIS_URL`, production namespace, or SteamDT API key.
- Every run appends a lowercase UUID to the required `steamdt-price-cache-integration-v1` prefix. Cleanup uses paged `SCAN`, Python exact-key validation, and `DEL` only for that UUID namespace; it never uses `KEYS`, `FLUSHDB`, or `FLUSHALL`.
- Real Redis coverage includes bytes/list Lua replies, `TYPE`, flat `HGETALL`, `TIME`, absolute `PEXPIREAT`, integer SCAN cursors, cross-client visibility, microsecond ordering, equal/older preservation, logical state reads, atomic expired deletion, fail-closed wrong/corrupt types, namespace isolation, purge, pagination, and concurrent races.
- The fixture and smoke harness own and close two redis-py async clients in `finally`; `RedisPriceCache` still never owns or closes an injected client. Cleanup failure is reported without replacing the primary scenario failure.
- Both entrypoints safely skip with exit code 0 before client construction when not opted in:
  - `python scripts/steamdt_redis_price_cache_smoke.py`
  - `python -m scripts.steamdt_redis_price_cache_smoke`
- Manual local example: `STEAMDT_RUN_REDIS_PRICE_CACHE_INTEGRATION_TESTS=true STEAMDT_TEST_REDIS_URL=redis://localhost:6379/15 STEAMDT_TEST_REDIS_PRICE_CACHE_NAMESPACE=steamdt-price-cache-integration-v1 python -m scripts.steamdt_redis_price_cache_smoke`.
- This is test-only integration validation, not production cache deployment. It does not call SteamDT or wire the Phase 12D3A cache factory into provider, pipeline, scheduler, FastAPI, refresh, or background work. Namespace SCAN is not claimed to be Redis-Cluster-global.

### Phase 12D3A Price Cache Factory / Composition
- `STEAMDT_PRICE_CACHE_BACKEND` selects the explicit cache backend: `inmemory` by default, or `redis` when intentionally enabled. Redis failures never silently fall back to memory.
- The Redis backend reuses formal `REDIS_URL` and `STEAMDT_PRICE_CACHE_REDIS_NAMESPACE` (default `steamdt-price-cache-v1`). It does not read the D2B test URL/namespace and adds no production TTL environment variables.
- Composition constructs `InMemoryPriceCache` or `RedisPriceCache` without PING, EVAL, SCAN, TIME, DELETE, or a SteamDT request. redis-py client creation is lazy and Redis connectivity is not checked at construction.
- `RedisPriceCache` still never owns or closes its client. Factory-created clients are owned by `SteamDTPriceCacheRuntime`; externally injected clients remain open by default unless ownership is explicitly transferred.
- Runtime close is asynchronous, idempotent, and at-most-once even after failure. Construction cleanup preserves the primary construction error and exposes a separate cleanup error if both operations fail, while public errors omit credential-bearing exception text.
- The limiter and cache factories remain independent. A future application runtime can inject one externally owned redis-py client into both with ownership disabled, then close that shared client itself; the client must not be marked owned by both runtimes.
- Phase 12D3A uses fake Redis clients only and is not wired into `PriceProvider`, selector, `ValuationService`, pipeline, scheduler, FastAPI, refresh, warming, alerts, or production deployment.

### Phase 12D3B SteamDT Snapshot Adapter and Cache-Backed Quote Resolver
- The adapter maps every selector-dependent `SteamDTPlatformPrice` field to the immutable pre-selection `NormalizedPriceCandidate`; Decimal values never pass through float, source timestamps remain opaque `int | str | None`, and candidate order and duplicates are preserved.
- Mutable raw HTTP records are never cached. Reconstructed selector inputs use `raw=None`, so the adapter does not claim to reproduce provider payload metadata.
- The read-only resolver performs one `PriceCache.get()` and reruns the existing selector with the caller's current `SteamDTPriceSelectionConfig` on every allowed hit. Selection strategy, liquidity thresholds, fallback policy, optional already-known avg input, and any future preferred-platform policy remain outside `PriceCacheKey`.
- `MISS`, `POLICY_BLOCKED`, `EXPIRED`, and `SELECTION_FAILURE` are typed normal outcomes with no live fallback. Allowed stale and stale-grace hits retain their state, age, and `needs_refresh=true` advice but never start refresh work.
- Redis backend failures and corrupt codec records continue to fail closed; adapter invariant failures remain a separate non-sensitive error type. D3B itself invokes no cache write/administration method, refresh, Redis/HTTP client creation, env read, or background task; the existing cache `get()` contract may remove an expired entry, and injected collaborators retain responsibility for their own side effects.
- The current selector does not implement a preferred-platform option. Policy-independent cache reuse is validated with its existing strategy and liquidity controls instead of inventing a new selector setting.
- Phase 12D3B is not wired into `PriceProvider`, `ValuationService`, pipeline, scheduler, FastAPI, alerts, or production deployment. Phase 12D4A adds only the isolated single-item write core below.

### Phase 12D4A Single-Item Refresh / Write Service Core
- `SteamDTPriceSnapshotSource` is an injected selector-before source port. Existing SteamDT client/provider methods return selected quotes and do not provide the complete candidate set plus source-owned `observed_at`, so no concrete HTTP source is wired in this phase.
- `SteamDTFetchedPriceSnapshot` carries canonical item/source identity, an aware source-provided observation time, and ordered defensive candidate clones with `raw=None`. Candidate `updateTime` remains opaque and never determines snapshot freshness.
- `SteamDTPriceRefreshService.refresh_one()` builds the same D1/D3B key, converts every candidate, and calls the injected cache writer once. It never selects a quote, reads/administers the cache, retries, or falls back to live data.
- Empty candidate observations return `NO_CANDIDATES` and do not write an empty snapshot. Nonempty refreshes return `CACHE_PUT_COMPLETED` plus the exact cache result: `CREATED`, `REPLACED`, `IGNORED_OLDER`, or `UNCHANGED_EQUAL`.
- The service clock supplies only provisional incoming `stored_at`; when it lags the source observation, the observation itself is used as the minimum valid placeholder so only the backend authority decides whether it is future. In-memory cache time or Redis server `TIME` remains authoritative. Concurrent refreshes are not coalesced and the cache resolves races exclusively by `observed_at`.
- Source, adapter, backend, and codec failures remain distinct and fail closed. There is no concrete SteamDT source, Redis construction, batch refresh, planner, scheduler, background task, retry, single-flight, pipeline/FastAPI wiring, or production deployment; Phase 12D4B adds only the isolated concrete read-only source and manual smoke below.

### Phase 12D4B Concrete Read-Only Snapshot Source and Manual Smoke
- `SteamDTHttpClient.get_price_single_candidates()` exposes the existing official `/open/cs2/v1/price/single` request/parser path before selection. The selected-quote methods reuse the same helper and retain their exact original response payload for current trace behavior; normal retry, typed-error, auth, and endpoint-limiter semantics are unchanged.
- `SteamDTSinglePriceSnapshotSource` borrows that narrow candidates client, fetches once, then timestamps successful request/parse completion with an injected aware UTC clock. Candidate `updateTime` remains opaque metadata, and the D4A fetched model strips raw HTTP mappings while preserving order, duplicates, Decimal values, counts, and IDs.
- `scripts/steamdt_price_snapshot_smoke.py` is disabled unless `STEAMDT_RUN_PRICE_SNAPSHOT_SMOKE=true`. The dedicated flag is the complete opt-in for this new harness; after it is enabled, `STEAMDT_API_KEY` and `STEAMDT_SMOKE_MARKET_HASH_NAME` are required. Older SteamDT smokes retain their existing `STEAMDT_DRY_RUN=false` convention.
- The smoke composes one owned HTTP client with the existing in-memory limiter, the concrete source, `SteamDTPriceRefreshService`, one directly constructed `InMemoryPriceCache`, and `SteamDTCachedPriceResolver`. It does not import either Redis-facing factory and never connects Redis.
- The smoke sets `max_retries=0`, disables redirects, counts HTTPX outbound attempts, and runs one `refresh_one()` followed by one cached resolution. Output is an allowlisted summary only: item, candidate count, observation time, write result, cache state, selected platform/price, refresh advice, and `SteamDT requests sent: 1`; owned HTTP resources close on success and failure.
- Both disabled entrypoints are supported: `py -3.13 scripts/steamdt_price_snapshot_smoke.py` and `py -3.13 -m scripts.steamdt_price_snapshot_smoke`. A real read-only run uses `STEAMDT_RUN_PRICE_SNAPSHOT_SMOKE=true` and must be invoked manually only once after fake/default checks pass.
- D4B does not add batch refresh, cache warming, provider/pipeline/scheduler/FastAPI wiring, background work, Redis, buying, login, or any production deployment claim.

### Phase 12D5A Batch Refresh Planner, Deduplication, and Chunking Core
- `SteamDTRefreshPlanner` is a synchronous pure planning layer: it consumes an item iterable once, constructs the existing complete `PriceCacheKey` for every entry, and returns an immutable `SteamDTRefreshPlan`. It executes no refresh and calls no source, client, cache, or selector.
- Stable deduplication uses full canonical key equality and preserves the first-seen order. Surrounding item/source whitespace follows `PriceCacheKey` normalization, case remains significant, each item records its zero-based first input index and occurrence count, and plan input/unique/duplicate counts are derived from those immutable records.
- Caller-supplied `chunk_size` must be an exact positive integer. Chunks continuously partition the unique items, use zero-based chunk and unique-item indices, and defend their count, size, order, key, source, and index invariants; empty input produces a valid empty plan.
- A D5A chunk is only a local execution grouping for a future controlled D5B executor. It is not a request to SteamDT's official `POST /open/cs2/v1/price/batch` endpoint, does not imply that endpoint will be used, and encodes no official batch-size or quota limit.
- Invalid items, source, chunk size, or contradictory public model data fail closed; no invalid item is silently discarded. D5A adds no concurrency, tasks, sleep, retry, limiter logic, environment settings, HTTP/Redis access, provider/pipeline/scheduler/FastAPI wiring, or production deployment.

### Phase 12D5B Controlled Batch Refresh Executor Core
- `SteamDTRefreshExecutor` consumes only an existing, fully validated D5A plan and one explicit `PriceCachePolicy`. Because D4A `refresh_one()` constructs the default SteamDT cache key, custom-source plans fail before any work rather than silently losing their full-key identity.
- Plan chunks execute sequentially: every item in chunk 0 completes before chunk 1 starts. Inside one chunk, a fixed worker pool limits active single-item refreshes to `min(max_concurrency, chunk size)` and does not create tasks for the whole plan at once.
- `max_concurrency` is only an executor work bound. It does not throttle request rate, encode provider quota, add a token bucket, or replace the SteamDT client limiter, which remains the only authority for endpoint acquisition and retry attempts.
- Reports are immutable and always follow zero-based plan order rather than task completion order. Each item retains its plan key and indices plus the exact D4A result, so normal `NO_CANDIDATES` and `CREATED`/`REPLACED`/`IGNORED_OLDER`/`UNCHANGED_EQUAL` meanings remain auditable without reinterpretation.
- Ordinary item exceptions are isolated and retained without appearing in normal result/report repr; siblings and later chunks continue. Caller cancellation instead propagates, cancels and joins current workers, starts no later chunk, and returns no partial report or detached task. Refreshes completed before cancellation are not transactionally rolled back.
- D5B does not call SteamDT's official batch endpoint, connect real SteamDT or Redis, create or close runtimes, retry, sleep, select/resolve quotes, warm cache, or wire provider, pipeline, scheduler, FastAPI, background work, or production deployment. D5C provides the separate manual integration command below.

### Phase 12D5C Manual End-to-End Refresh Integration Command
- `scripts/steamdt_refresh_integration.py` is the first manual end-to-end SteamDT milestone, composing the real planner, controlled executor, single-item source, refresh service, one shared `InMemoryPriceCache`, and cache-backed resolver. It is not production wiring.
- Fake mode is the default, deterministic, fully offline, visibly synthetic, and needs no API key. Fake prices do not represent market values. Both forms are supported: `py -3.13 -m scripts.steamdt_refresh_integration --item "AK-47 | Redline (Field-Tested)"` and `py -3.13 scripts/steamdt_refresh_integration.py --item "AK-47 | Redline (Field-Tested)"`.
- The CLI requires one or more repeated `--item` values and accepts `--chunk-size` (default 5) and `--max-concurrency` (default 2). It passes raw names to the real planner, which alone performs canonicalization, stable deduplication, and local chunking.
- Live read-only execution requires both `--mode live` and `STEAMDT_RUN_REFRESH_INTEGRATION=true`, then a `STEAMDT_API_KEY`. Without both gates it exits 2 before creating runtime state or sending a request. This phase did not execute the enabled online path.
- Live mode reuses the existing SteamDT client runtime, endpoint limiter, retry policy, parser, and official single-price source. It uses only an in-memory cache, never Redis or the official batch endpoint, adds no command-level retry, and never falls back to fake.
- Executor `max_concurrency` bounds simultaneous refresh work; it is not a rate limiter. The existing client limiter remains authoritative for every request attempt, including retries.
- Resolution starts only after the executor returns a complete report, then follows unique plan order. `NO_CANDIDATES` is a normal successful refresh; ordinary item failures are summarized safely and cause exit 1.
- Exit codes are 0 for all refreshes completed, 1 for item/orchestration/runtime/cleanup failure, 2 for CLI/validation/live-gate errors, and 130 for `KeyboardInterrupt`. Cancellation propagates after owned-runtime cleanup and emits no partial summary.
- Output is allowlisted and control-escaped: no API key, Authorization value, Redis URL/password, raw payload, exception message, or traceback. The command is not connected to provider, valuation, pipeline, scheduler, FastAPI, Discord, BUFF, or any background worker.
- With this SteamDT integration seam established, the next product priority returns to real BUFF listing input; that work is not part of D5C.

### BUFF Listing Input Contract
- `app/services/buff_listing.py` defines only the immutable boundary from a provider observation to a normalized tradable candidate. It validates canonical listing identity, exact `Decimal` CNY price/float values, exact integer quantities/seeds, optional wear and sticker metadata, and aware UTC observation time without carrying a raw payload.
- `normalize_buff_listing()` performs validation, normalization, and field conversion only. It does not judge price, calculate EV, run trade-up logic, call SteamDT, read cache, or apply risk policy. Quantity zero remains valid contract data.
- `BuffListingSource` is only an async protocol returning observations. There is no BUFF HTTP client, live BUFF connection, API mapping, authentication, login, Cookie handling, crawler, captcha handling, seller-private data, or real listing data in this phase.
- Candidates intentionally omit sticker metadata and all provider transport data. Public validation errors use fixed field-only messages, and observation/candidate repr is disabled to avoid exposing listing or credential-shaped data.
- This input contract is not wired into provider, valuation, pipeline, scheduler, FastAPI, Redis, SteamDT, Discord, or automatic purchasing. It is not a scraper and is not production-ready.

### Phase 12E2A Offline BUFF Fixture Parser Core
- `app/services/buff_listing_parser.py` defines a strict parser for the project-owned `schema_version=1` fixture in `tests/fixtures/buff/listings_v1.json`. This synthetic contract is for offline tests and is not a BUFF official API response or a confirmed live field mapping.
- The exact v1 top level is `schema_version`, canonical `source="buff"`, one aware ISO-8601 `observed_at`, and an ordered `listings` array. `Z` and explicit offsets normalize to UTC. Breaking schema changes require a new version rather than silently changing v1.
- CNY price and optional float values must be JSON strings and convert directly to `Decimal`; JSON numbers are rejected. Exact integer quantity/paint seed rules, blank wear normalization, finite/range checks, and immutable sticker string pairs are delegated through the E1 `BuffListingObservation` boundary.
- Mapping parsing and the thin UTF-8 file loader are strict/fail-closed. Missing or unknown fields, duplicate JSON keys, malformed JSON/timestamps/Decimals/stickers, wrong types, and domain-invalid values reject the entire fixture; no malformed record is skipped and no partial tuple is returned.
- Listing order and duplicate listing IDs remain intact, as do sticker order and duplicate pairs. Quantity zero is retained, mutable input is defensively detached, and raw fixture payloads are not stored on observations. The parser does not deduplicate, filter, judge eligibility or price, compute EV/risk/trade-ups, or call another service.
- Safe parser errors use fixed public text with stable file/JSON/schema/domain classification and optional zero-based record index. Rejected values, complete payloads, paths, nested exception messages, Cookie/Authorization/token values, seller data, and URLs are never rendered.
- The older `tests/fixtures/pipeline/mock_buff_orders.json` remains a separate synthetic pipeline mock with legacy raw/seller-shaped fields; it is not copied or interpreted as this fixture schema or an official response.
- See `docs/BUFF_LISTING_NOTES.md` for the complete offline contract. There is still no live BUFF payload adapter, HTTP/auth/login/Cookie/crawler/captcha behavior, SteamDT/Redis connection, runtime wiring, or automatic purchase. This milestone is not production-ready.

### Phase 12E2B BUFF Listing Eligibility Filter Core
- `app/services/buff_listing_eligibility.py` adds a separate pure decision boundary after normalization: `BuffTradableCandidate` remains format-valid data, while `BuffListingEligibilityDecision` says whether that listing may proceed toward a future solver.
- The caller must explicitly supply exact-boolean StatTrak, Souvenir, and special-seed facts. The evaluator does not infer classifications from `market_hash_name`, `paint_seed`, wear, stickers, or listing identifiers, and no real facts provider exists yet.
- The default policy requires quantity of at least 1, a positive buy price, and a float value, while disallowing explicitly marked StatTrak, Souvenir, and special-seed listings. Policy fields are immutable, exact typed, and independent of environment or production configuration.
- Every applicable rejection is retained in deterministic order: insufficient quantity, non-positive price, missing float, StatTrak disallowed, Souvenir disallowed, then special seed disallowed. No reasons means `is_eligible=True`.
- Decisions defensively revalidate candidate, facts, policy, and the complete reason tuple. Public models are immutable and repr-suppressed, and validation errors use fixed redacted text. E1/E2A semantics remain unchanged: quantity zero, zero price, and a missing float are still format-valid input values before policy evaluation.
- This core does not call or modify the legacy scanner, recipe solver, opportunity risk filter, providers, valuation, pipeline, scheduler, FastAPI, BUFF, SteamDT, Redis, or Discord. It is not wired into runtime and is not production-ready.

### Phase 12E3A Offline BUFF Listing Facts Provider
- `app/services/buff_listing_facts.py` adds the explicit offline boundary from project-owned metadata records to the existing `BuffListingEligibilityFacts`. Records contain only canonical listing ID, canonical market name, and exact-boolean StatTrak, Souvenir, and special-seed facts; they retain no raw payload.
- `tests/fixtures/buff/listing_facts_v1.json` is a synthetic project-owned `schema_version=1` contract with exact source `buff` and ordered `records`. It is not an official BUFF response or captured live metadata. The strict mapping parser and duplicate-key-aware UTF-8 loader reject missing/unknown fields, malformed records, non-boolean flags, duplicate identities, listing-ID/name collisions, and partial success.
- `OfflineBuffListingFactsProvider` is deterministic and in-memory. A candidate receives `FOUND` only when both canonical `listing_id` and `market_hash_name` match. An absent ID or known ID with the wrong item name returns `MISSING` with `facts=None`; missing metadata never defaults to an all-false classification and wrong-name lookup never receives another item's facts.
- Classification comes only from explicit records. StatTrak/Souvenir-shaped names and `paint_seed` values are never interpreted. Provider construction and lookup defensively detach input records, facts, and queried identity, and fixed safe errors/repr do not expose listing contents or nested failures.
- There is still no real BUFF facts adapter, HTTP/auth/login/Cookie behavior, or external metadata mapping. E3A itself performs no eligibility orchestration; the isolated E3B service below is its only current caller. Nothing is wired into pipeline, solver, or runtime, this phase does not connect BUFF, SteamDT, or Redis, and it is not production-ready.

### Phase 12E3B BUFF Listing Qualification Service Core
- `app/services/buff_listing_qualification.py` adds a thin async service that composes the existing facts-provider lookup with the existing eligibility evaluator for one `BuffTradableCandidate`. It does not define another facts model, policy, reason list, or eligibility rule.
- A valid `MISSING` lookup produces the distinct derived status `MISSING_FACTS`, keeps `decision=None`, skips the evaluator, and never synthesizes all-false facts. A valid `FOUND` lookup is evaluated once and derives `QUALIFIED` when no existing reason applies or `REJECTED` with the existing canonical reasons.
- Lookup listing ID and market name must both match the queried candidate, and evaluator decisions must match the current candidate, found facts, and policy. Invalid or tampered collaborator results fail closed with fixed redacted qualification validation; provider and evaluator invocation errors propagate rather than being degraded into missing or rejection outcomes.
- Results are immutable, repr-suppressed defensive snapshots, and status is derived rather than constructor-supplied. The provider is called once and the evaluator at most once; there is no retry, fallback, name/paint-seed inference, I/O, task/thread creation, or collaborator lifecycle ownership.
- This isolated composition seam is not connected to the scanner, solver, risk filter, valuation, pipeline, scheduler, FastAPI, Discord, BUFF, SteamDT, or Redis. There is no real facts adapter, metadata fetch, batch/background qualification, automatic purchase, or production wiring.

### Phase 12E4A Manual Offline BUFF Qualification Integration
- `scripts/buff_listing_qualification_integration.py` is a manual, fully offline command that executes the real strict listing loader → normalizer → strict facts loader → `OfflineBuffListingFactsProvider` → default eligibility policy → `BuffListingQualificationService` chain. It adds no second parser, domain, facts model, policy, evaluator, or eligibility rule.
- Dedicated project-owned synthetic fixtures under `tests/fixtures/buff/qualification_*_v1.json` produce four ordered results: qualified, rejected, a duplicate identity qualified again, and missing facts. Expected counts are 4 listings, 2 qualified, 1 rejected, and 1 missing facts. Duplicates are not removed, rejection reasons remain canonical, and missing facts never become all-false facts or rejection.
- Run it with `py -3.13 -m scripts.buff_listing_qualification_integration` or `py -3.13 scripts/buff_listing_qualification_integration.py`. Both fixture paths may be overridden explicitly with `--listings-fixture` and `--facts-fixture`; defaults are repository-anchored and importing the module reads no file or environment.
- The immutable ordered run result derives all counts. Complete runs return 0 even when listings are rejected or missing facts; invalid paths/CLI return 2, processing failure returns 1 without a partial summary, and interruption returns 130. Output JSON-escapes/redacts the canonical market name and never prints listing IDs, raw payloads, paths, credentials, exception messages, or tracebacks.
- This milestone uses synthetic data only. It sends zero BUFF and SteamDT requests, does not use Redis, and is not connected to solver, valuation, pipeline, scheduler, FastAPI, Discord, or automatic purchasing. It is not a real BUFF adapter and is not production-ready.

### Phase 12E4B0 Authoritative BUFF goods_id Contract Propagation
- `BuffListingObservation` and `BuffTradableCandidate` now retain an explicitly supplied canonical `goods_id`. The value is optional only so frozen listing fixture schema v1 remains usable as `goods_id=None`; schema v2 requires a nonblank string on every listing. Neither the domain nor parser infers it from listing ID, market name, paint seed, source, hashes, or placeholders.
- `tests/fixtures/buff/listings_v2.json` and `qualification_listings_v2.json` are project-owned synthetic v2 inputs, not live BUFF payloads or confirmed response mappings. Existing v1 files are unchanged and strict: v1 rejects a `goods_id` field, while v2 requires it. Decimal, timestamp, sticker, ordering, duplicate, and fail-closed behavior is otherwise unchanged.
- Normalization, eligibility decisions, and qualification results preserve goods ID through detached snapshots. Facts records and lookups remain keyed only by listing ID plus market name, goods ID creates no eligibility reason, and `QUALIFIED`/`REJECTED`/`MISSING_FACTS` semantics are unchanged.
- The manual qualification command now defaults to v2 listings with the existing v1 facts fixture; explicit v1 listings still work. Goods ID is never printed, and market names containing it are fail-closed redacted. The future solver adapter will require `QUALIFIED` plus nonempty goods ID, but no adapter or solver execution is added here.
- This remains offline synthetic infrastructure with no BUFF, SteamDT, or Redis connection, no confirmed endpoint or field mapping, no pipeline/runtime wiring, and no production readiness.

### Phase 12E4B Qualified BUFF Listing to Solver Candidate Adapter Core
- `app/services/buff_listing_solver_adapter.py` adds one pure single-record boundary from the exact existing `BuffListingQualificationResult` to the existing solver-facing `CandidateListing`. It rebuilds the qualification snapshot through its public constructor and accepts only `QUALIFIED` results with `FOUND` facts, an eligible consistent decision, policy-satisfying quantity, a non-null float, and an explicitly supplied nonempty authoritative goods ID.
- Goods ID, listing ID, market name, Decimal CNY buy price, paint seed, and observation time map directly. Decimal price never passes through float; Decimal float is converted exactly once and checked as finite and within `[0, 1]` only because the legacy candidate contract is float-based. Source is explicitly `buff`, while inspect link and raw payload remain `None`.
- `REJECTED`, `MISSING_FACTS`, legacy-v1 null goods ID, missing float, wrong types, and tampered or inconsistent results fail closed with one fixed redacted error. Quantity is checked but not expanded, and wear, stickers, facts, policy, reasons, seller data, credentials, URLs, and transport payloads are not copied.
- The adapter does not call a facts provider, eligibility evaluator, qualification service, metadata service, market scanner, or recipe solver. Importing the required existing `CandidateListing` loads its legacy market-scanner module and `BuffClient` type dependency, but constructs no client and performs no network or authentication work. `SkinMetadata` remains responsible for StatTrak, Souvenir, collection, rarity, and item float ranges.
- This is not a live BUFF payload adapter and adds no BUFF, SteamDT, Redis, pipeline, scheduler, FastAPI, Discord, retry, background work, automatic purchase, or production wiring. Recipe solver execution remains unimplemented for this path.

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
- isolated BUFF listing observation → normalized candidate contract with optional authoritative goods ID, strict project-owned v1/v2 listing fixtures, a separate v1 facts fixture/parser, pure eligibility decision core, deterministic goods-ID-independent facts lookup, isolated single-listing qualification orchestration, a manual synthetic end-to-end qualification command, and an isolated qualified-listing-to-existing-solver-candidate adapter（无真实 BUFF 连接、payload mapping、recipe solver execution 或 runtime wiring）

当前阶段**不**包含：
- 真实 BUFF API mapping、client、scraper 或 listing data
- SteamDT production wiring（只提供显式启用的只读 manual integration）
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