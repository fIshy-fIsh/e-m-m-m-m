# Phase 13A Step 2M-A4 — Validation

## Required offline commands

```bash
py -3.13 -m pytest tests/test_live_steamdt_buff_price_provider_smoke.py
py -3.13 -m pytest tests/test_steamdt_buff_price_provider.py
py -3.13 -m pytest tests/test_steamdt_buff_price_policy.py
py -3.13 -m pytest tests/test_live_steamdt_market_smoke.py
py -3.13 -m pytest tests/test_steamdt_market_data.py
py -3.13 -m pytest tests/test_steamdt_client.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 -m mypy scripts/run_live_steamdt_buff_price_provider_smoke.py
git diff --check
```

## Behavioral acceptance

- Only normalized explicit `true` on the dedicated gate permits key/name/base/runtime access.
- Missing gate, key, or market name creates no runtime and performs zero network.
- One enabled run constructs one owned HTTP runtime, one real BUFF provider, and invokes `get_price()` once for one stripped inherited name.
- The actual chain is existing single-candidate client → aggregate helper → exact BUFF selector → existing provider → existing `PriceQuote`.
- Success retains exact positive BUFF gross sell Decimal and fixed source `steamdt:buff`; bidding and other platforms never participate.
- Selection failures expose only an existing safe enum value. Other ordinary failures expose only a fixed reason.
- Exactly one request attempt is mandatory, no retry/fallback occurs, and owned resources close before output.
- Process-control values propagate by identity after cleanup with no partial summary.

## Architecture acceptance

- The script duplicates no HTTP response parser, BUFF selector, price validation, quote creation, valuation math, or retry algorithm.
- It calls neither provider batch nor official batch/base/avg/kline/wear APIs.
- It imports or invokes no SteamApis, Redis/cache, recipe, valuation, EV/ROI/risk, scheduler, background, Discord, FastAPI, database, marketplace action, login, Cookie, CAPTCHA, browser, or purchase path.
- Exactly seven approved paths differ, protected files remain unchanged, and no path is staged.

## Output safety

Neither stdout nor stderr contains:

- API key or Authorization/header data;
- actual requested market hash name;
- base/request URL;
- raw response, raw mapping, or provider records;
- platform item ID or update-time value;
- bidding price/count;
- nested exception text, repr, cause, or traceback;
- account, listing, inspect, or purchase data.

## Runtime safety

All implementation-time tests and checks are offline and must observe:

```text
real SteamDT requests: 0
SteamApis connections: 0
BUFF direct requests: 0
Redis connections: 0
Discord requests: 0
PostgreSQL connections: 0
live smoke executions: 0
scheduler/background executions: 0
purchase actions: 0
```

Local HTTPX transports and fake clients are offline test doubles, not real SteamDT requests.

## Observed results

Validated offline on Python 3.13:

```text
tests/test_live_steamdt_buff_price_provider_smoke.py: 58 passed
tests/test_steamdt_buff_price_provider.py: 47 passed
tests/test_steamdt_buff_price_policy.py: 85 passed
tests/test_live_steamdt_market_smoke.py: 40 passed
tests/test_steamdt_market_data.py: 16 passed
tests/test_steamdt_client.py: 117 passed
Full pytest: 2446 passed, 23 skipped, 1 warning
Ruff: passed
Mypy app: no issues in 65 source files
Mypy provider smoke script: no issues in 1 source file
git diff --check: passed
```

The full suite's one warning is the established Starlette `TestClient` / `httpx` deprecation warning and is unrelated to A4. Git emitted LF-to-CRLF working-copy notices for `.env.example` and `docs/STEAMDT_API_NOTES.md`; no whitespace error was found.

All A4 tests used fake clients, fake runtimes, disabled subprocess entrypoints, or local HTTPX transports. Real SteamDT requests, live smoke executions, SteamApis connections, BUFF direct requests, Redis, Discord, PostgreSQL, scheduler/background work, and purchase actions were all zero.

The real provider, aggregate helper, exact BUFF policy, single endpoint parser/client, request counter, and owned cleanup path were exercised offline. Exact BUFF gross sell Decimal values were retained; higher bids and other-platform values never participated. Selection failures exposed only allowlisted reasons, other ordinary failures remained fixed/redacted, and process-control values propagated after cleanup.

The real smoke was not executed. The current process inherited none of the three nonblank guards: provider-smoke gate `no`, API key `no`, market hash name `no`.

The concluding scope audit observed exactly seven approved paths: two modified files plus two new files and one new three-file spec directory. The index was empty. Git represented the untracked spec directory as one status entry. The working tree remains intentionally dirty and unstaged for review; nothing was committed or pushed.
