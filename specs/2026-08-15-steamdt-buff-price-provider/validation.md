# Phase 13A Step 2M-A2 — Validation

## Required offline commands

```bash
py -3.13 -m pytest tests/test_steamdt_buff_price_provider.py
py -3.13 -m pytest tests/test_steamdt_buff_price_policy.py
py -3.13 -m pytest tests/test_steamdt_market_data.py
py -3.13 -m pytest tests/test_price_provider.py
py -3.13 -m pytest tests/test_valuation_service.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
git diff --check
```

## Behavioral acceptance

- `SteamDTBuffPriceProvider` structurally supplies the existing two async `PriceProvider` methods without changing generic contracts.
- Single lookup composes the existing aggregate helper and exact BUFF policy once each, then returns an aligned `PriceQuote` with fixed source `steamdt:buff` and `raw=None`.
- The adapter contains no platform or sell-price policy and never reads bidding data or falls back to another platform.
- Batch names are stripped, blanks dropped, and canonical duplicates stably collapsed before sequential one-call-per-name composition.
- Successful quote keys/names preserve canonical input alignment and order.
- Ordinary failed items produce no quote, append aligned missing/error entries with fixed redacted codes, and do not block later items.
- Process-control failures propagate without a partial result or later calls.

## Architecture acceptance

- The provider borrows only `SteamDTMarketDataClient` and owns no runtime resource.
- It has no concrete client, HTTP/network, env/key, retry, sleep, batch endpoint, task/concurrency, cache/Redis/limiter, SteamApis, direct BUFF integration, valuation/EV/ROI/risk, fee, listing/purchase, scheduler, FastAPI, Discord, Docker, or database path.
- Protected client, aggregate, A1 policy, generic provider/contracts, valuation, recipe, cache/runtime, and existing tests remain unchanged.
- Exactly six approved paths differ, the feature-spec directory contains exactly `plan.md`, `requirements.md`, and `validation.md`, and no path is staged.

## Runtime safety

All tests and checks are fake-only/offline and must observe:

```text
real SteamDT requests: 0
SteamApis connections: 0
BUFF direct requests: 0
Redis connections: 0
Discord requests: 0
PostgreSQL connections: 0
live smoke executions: 0
ValuationService runtime calls: 0
```

## Observed results

Validated offline on Python 3.13:

```text
tests/test_steamdt_buff_price_provider.py: 47 passed
tests/test_steamdt_buff_price_policy.py: 85 passed
tests/test_steamdt_market_data.py: 16 passed
tests/test_price_provider.py: 43 passed
tests/test_valuation_service.py: 14 passed
Full pytest: 2369 passed, 23 skipped, 1 warning
Ruff: passed
Mypy app: no issues in 64 source files
git diff --check: passed
Scope audit: exactly 6 approved paths, 0 staged paths
Final HEAD: 2c01c46c90e85308c44781a10e88ceeb6ad645f5
```

The full suite's one warning is the established Starlette `TestClient` / `httpx` deprecation warning and is unrelated to this adapter. Git emitted an LF-to-CRLF working-copy notice for the modified SteamDT notes; no whitespace error was found.

All tests and audits were fake-only/offline. No live smoke ran and no real SteamDT, SteamApis, BUFF, Redis, Discord, or PostgreSQL request/connection was made. `ValuationService`, live recipe valuation, EV, ROI, and risk were not invoked as runtime composition. The protected client, aggregate service, A1 policy, generic provider/contracts, valuation, recipe, cache/limiter, scheduler/runtime, SteamApis, configuration, Docker, and database paths remain unchanged. Nothing was staged, committed, or pushed, and Step 2M-A3 was not started.
