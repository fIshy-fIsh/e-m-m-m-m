# Phase 13A Step 2M-A1 — Validation

## Required offline commands

```bash
py -3.13 -m pytest tests/test_steamdt_buff_price_policy.py
py -3.13 -m pytest tests/test_steamdt_market_data.py
py -3.13 -m pytest tests/test_price_provider.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
git diff --check
```

## Behavioral acceptance

- Only exact case-sensitive `platform == "BUFF"` is eligible.
- Exactly one BUFF record with an exact, finite, positive `Decimal` sell price returns a detached immutable result.
- No exact BUFF record and duplicate exact BUFF records fail closed with stable reasons.
- Missing, non-finite, zero, and negative sell prices fail closed; other platforms never serve as fallback.
- `bidding_price_cny` and `bidding_count` are not read, validated, compared, returned, or used as fallback.
- Gross sell price, sell count, opaque platform item ID, opaque update time, market name, and exact platform are preserved without fee or valuation arithmetic.
- Errors use one fixed redacted message and exact reason codes.
- The input aggregate is not mutated or retained.

## Architecture acceptance

- The new policy is synchronous and pure.
- It has no client, HTTP, environment, live-smoke, SteamApis, BUFF direct-integration, Redis/cache, provider/`PriceQuote`, valuation/EV/ROI/risk, fee, scheduler/background, FastAPI, Discord, Docker, or database dependency.
- The SteamDT client, aggregate service, generic selector/provider, valuation, cache/limiter, runtime, and SteamApis files remain unchanged.
- Exactly six approved paths differ, the feature-spec directory contains exactly `plan.md`, `requirements.md`, and `validation.md`, and no path is staged.

## Runtime safety

All tests and checks are offline and must observe:

```text
real SteamDT requests: 0
SteamApis connections: 0
BUFF direct requests: 0
Redis connections: 0
Discord requests: 0
PostgreSQL connections: 0
live smoke executions: 0
```

## Observed results

Validated offline on Python 3.13:

```text
tests/test_steamdt_buff_price_policy.py: 85 passed
tests/test_steamdt_market_data.py: 16 passed
tests/test_price_provider.py: 43 passed
Full pytest: 2322 passed, 23 skipped, 1 warning
Ruff: passed
Mypy app: no issues in 63 source files
git diff --check: passed
Scope audit: exactly 6 approved paths, 0 staged paths
Final HEAD: eed38f8838744ad08af85bf36c02808d8d9b6f56
```

The full suite's one warning is the established Starlette `TestClient` / `httpx` deprecation warning and is unrelated to this policy. Git emitted an LF-to-CRLF working-copy notice for the modified SteamDT notes; no whitespace error was found.

All tests and audits were offline. No live smoke ran and no real SteamDT, SteamApis, BUFF, Redis, Discord, or PostgreSQL request/connection was made. The protected client, aggregate service, provider/`PriceQuote`, valuation, recipe, cache/limiter, scheduler/runtime, SteamApis, configuration, Docker, and database paths remain unchanged. Nothing was staged, committed, or pushed, and Step 2M-A2 was not started.
