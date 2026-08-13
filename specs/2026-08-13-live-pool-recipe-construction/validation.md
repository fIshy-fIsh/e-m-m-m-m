# Phase 13A Step 2J — Validation

## Required commands

```bash
py -3.13 -m pytest tests/test_live_pool_recipe_construction.py
py -3.13 -m pytest tests/test_live_recipe_construction.py
py -3.13 -m pytest tests/test_live_metadata_catalog.py
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

- One call captures exactly one current pool snapshot and invokes existing Step 2E construction exactly once.
- Snapshot count equals the unique post-TTL snapshot length and complete eligible-plus-rejected classification total.
- Empty and rejected-only pools return valid no-recipe results.
- A real synthetic multi-collection pool produces one Step 2E recipe with ten ordered selected source IDs and one retained rejection.
- Newer pool state is used; older ignored and capacity-evicted history does not resurface.
- Snapshot lazy TTL eviction removes expired state before construction and remains after a later construction failure.
- Equivalent current state, catalog, config, and fixed clock yield deterministic classification, recipes, and selected IDs.
- Ordinary snapshot/construction/malformed-result failures become one fixed redacted unchained wrapper error with no partial result.
- `MemoryError`, cancellation, and non-`Exception` control flow propagate unchanged.

## Static acceptance

- Exactly the seven approved paths change.
- The feature-spec directory contains only `plan.md`, `requirements.md`, and `validation.md`.
- The production module has one `snapshot()` call site and one `construct_live_recipes()` call site.
- It calls no classifier, candidate adapter, metadata lookup, solver, pool lookup, ingest, source-ID join, purchase-link API, valuation, EV/risk, or alerting function.
- It imports no WebSocket client, Step 2I session runner, `websockets`, SteamDT, BUFF, Redis, Discord, FastAPI, scheduler, database, config, environment, logging, browser, or purchase boundary.
- It contains no retry, reconnect, sleep, task, thread, queue, executor, scheduler, loop, cache, or background manager.
- Protected modules, dependency/config files, previous specs, and existing tests remain unchanged.
- Nothing is staged, committed, or pushed; Step 2G and Step 2K remain untouched.

## Runtime safety

- Focused and full tests make zero real SteamApis connections.
- Tests and dry-runs make zero SteamDT, BUFF, Redis, Discord, or PostgreSQL requests/connections.
- Synthetic links/IDs/economics remain absent from wrapper result repr and public errors.
- No live smoke, secret, automatic login, Cookie collection, CAPTCHA/risk-control bypass, browser purchase, marketplace write, or automatic purchase exists.
- No actual whitespace errors or intentional line-ending rewrites exist.

## Observed results

Validated on Python 3.13:

```text
tests/test_live_pool_recipe_construction.py: 27 passed
tests/test_live_recipe_construction.py: 25 passed
tests/test_live_metadata_catalog.py: 53 passed
tests/test_steamapis_offer_pool.py: 58 passed
Full pytest: 2138 passed, 23 skipped, 1 warning
Ruff: passed
Mypy: no issues in 61 source files
run_mock_pipeline.py: passed
run_scheduler_once.py: passed
scripts/docker_smoke_test.py: passed
git diff --check: no actual whitespace errors
```

The full suite's one warning is the established Starlette `TestClient` / `httpx` deprecation warning and is unrelated to this current-pool boundary.

The focused real integration used a real offer pool, metadata catalog, Step 2D classifier, Step 2E construction, and new wrapper with synthetic observations only. Its unique snapshot contained 12 observations, classified 11 as eligible and one as `metadata_not_found`, preserved a mixed two-collection bucket, constructed one recipe with ten selected source IDs, and performed no network or provider I/O.

Static and scope audits observed:

- exactly seven approved changed paths and exactly three feature-spec files;
- one production `snapshot()` call site and one `construct_live_recipes()` call site;
- no direct classifier, candidate adapter, metadata lookup, solver, pool lookup/ingest, link, session/WebSocket, valuation/EV/risk, SteamDT, external I/O, or background boundary;
- post-TTL snapshot count equals complete eligible-plus-rejected classification count;
- lazy TTL eviction remains after later construction failure, with no wrapper rollback or partial result;
- empty, rejected-only, TTL, capacity, newer/older, and deterministic current-state cases passed;
- no protected module, dependency/config file, existing test/spec, or staged-file change;
- no real SteamApis, SteamDT, BUFF, Redis, Discord, or PostgreSQL request/connection;
- no live smoke, secret, purchase behavior, commit, push, Step 2G resumption, or Step 2K work.

Git emitted Windows working-copy LF-to-CRLF notices for the two modified existing documentation files. No line endings were rewritten, and `git diff --check` found no whitespace error.
