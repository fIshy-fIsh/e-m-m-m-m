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
- 阶段：`PHASE_13T_COMPLETE`。
- Phase 13T production / test checkpoint：`9288794`（`add bounded multi-recipe scale validation`）。
- Post-Phase-13T handoff baseline：`bb09068`（`sync AI context after Phase 13T`）。
- 当前 Git HEAD 必须通过仓库实时验证（`git rev-parse HEAD` / `git status --short`），不在此处硬编码。
- 当前 bounded multi-recipe 校验：`tests/test_multi_recipe_scanner_scale_validation.py`。
- Minimum CI 已建立并远端验证：`.github/workflows/ci.yml`（Python 3.12；`ruff check .`；`mypy app`；`pytest`）。
- 权威交接文档：`docs/ai-context/DEVELOPMENT_HANDOFF.md`。

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