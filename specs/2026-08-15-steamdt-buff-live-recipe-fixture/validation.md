# Phase 13A Step 2M-A5-PRE1 — Validation

## Required offline commands

```bash
py -3.13 -m pytest tests/test_steamdt_buff_live_recipe_fixture.py
py -3.13 -m pytest tests/test_recipe_solver.py
py -3.13 -m pytest tests/test_tradeup_engine.py
py -3.13 -m pytest tests/test_live_recipe_construction.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
git diff --check
```

## Behavioral acceptance

- The exact output name enters only one output metadata record.
- The builder calls the existing public recipe-selection authority once and the real trade-up engine derives all output geometry.
- One fixed synthetic input metadata record and one complete next-rarity output record produce one recipe, ten inputs, and one canonical output.
- Probability, output float, wear, zero output-price placeholder, and zero contribution are the exact real engine result rather than handwritten fixture fields.
- Ten deterministic compatibility tokens remain aligned to solver-selected listing order and are clearly non-observed, non-listing, non-purchase provenance.
- Repeated builds are structurally equal and detached, with no clock, random, environment, file, or network dependency.
- The derived future provider-lookup budget is one; PRE1 performs no provider lookup.

## Architecture acceptance

- The fixture module imports no trade-up result/input/output models and calls no geometry helper directly.
- It contains one `construct_recipe_selections()` call site and no direct engine, valuation, EV, ROI, risk-evaluation, provider, client, runtime, SteamApis observation/payload/pool, cache, scheduler, task, or purchase path.
- Existing solver, engine, live metadata/construction, provider, valuation, and runtime authorities remain unchanged and do not reverse-import the fixture.
- Exactly six approved paths differ and no path is staged.

## Runtime safety

All tests and checks are offline and must observe:

```text
real SteamDT requests: 0
SteamDT provider lookups: 0
valuation executions: 0
EV/ROI/risk evaluations: 0
SteamApis observations/connections: 0
BUFF requests: 0
Redis connections: 0
Discord requests: 0
PostgreSQL connections: 0
live smoke executions: 0
scheduler/background executions: 0
purchase actions: 0
```

## Observed results

Validated entirely offline on Python 3.13:

```text
tests/test_steamdt_buff_live_recipe_fixture.py: 33 passed
tests/test_recipe_solver.py: 59 passed
tests/test_tradeup_engine.py: 15 passed
tests/test_live_recipe_construction.py: 25 passed
Full pytest: 2479 passed, 23 skipped, 1 warning
Ruff: passed
Mypy app: no issues in 66 source files
git diff --check: passed
```

The full suite's one warning is the established Starlette `TestClient` / `httpx` deprecation warning and is unrelated to PRE1. Git emitted an LF-to-CRLF working-copy notice for `docs/STEAMDT_API_NOTES.md`; no whitespace error was found.

The focused tests observed one real `construct_recipe_selections()` call and one indirect real `calculate_tradeup_results()` call. They confirmed exact one-recipe/ten-input/one-canonical-output geometry, engine-derived probability/float/wear, zero construction price/contribution placeholders, deterministic selected order/configuration, and ten synthetic compatibility tokens with no observation or purchase provenance.

All validation remained construction-only. Provider lookups, valuation, EV/ROI/risk evaluation, real SteamDT requests, live smoke executions, SteamApis observations/connections, BUFF requests, Redis/Discord/PostgreSQL connections, scheduler/background work, and purchase actions were all zero.
