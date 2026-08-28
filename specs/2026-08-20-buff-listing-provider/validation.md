# Phase 13C — Validation

## Required offline commands

```bash
py -3.13 -m pytest \
  tests/test_buff_anonymous_listing_client.py \
  tests/test_buff_listing_provider.py \
  tests/test_live_buff_anonymous_sell_order_schema_smoke.py \
  tests/test_live_buff_listing_provider_smoke.py
py -3.13 -m pytest tests/test_buff_listing.py tests/test_buff_listing_parser.py
py -3.13 -m pytest tests/test_buff_listing_qualification.py tests/test_buff_listing_solver_adapter.py
py -3.13 -m pytest tests/test_market_scan_service.py tests/test_recipe_solver.py
py -3.13 -m pytest tests/test_steamdt_buff_live_recipe_valuation.py tests/test_live_recipe_valuation.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 -m mypy scripts/buff_listing_smoke_utils.py
py -3.13 -m mypy scripts/run_live_buff_anonymous_sell_order_schema_smoke.py
py -3.13 -m mypy scripts/run_live_buff_listing_provider_smoke.py
git diff --check
git diff --name-only
git diff --stat
git diff --cached --name-only
git status --short
```

## Acceptance

- Shared client is the only anonymous sell-order HTTP authority and sends one exact request per provider call.
- Strict parser maps every valid item into immutable provider DTOs, preserves order, maps missing seed to `None`, and rejects any invalid item atomically.
- Market name remains `None`; asset ID is required; request-context goods ID and fixed source are preserved.
- Provider borrows its client, owns no lifecycle, and calls client/parser exactly once.
- Both smoke scripts use the shared runtime and provider, remain disabled, anonymous, redacted, one-request, and offline during validation.
- Existing pipeline, Phase 12, SteamDT valuation, SteamApis, solver, EV/risk, scheduler, and default application behavior remain unchanged.
- Exactly one final commit follows baseline `04ba133`; working tree is clean and no push occurs.

## Runtime safety

```text
real BUFF requests: 0
live BUFF smoke executions: 0
SteamDT requests: 0
SteamApis connections: 0
Redis/Discord/PostgreSQL connections: 0
pipeline/scheduler/background executions: 0
login/session/Cookie actions: 0
purchase/market-write actions: 0
```

## Observed results

Validated entirely offline on Python 3.13:

```text
Focused client/provider/schema-smoke/provider-smoke: 203 passed
Adjacent BUFF/solver/SteamDT valuation regressions: 412 passed
Full pytest: 2769 passed, 23 skipped, 1 warning
Ruff: passed
Mypy app: no issues in 68 source files
Mypy shared smoke utility: no issues in 1 source file
Mypy historical schema smoke: no issues in 1 source file
Mypy provider smoke: no issues in 1 source file
git diff --check: passed
```

The full-suite warning is the existing Starlette TestClient / HTTPX deprecation warning and is unrelated to Phase 13C. Automated validation used synthetic fixtures, fake clients/runtimes, and local HTTPX transports only. Real BUFF/SteamDT requests, live-smoke executions, SteamApis connections, Redis/Discord/PostgreSQL connections, pipeline/scheduler/background work, login/session/Cookie actions, and purchase/market writes were all zero.
