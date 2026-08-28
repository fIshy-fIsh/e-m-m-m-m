# Phase 13A Step 2M-A5 — Validation

## Required offline commands

```bash
py -3.13 -m pytest tests/test_live_steamdt_buff_live_recipe_valuation_smoke.py
py -3.13 -m pytest tests/test_steamdt_buff_live_recipe_fixture.py
py -3.13 -m pytest tests/test_steamdt_buff_live_recipe_valuation.py
py -3.13 -m pytest tests/test_live_recipe_valuation.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 -m mypy scripts/run_live_steamdt_buff_live_recipe_valuation_smoke.py
git diff --check
git diff --name-only
git diff --stat
git diff --cached --name-only
git status --short
```

## Behavioral acceptance

- The dedicated disabled gate is independent and only stripped case-insensitive `true` enables it.
- Guard order is gate, API key, base URL, verified builder, fixture invariants, runtime, then one full valuation.
- No market-hash-name environment value is read or required.
- Invalid fixture geometry stops before runtime and maps to the exact stable reason.
- A successful local-transport run sends one request only to the existing single-price GET endpoint with zero retries and no redirects.
- The script invokes the verified builder and A3 composition exactly once and does not copy provider selection, valuation, fee, EV/ROI, probability, or risk logic.
- Exact BUFF gross sell is used; bid and other-platform values never provide fallback.
- Complete valuation produces one opportunity and no rejection; both true and false risk decisions are plumbing success.
- Existing Step 2F rejection reasons map safely and unexpected result geometry fails closed.
- Request count, runtime close, and process-control behavior match the frozen deterministic contract.

## Output and redaction acceptance

- Success output is exactly the fixed nonnumeric summary plus `risk_passed: yes|no` and request count one.
- Failure output uses only the frozen allowlist and never formats exception details.
- No market hash name, input/output price, numeric EV/revenue/profit/ROI, float, seed, provenance/listing/platform ID, provider record, bid, raw response, key, header, or URL is printed.
- `price_source_path: steamdt:buff` is documented and tested as a closed-composition attestation, not a field recovered from the final DTO.

## Architecture acceptance

- Production fixture, client, aggregate, A1, A2, A3, `ValuationService`, Step 2F, solver, engine, EV/risk, SteamApis, cache/Redis/limiter, scheduler, Discord, FastAPI, database, and dependency files have no diff.
- Static guards prove no direct provider/selector/metrics/risk construction or formula, batch/fallback endpoint, SteamApis, cache, scheduler/background, or purchase/account/browser behavior exists in the smoke.
- Protected modules do not reverse-import the script.
- Exactly seven approved paths differ and the index remains empty.

## Runtime safety

All automated validation is offline and must observe:

```text
real SteamDT requests: 0
live A5 smoke executions: 0
SteamApis connections: 0
direct BUFF requests: 0
Redis connections: 0
Discord requests: 0
PostgreSQL connections: 0
scheduler/background executions: 0
purchase actions: 0
```

Local HTTPX transports and narrow fake collaborators are not real network.

## Inherited environment presence

After all offline validation, nonblank presence was inspected without exposing values:

```text
STEAMDT_RUN_BUFF_LIVE_RECIPE_VALUATION_SMOKE: no
STEAMDT_API_KEY: no
```

The live smoke was not executed.

## Observed results

Validated entirely offline on Python 3.13:

```text
tests/test_live_steamdt_buff_live_recipe_valuation_smoke.py: 82 passed
tests/test_steamdt_buff_live_recipe_fixture.py: 38 passed
tests/test_steamdt_buff_live_recipe_valuation.py: 18 passed
tests/test_live_recipe_valuation.py: 41 passed
Full pytest: 2566 passed, 23 skipped, 1 warning
Ruff: passed
Mypy app: no issues in 66 source files
Mypy A5 script: no issues in 1 source file
git diff --check: passed
```

The full-suite warning is the existing Starlette `TestClient` / HTTPX deprecation warning and is unrelated to A5. Git emitted LF-to-CRLF working-copy notices for the two modified existing files; no whitespace error was found.

Automated tests used narrow fakes and local HTTPX transports only. Real SteamDT requests, A5 live-smoke executions, SteamApis connections, direct BUFF requests, Redis/Discord/PostgreSQL connections, scheduler/background work, and purchase actions were all zero.
