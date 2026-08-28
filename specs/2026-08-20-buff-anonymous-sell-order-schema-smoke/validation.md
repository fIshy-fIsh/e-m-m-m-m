# Phase 13B Step 2B — Validation

## Required offline commands

```bash
py -3.13 -m pytest tests/test_live_buff_anonymous_sell_order_schema_smoke.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 -m mypy scripts/run_live_buff_anonymous_sell_order_schema_smoke.py
git diff --check
git diff --name-only
git diff --stat
git diff --cached --name-only
git status --short
```

## Behavioral acceptance

- Only the dedicated normalized gate enables the smoke; missing/invalid goods IDs stop before runtime.
- The owned client can issue at most one transport-bound anonymous GET to the exact fixed endpoint/query and never follows redirects or inherited proxies.
- Request headers contain only the fixed transparent User-Agent/Accept plus normal HTTPX transport headers and no auth, Cookie, device, CSRF, browser, or session state.
- Strict response handling validates exact `code == OK`, `data.items`, and only the first item.
- Required ID, positive Decimal price, and bounded paintwear must all validate; optional asset/seed absence remains success.
- Every failure uses only the fixed allowlist; output contains no concrete response or request data.
- Owned cleanup, request-state precedence, and process-control propagation match the frozen contract.

## Architecture acceptance

- `BuffHttpClient` and all protected Phase 12/application modules have no diff.
- The smoke contains no provider/scanner/qualification/candidate/solver/valuation/runtime wiring beyond its standalone anonymous HTTPX probe.
- Static guards prove no login, Cookie/session, auth/key/device/CSRF, proxy/UA rotation, retry/backoff, browser/evasion, purchase, pagination/filter loop, background work, or marketplace write.
- Protected modules do not reverse-import the smoke.
- Exactly seven approved paths differ and the index is empty.

## Output safety

- Success exposes only fixed anonymous/read-only/page/schema-presence attestations and actual request count.
- No goods/listing/asset ID, price, float, seller/account data, market name, BUFF message, URL/query, response body, headers, cookies, exception details, repr, or traceback is printed.
- No raw response becomes fixture, expected production value, log data, or documentation content.

## Runtime safety

All automated validation is offline and must observe:

```text
real BUFF requests: 0
live anonymous smoke executions: 0
SteamDT requests: 0
SteamApis connections: 0
Redis/Discord/PostgreSQL connections: 0
scheduler/background executions: 0
login/session/Cookie actions: 0
purchase/market-write actions: 0
```

Local HTTPX transports and fake runtimes are not real network.

## Inherited environment presence

After offline validation, nonblank presence was inspected without exposing values:

```text
BUFF_RUN_ANONYMOUS_SELL_ORDER_SCHEMA_SMOKE: no
BUFF_READONLY_SMOKE_GOODS_ID: no
```

The live smoke was not executed.

## Observed results

Validated entirely offline on Python 3.13:

```text
tests/test_live_buff_anonymous_sell_order_schema_smoke.py: 148 passed
Full pytest: 2714 passed, 23 skipped, 1 warning
Ruff: passed
Mypy app: no issues in 66 source files
Mypy smoke script: no issues in 1 source file
git diff --check: passed
```

The full-suite warning is the existing Starlette `TestClient` / HTTPX deprecation warning and is unrelated to Step 2B. Git emitted an LF-to-CRLF working-copy notice for the modified `.env.example`; no whitespace error was found.

Automated tests used fake runtimes and local HTTPX transports only. Real BUFF/SteamDT requests, SteamApis connections, live-smoke executions, Redis/Discord/PostgreSQL connections, scheduler/background work, login/session/Cookie actions, and purchase/market-write actions were all zero.
