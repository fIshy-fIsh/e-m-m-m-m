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
- 阶段：`PHASE_16F_RECIPE_FIRST_BUFF_INTERFACE_VALIDATED`（one bounded read-only recipe-first BUFF interface validation；分支 `feature/recipe-first-live-buff-interface-validation` from Phase 16E `f67d500c`；Phase 16G NOT STARTED / NOT AUTHORIZED）。
- Phase 16F implemented：frozen case DTO `LiveValidationCase` + canonical UTF-8 JSON outside-Git serialization；`LiveValidationRunner` reusing existing `BuffAnonymousListingHttpClient` + `BuffListingProvider` + `ExistingRecipeFirstAcquisitionPipeline`；`attempted` budget enforced before HTTP dispatch；sequential at most `hard_request_count <= 10` page-1/default-sort GET requests；2-second minimum pacing；redacted `LiveValidationRunResult` excludes raw payload, listing_id, asset_id, paintwear, secret, webhook data；classification=`validated` from one live attempt against goods_id `33960` (`AK-47 | Redline (Field-Tested)`)；10 listings identity-resolved/intrinsic-resolved/candidate-accepted/metadata-resolved；ZERO SteamDT；ZERO Discord；ZERO Redis；ZERO PostgreSQL mutation；ZERO scheduler；ZERO production-default switch。
- Phase 16F boundary：production recipe-first remains OFF；`LiveScannerOrchestrator` and `scripts/run_live_scan_once.py` byte-deterministic unchanged；legacy goods-first path remains the production default；`D-TRADEUP-WEAR-ROW-MIGRATION-001` remains deferred；single live attempt is the bounded evidence, no replay, no additional live runs authorized by Phase 16F。
- Phase 16E implemented：family-count-preserving bounded enumerator reusing `RecipeEnumerationConfig(2,256)`；new `ConcreteFamilyTradeupResults` from Phase 16B finish geometry + canonical float/wear helpers bypassing the legacy wear-row bug；opt-in offline orchestrator with `enabled=False` default；existing acquisition/enrichment/identity/intrinsic stages composed via `ExistingRecipeFirstAcquisitionPipeline`；`RunScopedValuationSession` + `ValuationService` + `calculate_opportunity_metrics` + `evaluate_opportunity` reused unchanged；ZERO BUFF/SteamDT HTTP / zero production caller imports.
- Phase 16E reconciliation：legacy `LiveScannerOrchestrator` and `scripts/run_live_scan_once.py` byte-deterministic unchanged；`D-TRADEUP-WEAR-ROW-MIGRATION-001` remains deferred for the goods-first path; the new recipe-first path uses Phase 16B finish-level structural geometry so it never inherits the wear-row cardinality bug.
- Phase 16D implemented：immutable exact-name strict-BUFF price book；exact per-input pinned identity/goods_id/adjusted-float evidence；Decimal/Fraction optimistic/base/conservative economics with explicit fee；deterministic seven-key streaming Top-2；exact candidate order and <=10 targeted slot allocation；one active family / pre-live fallback only；zero production callers / zero live HTTP。
- Phase 16D reconciliation：SteamDT `update_time: int | str | None` remains opaque diagnostics only（NOT parsed/chronologically compared/ranked/freshness proof；`D-PRESCREEN-TIMESTAMP-NONAUTHORITY-001`）；Phase 16C exact interval-union/reachable finish-wear evidence is gate + structured evidence，NOT `static_float_margin_vs_threshold` scalar。
- Final valuation remains existing single strict-BUFF path；defaults 5/60、enumeration 2/256、cache/session/risk/EV、`D-TRADEUP-WEAR-ROW-MIGRATION-001` unchanged。
- Phase 16B implemented：immutable `StructuralOutputFinishIndex`、`RecipeFamily` exact eligibility/identity、analytic counts、lazy deterministic generation、`RecipeFamilyGeometry` exact Fraction finish-level probability；authoritative C=`38/44/86/44/76/44/63/44`, K<=3 total `9,972,412`; 45 focused tests, full 3482 passed；zero current production callers。
- `D-TRADEUP-WEAR-ROW-MIGRATION-001` remains UNCHANGED / DEFERRED；scanner remains goods-first；default 5 / hard max 60 / enumeration 2/256 unchanged。
- Phase 16A-R1 corrections：Souvenir is NOT a `RecipeFamily` structural identity axis (StatTrak IS); Top-N ranking does NOT multiply live BUFF request budget (one active family per run, fallback only before any BUFF request starts, `<= MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10`); 9,972,412 K<=3 theoretical family states are analytic evidence, NOT an eager-materialization requirement (lazy deterministic generation, streaming top-K ranking, dedupe-before-batch).
- Phase 16A-R3 evidence：authoritative exact-identity + valid-next-rarity-output-finish gates yield eligible C=`38/44/86/44/76/44/63/44`, K<=3 counts=`310061/485342/3717221/485342/2556526/485342/1447236/485342`, total `9,972,412`; prior metadata-only C=`38/46/91/44/91/45/78/44` and written `13,947,034` are superseded historical evidence (line items actually sum `13,943,034`)；decision `D-RECIPE-FIRST-EVIDENCE-RECONCILIATION-001`。
- Phase 16A-R2 corrections：`StructuralOutputFinish` (finish-level) 作为 collection output pool membership / 结构性概率 / 几何 / 去重 的 structural identity；exact market valuation identity (canonical non-Souvenir `market_hash_name`) fail-closed 从 pinned finish + wear metadata 在 output float 决定后解析；`represented_outputs` 替换为 `represented_output_finishes`；结构性概率按 unique finish count 计算 `(collection_count/10)/unique_finish_count_in_collection`，概率和必须等于 1；现 production `tradeup_engine.calculate_tradeup_results` 按 wear-qualified row 拆概率（recorded as `D-TRADEUP-WEAR-ROW-MIGRATION-001`），Phase 16B 不得静默 reuse；6-tuple `(collection_name, rarity, stattrak, name, weapon, paint_index)` 对 pinned snapshot 是 collision-free（16868 wear rows -> 2148 distinct finish keys）。
- Phase 16A-R1 frozen V1 project bounds (NOT external API limits)：`MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3`、`TOP_RANKED_FAMILIES = 2`、`MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10`、`PRESCREEN_BATCH_CHUNK_SIZE = 10` (internal project transport chunk; NOT a confirmed SteamDT limit).
- Pre-screen / final separation：SteamDT batch pre-screen is approximate ranking/pruning only；strict BUFF sellPrice selector（case-sensitive `platform == "BUFF"`, positive finite `sellPrice`, single BUFF record per name；missing/unusable BUFF → FAIL_CLOSED）；NEVER `biddingPrice` / second-platform / lowest-across-platforms；pre-screen NEVER produces `LiveOpportunity`、NEVER passes `RiskFilterConfig`、uses separate `RecipeFamilyPreScreenEconomics` DTO distinct from `OpportunityMetrics`.
- Phase 16A + 16A-R1 + 16A-R2 decisions appended：`D-RECIPE-FIRST-001`, `D-PRESCREEN-VALUATION-001`, `D-PRESCREEN-FLOAT-001`, `D-TARGETED-BUFF-001`, `D-PHASE15C3-DEFER-001`, `D-RECIPE-FIRST-SOUVENIR-IDENTITY-001`, `D-TARGETED-BUFF-BUDGET-001`, `D-RECIPE-FIRST-ENUMERATION-001`, `D-RECIPE-FIRST-OUTPUT-IDENTITY-001`, `D-RECIPE-FIRST-PROBABILITY-001`, `D-OUTPUT-WEAR-MAPPING-001`, `D-TRADEUP-WEAR-ROW-MIGRATION-001`。
- Phase 15B decision remains controlling：`NO_PRODUCTION_DEFAULT_CHANGE_PENDING_REPRESENTATIVE_SNAPSHOT`；production default 保持 `5`；`HARD_MAX_60_REVIEW_DEFERRED`；hard max 保持 `60`。Phase 15A designed replay quantiles/threshold shares 是 structural coverage evidence，不是 production-run probability distribution。
- Phase 15B artifact：`research/valuation_budget_calibration/POLICY_DECISION.md`；下一 numeric policy gate 需要 separately authorized representative read-only listing-snapshot calibration。
- Phase 15A evidence：`research/valuation_budget_calibration/` 使用规范化 pinned identity/metadata snapshots，经 current COHORT_DEPTH universe builder + real scanner composition/recipe solver/trade-up output construction，固定 default enumeration `2 / 256`；192 个 deterministic replay observations；结构 census 439 records；报告 `results.json` / `REPORT.md`；没有生产 budget/default/hard-max/CLI/atomic semantics 变化。
- Phase 15A checkpoint：`df621d4de162080293553874f7b374a58bc4e6be`（`measure scanner valuation output cardinality`）；branch CI run `33325598811` / job `quality` SUCCESS。
- Phase 15A/15B production diff：empty；仅 research harness/artifacts、focused calibration tests 和最小 docs/policy checkpoint。
- Post-Phase-13T handoff baseline：`bb09068`（`sync AI context after Phase 13T`）。
- Pre-R0-C DEV tip (historical)：`4c2f1ef`（`sync docs after minimum CI validation`）。
- Post-R0-C canonical main：`9cfaf36`（`sync docs after R0-C repository consolidation`），parents `{24ece858, 3aa44e93}`，tree `7a39d28`。作为祖先节点保留；当前 canonical main 已迁移。
- Post-R0-C docs checkpoint：`b13201b`（`sync docs after R0-C repository consolidation` docs PR，PR #2）。
- Phase 14 canonical integration main：`P4 = 26c69bae9e482452f56f380277d8b10fefa29d52`，parents `{24c95c029f583d5cc0b0a67986e48c06d0ef7957, 47227b33cd088a0961320254dd6c0de75e3564bb}`，tree `39a82914fa53fd414d141fbb87cbf197c1ff2c19`；PR #4 merged；main CI run `33320657978` SUCCESS。
- 当前 canonical main（Phase 14 docs checkpoint PR #5 merged）：`215c91c46a6d95de793649a87bccceb3a24a42d3`，parents `{26c69bae9e482452f56f380277d8b10fefa29d52, fc5144f2b27815eff167995314156c8288276aa2}`，tree `ca11f054978b4133e1ea95b51ba70b3bda419e5b`；main CI run `33321890478` SUCCESS。
- 当前 Git HEAD 必须通过仓库实时验证（`git rev-parse HEAD` / `git status --short`），不在此处硬编码。
- 当前 bounded multi-recipe 校验：`tests/test_multi_recipe_scanner_scale_validation.py`。
- Minimum CI 已建立并远端验证：`.github/workflows/ci.yml`（Python 3.12；`ruff check .`；`mypy app`；`pytest`）；CI workflow blob 自 R0-A 起保持 `02d0ce81...`。
- 权威交接文档：`docs/ai-context/DEVELOPMENT_HANDOFF.md`。
- R0-A / R0-B / R0-C / R0-C docs checkpoint / R0-D：COMPLETE。R0-D 由 PR #3 完成 docs checkpoint 合并与 CI green（run 33240760167）验证。
- Phase 14：CANONICAL MAIN INTEGRATION COMPLETE — Phase 14A / 14A-R1 / 14B / 14C / 14D 通过 PR #4 合并到 main。Phase 14 集成包括：run-scoped exact-name reuse；NEW LIVE request-budget accounting；FRESH_ONLY Phase 12D scanner cache reads；strict BUFF cached selection；default one-shot CLI cache composition（inmemory default，可选 Redis）；无 scanner write-after-live、无 refresh/scheduler/TTL env config。
- Phase 15B：POLICY FREEZE COMPLETE；default `5` 与 hard max `60` 均 unchanged；代表性 read-only snapshot calibration 未单独授权，任何 numeric policy implementation 仍 NOT AUTHORIZED。

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