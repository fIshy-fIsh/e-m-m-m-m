# Phase 13A Step 2F — Offline Live Recipe Valuation Validation

## Required commands

```bash
py -3.13 -m pytest tests/test_live_recipe_valuation.py
py -3.13 -m pytest tests/test_live_recipe_construction.py
py -3.13 -m pytest tests/test_valuation_service.py
py -3.13 -m pytest tests/test_ev_service.py
py -3.13 -m pytest tests/test_risk_filter.py
py -3.13 -m pytest tests/test_recipe_solver.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
git diff --name-status 45f0fd68cca7dcbeb04675af4b8b2db3a1bd0e5c
git diff --stat 45f0fd68cca7dcbeb04675af4b8b2db3a1bd0e5c
git diff --cached --name-only
git status --short
```

## Behavioral acceptance

- A synthetic already-constructed live recipe is valued through an injected deterministic provider without any reconstruction or candidate selection call.
- Every output has an aligned provider quote; zero construction placeholders are never used as fallback.
- Valuation changes only estimated output price and expected-value contribution while count, order, name, probability, float, wear, inputs, and paint seeds remain unchanged.
- Existing metrics authority receives valued outputs and configured sell fee, producing valid input cost, revenue, profit, ROI, probability, and best/worst-case fields.
- Existing risk authority receives the actual compact construction paint seeds, risk config, and liquidity score.
- A valid risk failure remains an opportunity with `passed=False`.
- Selected source-offer IDs remain exact and ordered in opportunities and rejections.
- Missing/provider/integrity failures reject the entire affected recipe and never invoke downstream metrics/risk.
- Multiple recipes are sequential and independent for business rejection; downstream orchestration failure publishes no partial result.
- Repeated evaluation is deterministic and input values/configurations remain unmodified.

## Architecture and safety acceptance

- The integration calls no solve/construction/selection/geometry function and accesses no pool, observation, URL, purchase link, external provider client, cache, limiter, environment, runtime, or background facility.
- It connects to no SteamDT, SteamApis, BUFF, Redis, Discord, PostgreSQL, WebSocket, HTTP, browser, login, purchase, scheduler, FastAPI, or Docker service.
- It reuses existing EV and risk authorities and does not duplicate formulas or risk rules.
- Fixed errors and repr-suppressed DTOs expose no names, IDs, links, prices, floats, seeds, provider payload/error text, or credentials.
- Protected legacy/core/provider modules and their fail-open behavior remain unchanged.

## Scope acceptance

Only the seven approved paths may differ from `45f0fd68cca7dcbeb04675af4b8b2db3a1bd0e5c`. Nothing may be staged. No dependency, configuration, environment, fixture, protected module, runtime integration, earlier spec, or Phase 12 strict BUFF module may change. Stop before Step 2G.

## Results

- `tests/test_live_recipe_valuation.py`: 41 passed.
- `tests/test_live_recipe_construction.py`: 25 passed.
- `tests/test_valuation_service.py`: 14 passed.
- `tests/test_ev_service.py`: 11 passed.
- `tests/test_risk_filter.py`: 13 passed.
- `tests/test_recipe_solver.py`: 59 passed.
- Full pytest: 2033 passed, 23 skipped, with one pre-existing Starlette/httpx deprecation warning.
- Ruff: all checks passed.
- Mypy: no issues in 58 source files.
- Mock pipeline, one-shot scheduler, and Docker smoke dry-runs: passed. They exercised only established synthetic/dry-run paths and made no live external connection.
- `git diff --check`: no actual whitespace error; Git emitted only Windows LF-to-CRLF working-copy warnings for the two modified tracked documentation files.
- Scope audit: exactly the seven approved paths differ from `45f0fd68`; the spec directory contains exactly `plan.md`, `requirements.md`, and `validation.md`; nothing is staged and no protected core/provider/runtime/dependency/config/env/fixture/earlier-spec path changed.
- Architecture/safety audit: the new module has exactly one metrics call and one risk call, no solve/construction/selection/geometry call, no concurrency/background work, no link access, and no SteamDT/SteamApis/BUFF/Redis/WebSocket/Discord/network/runtime import or connection.
- The branch remains `feature/steamdt-cache-rate-limit` at baseline commit `45f0fd68cca7dcbeb04675af4b8b2db3a1bd0e5c`; work is uncommitted and unpushed. Step 2G has not started.
