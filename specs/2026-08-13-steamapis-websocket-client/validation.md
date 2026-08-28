# Phase 13A Step 2H — Validation

## Required commands

```bash
py -3.13 -m pytest tests/test_steamapis_websocket_client.py
py -3.13 -m pytest tests/test_steamapis_listing.py
py -3.13 -m pytest tests/test_steamapis_offer_pool.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
```

## Static acceptance checks

- Exactly the eight allowed paths changed.
- The feature-spec directory contains only `plan.md`, `requirements.md`, and `validation.md`.
- `pyproject.toml` contains one bounded `websockets>=17,<18` dependency and no second WebSocket library.
- The client imports and calls the existing Step 2A parser.
- The client has one connector call site and one subscription send site.
- The connection explicitly enables `compression="deflate"` and bounds open timeout and message size.
- The fixed subscription contains only Buff163, CS2, and `newFloorOnly=false`.
- No `all` scope, reconnect, retry, sleep, task, thread, scheduler, environment read, logging, raw frame retention, or secret literal exists.
- No imports or calls enter the offer pool, candidate adapter, metadata, recipe construction, recipe valuation, solver, SteamDT, BUFF, Redis, Discord, FastAPI, or database layers.
- Protected parser/core/provider/runtime modules remain unchanged.
- Nothing is staged, committed, or pushed.

## Runtime safety checks

- Focused and full tests make zero real SteamApis connections.
- Tests and dry-runs make zero SteamDT, BUFF, or Redis requests/connections.
- Dummy keys remain synthetic and never appear in repr or fixed errors.
- No live smoke is created or run.
- Normal close ends iteration; abnormal close fails with one fixed redacted error.
- Cancellation and non-ordinary failures propagate unchanged.
- No actual whitespace errors exist.

## Observed results

Validated on Python 3.13 with `websockets` 17.0.1:

```text
tests/test_steamapis_websocket_client.py: 46 passed
tests/test_steamapis_listing.py: 93 passed
tests/test_steamapis_offer_pool.py: 58 passed
Full pytest: 2079 passed, 23 skipped, 1 warning
Ruff: passed
Mypy: no issues in 59 source files
run_mock_pipeline.py: passed
run_scheduler_once.py: passed
scripts/docker_smoke_test.py: passed
git diff --check: no actual whitespace errors
```

The full suite's single warning is the established Starlette `TestClient` / `httpx` deprecation warning and is unrelated to this transport.

Static audit observed:

- exactly eight allowed changed paths and no staged files;
- exactly three feature-spec files;
- one parser call, connector call, and send call site;
- explicit compression, open timeout, and message-size bound;
- no forbidden imports, reconnect/retry syntax, environment access, logging, manual extension header, or purchase-link parsing;
- no real SteamApis, SteamDT, BUFF, or Redis connection;
- no live smoke, commit, push, Step 2G resumption, or Step 2I work.

Git emitted Windows working-copy LF-to-CRLF notices for three existing tracked text files. No line endings were rewritten, and `git diff --check` found no whitespace error.
