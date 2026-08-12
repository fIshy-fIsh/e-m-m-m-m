# Phase 13A Step 2D — Validation

## Required commands

```bash
py -3.13 -m pytest tests/test_live_metadata_catalog.py
py -3.13 -m pytest tests/test_steamapis_listing.py
py -3.13 -m pytest tests/test_steamapis_candidate_adapter.py
py -3.13 -m pytest tests/test_steamapis_offer_pool.py
py -3.13 -m pytest tests/test_recipe_solver.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
git diff --name-status 3b610d4
git diff --stat 3b610d4
git diff --cached --name-only
git status --short
```

## Behavioral acceptance

- Catalog construction detaches exact metadata with `raw=None`, rejects empty input and global duplicate names, preserves exact case-sensitive identity, and creates deterministic name and solver-mode indexes.
- Source-list, record, and raw-payload mutation cannot change catalog results; lookups return fresh detached metadata.
- Every snapshot observation produces exactly one eligible binding or typed rejection, without name-based offer deduplication or silent missing-metadata skips.
- Rejection precedence is metadata missing, collection missing, candidate float missing, then float outside the inclusive skin range.
- Same rarity/StatTrak/Souvenir offers share one bucket even across collections; each of the three key dimensions separates buckets, while affected collection sets remain exact.
- Eligible/rejected snapshot subsequences, bucket binding order, and sorted bucket order are deterministic.
- Purchase provenance remains only on observations and can be rejoined through source ID; no purchase link enters the classification result.
- Errors are fixed and redacted, ordinary failures are atomic, and memory/control-flow exceptions propagate.

## Architecture and safety acceptance

- The module performs no metadata provider/file/env/network access, WebSocket, SteamApis transport, BUFF/SteamDT/Redis/Discord call, solver/engine/EV/risk/valuation action, pipeline/scheduler/FastAPI/database behavior, URL parsing, browser/login/purchase action, or background work.
- No name-string, seed, collection, StatTrak, Souvenir, special-seed, trade-lock, price, or profitability inference is introduced.
- No dependency, config, environment, fixture, protected service, runtime, or prior spec changes.
- No external service is contacted and no recipe solver is run during validation.

## Scope acceptance

Exactly the seven approved paths may differ from `3b610d4d04dffaafb56be02967f74850f1379f02`. Nothing may be staged. `HEAD` remains unchanged, and work remains uncommitted and unpushed. Stop before Step 2E.

## Results

- `tests/test_live_metadata_catalog.py`: 53 passed across 32 focused test functions.
- `tests/test_steamapis_listing.py`: 93 passed.
- `tests/test_steamapis_candidate_adapter.py`: 41 passed.
- `tests/test_steamapis_offer_pool.py`: 58 passed.
- `tests/test_recipe_solver.py`: 50 passed.
- Full pytest: 1958 passed, 23 skipped, with one pre-existing Starlette/httpx deprecation warning.
- Ruff: all checks passed.
- Mypy: no issues in 56 source files.
- Mock pipeline, one-shot scheduler, and Docker smoke dry-runs: passed without exercising the new Step 2D module or making external connections.
- `git diff --check`: no actual whitespace error; Git emitted only Windows LF-to-CRLF working-copy warnings for the two modified documentation files.
- Scope audit: exactly the seven approved paths differ from `3b610d4`; nothing is staged, `HEAD` is unchanged, and no protected module, dependency/config/env file, fixture, runtime integration, or earlier spec changed.
- Architecture/safety audit: no provider/file/env/network access, WebSocket, SteamApis/BUFF/SteamDT/Redis/Discord connection, recipe solver invocation, EV/risk/valuation, background work, URL/browser behavior, purchase action, secret, commit, push, or Step 2E work.
