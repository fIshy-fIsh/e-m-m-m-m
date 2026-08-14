# Phase 13A Step 2K — Validation

## Required offline commands

```bash
py -3.13 -m pytest tests/test_live_steamapis_offer_smoke.py
py -3.13 -m pytest tests/test_steamapis_offer_session.py
py -3.13 -m pytest tests/test_steamapis_websocket_client.py
py -3.13 -m pytest tests/test_steamapis_offer_pool.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
```

## Behavioral acceptance

- CLI duration is an integer from 5 through 60, defaulting to 15, and is validated before environment access.
- Only a trimmed, case-insensitive exact `true` gate permits key access or collaborator construction.
- Missing/blank key fails closed with no client, session, pool, or network activity.
- The key never appears in output, repr, errors, test diagnostics, documentation examples, or Git diff.
- Production composition uses the existing config/client, existing session runner, and existing process-local pool with max size 5000 and TTL 10 minutes.
- One timeout context wraps one foreground session-runner call. There is no retry, reconnect, background task, second client, or second iterator.
- Actual timeout expiry cancels through the runner/client and becomes expected `stop_reason: timeout`; external cancellation and collaborator-raised `TimeoutError` are not mislabeled.
- Normal close becomes `stop_reason: normal_close` without reopening the session.
- Exactly one snapshot follows an expected stop; no snapshot follows ordinary session failure.
- Snapshot counts describe current post-TTL/post-capacity observations, and retained total equals current Added plus current Updated.
- Positive retained state succeeds; zero retained state fails without retry.
- Safe terminal output contains only fixed control fields and aggregate integer counts, never listing/provider/secret details.
- Memory and process-control exceptions propagate unchanged.

## Offline integration acceptance

A real existing `SteamApisWebSocketClient` with an injected fake connector, real parser, real `run_steamapis_offer_session()`, real pool, and new smoke boundary processes:

```text
SUBSCRIBED
Added A
newer Updated A
Added B
older Updated A
normal close
```

Expected:

- one connector invocation;
- one subscription;
- one session-runner invocation;
- one final snapshot;
- two retained current observations;
- one retained Added and one retained Updated;
- older A ignored for current retention;
- zero network or DNS activity;
- no synthetic secret or listing detail in summary.

## Static and scope acceptance

- Exactly eight approved paths change and the feature-spec directory contains only `plan.md`, `requirements.md`, and `validation.md`.
- The script has one session-runner call site and one pool snapshot call site.
- It duplicates no endpoint, subscription, compression, parser, or source-ID logic.
- It imports/calls no Step 2J, classifier, metadata provider, candidate adapter, solver, valuation, SteamDT, BUFF client, Redis, Discord, FastAPI, scheduler, database, application config, dotenv, logging, browser, or purchase boundary.
- It contains no retry, reconnect, explicit task, gather, sleep, thread, queue, executor, scheduler, persistence, or background manager.
- Protected modules, dependencies, previous specs/tests, and runtime/config files remain unchanged.
- Nothing is staged, committed, or pushed; Step 2G remains blocked and Step 2L remains unstarted.

## Runtime safety

All ordinary validation commands must observe:

```text
real SteamApis connections: 0
SteamDT requests: 0
BUFF requests: 0
Redis connections: 0
```

No automatic login, Cookie collection, CAPTCHA/risk-control bypass, browser purchase, marketplace write, or automatic purchase exists.

## Conditional real smoke

Only after every offline command passes, inspect the inherited current-process environment without printing values.

If and only if the inherited gate is exact normalized true and the inherited key is nonblank, run once:

```bash
py -3.13 scripts/run_live_steamapis_offer_smoke.py --seconds 15
```

Otherwise do not connect, prompt, search, source `.env`, modify the gate, or retry. Record only `live smoke executed: no` and the missing guard category.

If a live run occurs, record only its safe summary and exit status. Do not record URI, key, provider frame, exception text, or listing detail.

## Observed offline results

Validated on Python 3.13:

```text
tests/test_live_steamapis_offer_smoke.py: 43 passed
tests/test_steamapis_offer_session.py: 32 passed
tests/test_steamapis_websocket_client.py: 46 passed
tests/test_steamapis_offer_pool.py: 58 passed
Full pytest: 2181 passed, 23 skipped, 1 warning
Ruff: passed
Mypy app: no issues in 61 source files
Mypy smoke script (explicit package bases): no issues in 1 source file
run_mock_pipeline.py: passed
run_scheduler_once.py: passed
scripts/docker_smoke_test.py: passed
git diff --check: no actual whitespace errors
Static/scope audit: 37 assertions passed
```

The full suite's one warning is the established Starlette `TestClient` / `httpx` deprecation warning and is unrelated to Step 2K.

All automated tests and dry-runs were offline. The focused real-boundary test used the real existing WebSocket client with an injected fake connector, real parser, real foreground session runner, and real pool; it opened one fake connection, sent one fixed subscription, retained two current observations (one Added and one Updated), and performed zero network or DNS activity.

Static and scope audits observed exactly eight approved changed paths, exactly three feature-spec files, zero staged files, one production session-runner call site, one timeout-factory call site, and one snapshot call site. They found no duplicated endpoint/subscription/parser logic; Step 2J, metadata, recipe, valuation, SteamDT, BUFF, Redis, runtime, persistence, background, browser, and purchase boundaries remain absent.

Git emitted Windows working-copy LF-to-CRLF notices for the three modified existing text files. No line endings were intentionally rewritten, and `git diff --check` found no whitespace error.

## Conditional live result

```text
live smoke executed: no
reason: inherited explicit opt-in gate was not enabled
```

The inherited environment was checked without printing either guard value. No key was requested or searched, `.env` was not loaded, the gate was not changed, and no real SteamApis connection was attempted.
