# CS2 BUFF Trade-up Opportunity Scanner

## 项目目标
构建一个后端优先、可 24h 无人值守运行的 CS2 BUFF trade-up opportunity scanner。V1 只负责扫描、归一化、计算、过滤和 Discord Webhook 提醒，不执行任何交易动作。

## 技术栈
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

## 开发规则
1. 先遵循 `specs/mission.md`、`specs/tech-stack.md`、`specs/roadmap.md`、feature specs、`docs/SPEC.md`、`docs/BUFF_API_NOTES.md`。
2. V1 只做项目骨架、扫描分析链路和提醒链路，不做交易执行。
3. 所有外部 API client 必须具备：
   - timeout
   - retry
   - rate limit
   - 错误分类
   - 响应校验
4. BUFF API endpoint、签名方式、request 参数、response 字段不确定时，必须写入 `docs/BUFF_API_NOTES.md` 的 TODO，不允许编造。
5. 所有核心 trade-up、float、EV、probability 计算必须有单元测试。
6. 业务逻辑必须与外部 provider 字段解耦；先 normalize，再进入 engine/service。
7. 代码优先可测试、可复算、可追踪。

## 安全规则
1. 不允许实现自动购买。
2. 不允许实现自动登录。
3. 不允许 Cookie 抓取。
4. 不允许验证码绕过。
5. 不允许 BUFF 风控绕过。
6. 不允许浏览器模拟购买。
7. 不允许硬编码 API key、cookie、token、Discord Webhook URL、Steam credentials、BUFF credentials。
8. 所有 secret 必须从 `.env` 读取。
9. 日志中不得打印 secret、token、cookie 或 webhook URL。
10. 若外部接口细节未确认，保留 TODO，不得猜测实现。

## 测试命令
- `ruff check .`
- `mypy app`
- `pytest`

## 代码风格
1. 使用类型标注。
2. 模块职责单一，目录边界清晰。
3. 保持 FastAPI / service / client / repository 分层。
4. 避免把外部 API 原始字段直接传播到核心域模型。
5. 配置集中管理，禁止散落读取环境变量。
6. 优先编写最小可运行代码和明确的占位实现。

## 每次完成任务后的验证流程
1. 运行 `ruff check .`
2. 运行 `mypy app`
3. 运行 `pytest`
4. 如涉及 API 或调度入口，验证最小启动路径可工作。
5. 检查是否违反本文件安全规则与禁止事项。
6. 检查是否把未确认的 BUFF API 细节错误写死进代码。

## 当前阶段指针
- 阶段：`PHASE_14C_COMPLETE`（scanner service/session 已实现 Phase12D FRESH_ONLY cache READ；default CLI composition 与 scanner write-after-live 尚未实现；分支 `feature/scanner-valuation-integration`）。
- Phase 14C production / test checkpoint：本分支 commit `add scanner fresh-only price cache reads`（完成后通过 `git rev-parse HEAD` 实时确认）；新增 strict-BUFF cached selector 与 scanner-owned resolver wrapper，将 optional cache-reader dependency 接入 Stage A；全套验证 `3413 passed, 23 skipped, 1 warning`。
- Post-Phase-13T handoff baseline：`bb09068`（`sync AI context after Phase 13T`）。
- Pre-R0-C DEV tip (historical)：`4c2f1ef`（`sync docs after minimum CI validation`）。
- Post-R0-C canonical main：`9cfaf36`（`sync docs after R0-C repository consolidation`），parents `{24ece858, 3aa44e93}`，tree `7a39d28`。作为祖先节点保留；当前 canonical main 已迁移到下方 P3。
- Post-R0-C docs checkpoint：`b13201b`（`sync docs after R0-C repository consolidation` docs PR，PR #2），merge commit 在 P2。
- 当前 canonical main：`P3 = 24c95c029f583d5cc0b0a67986e48c06d0ef7957`，parents `{328269112f229faf3fce4cf0be4b9c7875582b65, 6964cc4ff25cd4ad72fe65f92f40a5ce70a4a268}`，tree `608d3e47...`。R0-D 完成 docs checkpoint PR (#3) 已合并至 main；P2 = 328269112... 现为 P3 祖先节点保留。
- 当前 Git HEAD 必须通过仓库实时验证（`git rev-parse HEAD` / `git status --short`），不在此处硬编码。
- 当前 bounded multi-recipe 校验：`tests/test_multi_recipe_scanner_scale_validation.py`。
- Minimum CI 已建立并远端验证：`.github/workflows/ci.yml`（Python 3.12；`ruff check .`；`mypy app`；`pytest`）；CI workflow blob 自 R0-A 起保持 `02d0ce81...`。
- 权威交接文档：`docs/ai-context/DEVELOPMENT_HANDOFF.md`。
- R0-A / R0-B / R0-C / R0-C docs checkpoint / R0-D：COMPLETE。R0-D 由 PR #3 完成 docs checkpoint 合并与 CI green（run 33240760167）验证。
- Phase 14A：COMPLETE — design freeze。`specs/2026-08-29-scanner-valuation-integration-design-freeze/{requirements,plan,validation}.md`；commit `e98cd97`。Phase 14A-R1 coherence correction：COMPLETE，commit `bb056e5`，decision `D-PHASE14A-R1-COHERENCE`。
- Phase 14B：COMPLETE — run-scoped exact-name valuation reuse。每次 `LiveScannerOrchestrator.run_once()` 创建新的 scanner-owned session；async Stage A prepare 零 provider calls；atomic admission 后 Stage B 仅请求 NEW LIVE exact names；success 与 terminal failure 在同一 run 内复用；跨 run 不复用。`max_valuation_requests_per_run` runtime 含义迁移为 NEW LIVE exact-name demand；legacy logical counters 保持；new additive counters active；cache counters 在 14B 中保持零。`ValuationService` formula 未修改。
- `D-CACHE-001` 仍为 Active broader migration record：14B 已迁移 run-scoped reuse；14C 已迁移 scanner service/session FRESH_ONLY persistent cache READ；default `run_live_scan_once.py` runtime composition 仍待 14D。scanner write-after-live 仍 NOT IMPLEMENTED。
- Phase 14C：COMPLETE — optional cache-reader injection；scanner-owned wrapper 内部固定构造 `SteamDTCachedPriceResolver(selector=select_scanner_cached_buff_price)`；Stage A 严格 memo → FRESH_ONLY cache → live classification；cached selector 复用 `select_buff_output_price`，generic cross-platform resolver 无法进入 public scanner composition；无 stale consumption、无 cache write、无 refresh service。snapshot 的 stored `PriceCachePolicy` 由 writer 管理，无 scanner read-time numeric TTL config。
- Phase 14D：NEXT / NOT STARTED / NOT AUTHORIZED（default one-shot CLI cache composition + scale / bounded-live validation）。
- `main` 未被 Phase 14A 推送修改；HEAD 当前在 `feature/scanner-valuation-integration`，需通过 `git rev-parse HEAD` 实时确认。

## 禁止事项
- 自动购买
- 自动登录
- Cookie 抓取
- 验证码绕过
- BUFF 风控绕过
- 浏览器模拟购买
- 非官方反检测/规避风控能力
- 硬编码 secrets
- 编造 BUFF endpoint / 签名 / 参数 / 字段 mapping
- 在未补足单元测试前提交核心计算逻辑