# Phase 13A Step 2E — Validation

## Required commands

```bash
py -3.13 -m pytest tests/test_live_recipe_construction.py
py -3.13 -m pytest tests/test_recipe_solver.py
py -3.13 -m pytest tests/test_live_metadata_catalog.py
py -3.13 -m pytest tests/test_steamapis_offer_pool.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
git diff --name-status e7bcdfa1958a24f71646c7d315ff0e589af37d08
git diff --stat e7bcdfa1958a24f71646c7d315ff0e589af37d08
git diff --cached --name-only
git status --short
```

## Behavioral acceptance

- The source-agnostic selection trace comes directly from selected candidates and remains one-to-one with constructed inputs.
- Existing construction and evaluated solver behavior remains compatible, with no duplicate trade-up calculation.
- One synthetic pool snapshot is classified exactly once; only eligible candidates in matching exact mode buckets enter construction.
- At least two collections may be combined within one exact rarity/mode recipe.
- Ten selected listing IDs map exactly through same-bucket bindings to ten ordered, unique source offer IDs, including identical-economics listings.
- Unknown, incomplete, duplicate, repeated, or cross-bucket provenance fails atomically.
- Every selected source ID joins back to a retained pool observation and nonempty opaque purchase link, while no link enters a result DTO or repr.
- Construction yields exactly ten inputs, nonempty results, the engine-contract probability total, unchanged paint-seed semantics, and the existing derived total cost.
- Repeated construction is deterministic and does not mutate input snapshots, metadata, configurations, or pools.

## Architecture and safety acceptance

- The integration calls no `solve_recipes`, opportunity metrics, risk filter, valuation service/provider, SteamDT, Redis, BUFF client, Discord, WebSocket/network, environment/config/provider/file loader, pipeline/scheduler/FastAPI/database, browser/login/purchase action, or background work.
- No source ID is parsed from a candidate namespace or URL and no market name/price/float/seed approximate matching is introduced.
- No dependency, config, environment, fixture, protected service, runtime integration, prior spec, or Step 2A–2D module changes.
- No external service is contacted, no dependency is installed, and no commit or push occurs.

## Scope acceptance

Only the nine approved paths may differ from `e7bcdfa1958a24f71646c7d315ff0e589af37d08`: the new live module and tests, the minimal solver provenance source/test changes, two documentation files, and this spec directory's three files. Nothing may be staged. Stop before Step 2F.

## Results

- `tests/test_live_recipe_construction.py`: 25 passed.
- `tests/test_recipe_solver.py`: 59 passed.
- `tests/test_live_metadata_catalog.py`: 53 passed.
- `tests/test_steamapis_offer_pool.py`: 58 passed.
- Full pytest: 1992 passed, 23 skipped, with one pre-existing Starlette/httpx deprecation warning.
- Ruff: all checks passed.
- Mypy: no issues in 57 source files.
- Mock pipeline, one-shot scheduler, and Docker smoke dry-runs: passed. They exercised only established synthetic/dry-run paths and made no live external connection.
- `git diff --check`: no actual whitespace error; Git emitted only Windows LF-to-CRLF working-copy warnings for four modified tracked files.
- Scope audit: exactly the nine approved paths differ from `e7bcdfa`; nothing is staged and no protected module, dependency/config/env file, fixture, runtime integration, or earlier spec changed.
- Architecture/safety audit: the new live integration imports only the approved offline catalog, metadata rarity authority, construction-only solver, snapshot, and trade-up DTO boundaries. It contains no `solve_recipes`, EV/risk/valuation, SteamDT/Redis/BUFF/WebSocket/network/env, purchase-link handling, prefix parsing, background work, browser, login, or purchase behavior.
- Git baseline remains `e7bcdfa1958a24f71646c7d315ff0e589af37d08`; work is uncommitted and unpushed. Step 2F has not started.
