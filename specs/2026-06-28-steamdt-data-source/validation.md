# SteamDT Data Source Validation Plan

## Phase 1 Validation

当前阶段只做文档和配置，因此验证：
- `docs/STEAMDT_API_NOTES.md` exists
- `specs/2026-06-28-steamdt-data-source/plan.md` exists
- `specs/2026-06-28-steamdt-data-source/requirements.md` exists
- `specs/2026-06-28-steamdt-data-source/validation.md` exists
- `README.md` updated
- `.env.example` contains SteamDT variables
- no business code changed
- `ruff check .` still passes
- `mypy app` still passes
- `pytest` still passes
- `python scripts/run_mock_pipeline.py` still passes
- `python scripts/run_scheduler_once.py` still passes
- `python scripts/docker_smoke_test.py` still passes

### Strong Constraint
当前阶段不应新增任何 SteamDT 业务代码、client、provider、valuation 实现。

当前阶段禁止新增：
- `app/clients/steamdt_client.py`
- `SteamDTHttpClient`
- `MockSteamDTClient`
- `DryRunSteamDTClient`
- `PriceProvider` 实现
- `ValuationService` 实现

当前阶段禁止修改核心业务模块：
- `app/services/tradeup_engine.py`
- `app/services/ev_service.py`
- `app/services/risk_filter.py`
- `app/services/recipe_solver.py`
- `app/services/pipeline_service.py`
- `app/services/pipeline_alert_service.py`
- `app/clients/buff_client.py`
- `app/clients/discord_client.py`

## Future Phase 2 Validation: SteamDT Client

测试要求：
1. `SteamDTClientConfig` 正常创建
2. `dry_run=False` 且 `api_key` 缺失时报错
3. `api_key` 不在 repr 中泄露
4. `SteamDTPriceQuote` 正常创建
5. `price_cny < 0` 报错
6. `market_hash_name` 为空报错
7. `SteamDTWearInfo` float < 0 / > 1 报错
8. `SteamDTHistoricalPricePoint` timestamp 非 timezone-aware 报错
9. `MockSteamDTClient.get_price_single` 正常
10. `MockSteamDTClient.get_price_batch` 正常
11. `get_price_batch missing` 正常返回
12. `DryRunSteamDTClient` 不真实请求
13. `SteamDTHttpClient dry_run=True` 不真实请求
14. `SteamDTHttpClient endpoint` 未确认时抛 `NotImplementedError`
15. 不需要真实 `STEAMDT_API_KEY`
16. 不真实请求互联网

## Future Phase 3 Validation: PriceProvider / ValuationService

测试要求：
1. `PriceProvider` mock returns `Decimal` price
2. batch price query returns expected mapping
3. missing price handled safely
4. `ValuationService` updates `TradeupResult.estimated_price_cny`
5. probabilities unchanged
6. output_float unchanged
7. EV changes after valuation
8. Decimal precision preserved
9. no real SteamDT request

## Future Pipeline Validation

测试要求：
1. mock pipeline with SteamDT mock prices
2. output `estimated_price_cny` no longer fixed at 0
3. EV reflects output valuation
4. missing price does not crash pipeline
5. risk filter remains conservative
6. Discord alert remains dry-run
7. Scheduler remains dry-run

## Commands

每阶段都必须运行：
- `ruff check .`
- `mypy app`
- `pytest`
- `python scripts/run_mock_pipeline.py`
- `python scripts/run_scheduler_once.py`
- `python scripts/docker_smoke_test.py`
