# Phase 13A Step 2L-PIVOT-R1 — Validation

## Required offline commands

```bash
py -3.13 -m pytest tests/test_steamdt_market_data.py
py -3.13 -m pytest tests/test_live_steamdt_market_smoke.py
py -3.13 -m pytest tests/test_steamdt_client.py
py -3.13 -m pytest tests/test_price_provider.py
py -3.13 -m pytest tests/test_valuation_service.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 -m mypy --explicit-package-bases scripts/run_live_steamdt_market_smoke.py
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
```

## Behavioral acceptance

- The aggregate service calls the existing candidate method once, retains provider order and duplicates, and returns defensive exact `SteamDTPlatformPrice` snapshots with `raw=None`.
- The service adds no duplicate platform DTO, selector, cache, valuation, listing synthesis, or external/runtime dependency.
- The CNY semantics are explicitly described and tested as a user-approved project interpretation, never as an official current SteamDT guarantee.
- Gate-off, missing-key, and missing-item paths build nothing and send zero requests.
- The enabled runtime uses one client, `max_retries=0`, one item, one service call, and exactly one single endpoint attempt.
- Empty platform data fails without retry. Nonempty data prints provider-order aggregate records only.
- Output preserves safely escaped exact platform strings and does not print IDs, requested item text, update-time values, secrets, headers, raw data, or nested errors.
- Owned resources close on every path; ordinary failures are fixed/redacted and process-control values propagate after cleanup.
- The smoke imports/calls no batch/base/avg/kline/wear, Redis/cache, provider/valuation, SteamApis/BUFF, scheduler/background, browser, or purchasing boundary.
- One offline integration validates the real parser/client/service; another validates the existing client/provider `PriceQuote.price_cny` chain under the project assumption.

## Runtime safety

All ordinary tests and dry-runs must observe:

```text
real SteamDT requests: 0
SteamApis connections: 0
BUFF requests: 0
Redis connections: 0
Discord requests: 0
PostgreSQL connections: 0
```

## Conditional live probe

Only after every offline check passes, inspect the inherited process environment without printing values. Run exactly once:

```bash
py -3.13 scripts/run_live_steamdt_market_smoke.py
```

if and only if:

- `STEAMDT_RUN_PRICE_SNAPSHOT_SMOKE` is trimmed/case-insensitive exact `true`;
- `STEAMDT_API_KEY` is nonblank;
- `STEAMDT_SMOKE_MARKET_HASH_NAME` is nonblank.

Otherwise do not connect, prompt, search, source `.env`, alter guards, or retry. Record only the missing guard category. If run, retain only the script's safe output and report possible BUFF-related platform values exactly as returned.

## Scope acceptance

- Exactly ten approved paths may change and the feature-spec directory contains exactly `plan.md`, `requirements.md`, and `validation.md`.
- `.env.example`, protected client/provider/valuation/cache/limiter/SteamApis/BUFF/runtime files, dependencies, Docker, and database files remain unchanged.
- Nothing is staged, committed, or pushed; Step 2M remains unstarted.

## Observed results

Validated offline on Python 3.13:

```text
tests/test_steamdt_market_data.py: 16 passed
tests/test_live_steamdt_market_smoke.py: 40 passed
tests/test_steamdt_client.py: 117 passed
tests/test_price_provider.py: 43 passed
tests/test_valuation_service.py: 14 passed
Full pytest: 2237 passed, 23 skipped, 1 warning
Ruff: passed
Mypy app: no issues in 62 source files
Mypy live smoke (explicit package bases): no issues in 1 source file
run_mock_pipeline.py: passed
run_scheduler_once.py: passed
scripts/docker_smoke_test.py: passed
git diff --check: no actual whitespace errors
Static/scope audit: passed; exactly 10 approved paths and 0 staged paths
```

The full suite's one warning is the established Starlette `TestClient` / `httpx` deprecation warning and is unrelated to this phase. Git emitted working-copy LF-to-CRLF notices for the three modified existing Markdown files; no whitespace error was found.

All tests, dry-runs, and audits were offline. Focused HTTP behavior used injected mock clients or local HTTPX transports and sent zero real SteamDT, SteamApis, BUFF, Redis, Discord, or PostgreSQL request/connection.

Conditional inherited guards were inspected without printing values:

```text
gate enabled: no
API key present: no
market hash name present: no
live probe executed: no
reason: opt_in_disabled
```

No credential was requested or searched, `.env` was not loaded, no guard was changed, and no real provider request was attempted.
