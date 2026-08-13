# Phase 13A Step 2I — Validation

## Required commands

```bash
py -3.13 -m pytest tests/test_steamapis_offer_session.py
py -3.13 -m pytest tests/test_steamapis_websocket_client.py
py -3.13 -m pytest tests/test_steamapis_offer_pool.py
py -3.13 -m pytest tests/test_steamapis_listing.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
```

## Behavioral acceptance

- Empty normal session returns zero; N successful ingest calls return N.
- The client iterator is called once and observations reach pool ingest in exact yield order.
- Added and newer Updated retention remains pool-authoritative.
- Older, identical, expired, and capacity-evicted observations still count after normal ingest return while pool retention remains unchanged.
- Equal-time conflicting content fails through the pool and becomes the fixed session error.
- Client failure after successful ingestion fails the runner without discarding earlier pool state.
- No partial result is returned on failure and no rollback is attempted.
- Normal WebSocket close returns the accumulated count rather than an error.
- Ordinary client, pool, and unexpected errors are fixed, redacted, and unchained.
- `MemoryError`, cancellation, and non-`Exception` `BaseException` values propagate unchanged.
- The real-client/fake-connector/parser/pool/runner offline chain retains the expected final A/B state and returns count four.

## Static acceptance

- Exactly the seven approved paths change.
- The feature-spec directory contains only `plan.md`, `requirements.md`, and `validation.md`.
- The runner has one iterator call site and one ingest call site.
- The runner calls no snapshot or pool lookup.
- It has no parser/schema/hash/link logic, timestamp/event comparison, deduplication, TTL, or capacity implementation.
- It has no reconnect, retry, backoff, sleep, task, thread, queue, gather, executor, scheduler, or background manager.
- It imports no candidate, metadata, construction, solver, valuation, EV/risk, SteamDT, BUFF, Redis, Discord, FastAPI, database, config, environment, logging, browser, or purchase boundary.
- Protected client/parser/pool/provider/runtime modules and `pyproject.toml` remain unchanged.
- Nothing is staged, committed, or pushed; Step 2G and Step 2J remain untouched.

## Runtime safety

- Focused and full tests make zero real SteamApis connections.
- Tests and dry-runs make zero SteamDT, BUFF, Redis, Discord, or PostgreSQL requests/connections.
- Only synthetic keys/links/IDs/data are used, and none is exposed by result repr or session errors.
- No live smoke, secret, automatic login, Cookie collection, CAPTCHA/risk-control bypass, browser purchase, or marketplace write exists.
- No actual whitespace errors or intentional line-ending rewrites exist.

## Observed results

Validated on Python 3.13 with the declared `websockets>=17,<18` dependency:

```text
tests/test_steamapis_offer_session.py: 32 passed
tests/test_steamapis_websocket_client.py: 46 passed
tests/test_steamapis_offer_pool.py: 58 passed
tests/test_steamapis_listing.py: 93 passed
Full pytest: 2111 passed, 23 skipped, 1 warning
Ruff: passed
Mypy: no issues in 60 source files
run_mock_pipeline.py: passed
run_scheduler_once.py: passed
scripts/docker_smoke_test.py: passed
git diff --check: no actual whitespace errors
```

The full suite's one warning is the established Starlette `TestClient` / `httpx` deprecation warning and is unrelated to this session runner.

The focused end-to-end test used the real WebSocket client, injected fake connector/context/WebSocket, unchanged real parser path, real offer pool, and real runner. It opened no socket and made no DNS or provider call. Its SUBSCRIBED → Added A → newer Updated A → Added B → older Updated A → normal-close sequence consumed four observations, retained A at the newer timestamp and B, preserved parser-generated identity and opaque pool provenance, and used one connection and one subscription.

Static and scope audits observed:

- exactly seven approved changed paths and exactly three feature-spec files;
- one iterator call site, one ingest call site, and no runner snapshot or pool lookup;
- no parser/schema/hash/link, timestamp/event comparison, retention, TTL, or capacity duplication;
- no reconnect, retry, sleep, task, thread, queue, scheduler, background manager, or downstream/external subsystem import;
- no protected module or dependency change and no staged files;
- no real SteamApis, SteamDT, BUFF, Redis, Discord, or PostgreSQL request/connection;
- no live smoke, secret, purchase behavior, commit, push, Step 2G resumption, or Step 2J work.

Git emitted Windows working-copy LF-to-CRLF notices for the two modified existing documentation files. No line endings were rewritten, and `git diff --check` found no whitespace error.
