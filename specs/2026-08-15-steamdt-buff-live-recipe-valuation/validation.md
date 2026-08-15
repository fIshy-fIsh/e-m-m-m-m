# Phase 13A Step 2M-A3 — Validation

## Required offline commands

```bash
py -3.13 -m pytest tests/test_steamdt_buff_live_recipe_valuation.py
py -3.13 -m pytest tests/test_steamdt_buff_price_provider.py
py -3.13 -m pytest tests/test_steamdt_buff_price_policy.py
py -3.13 -m pytest tests/test_live_recipe_valuation.py
py -3.13 -m pytest tests/test_valuation_service.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
git diff --check
```

## Behavioral acceptance

- The new entry point constructs the exact BUFF provider and existing valuation service, then delegates exactly once to the existing Step 2F authority.
- Authoritative output names come only from existing recipe trade-up results; A3 performs no inference, rematching, or global prefetch.
- Complete exact BUFF gross sell prices produce an existing `LiveRecipeValuationResult` with exact output geometry, Step 2F metrics, configured fee, ROI, risk, provenance, and paint-seed behavior.
- A2 source is exactly `steamdt:buff`; other providers cannot be injected through the closed A3 API, and bidding prices never participate.
- No-BUFF, duplicate-BUFF, missing/nonfinite/nonpositive sell, ordinary client failure, and other-platform-only records create no quote and reject the whole affected recipe as an inherited provider error before EV/risk.
- Missing metadata price placeholders never become an accepted zero/fallback valuation.
- Per-recipe stable deduplication cannot reorder or shift valued geometry. Shared outputs across recipes remain deterministic and are not globally cached.
- One ordinary failed recipe does not contaminate a later complete recipe.
- `MemoryError`, cancellation, keyboard interruption, and system exit propagate by identity with no later call or partial result.

## Architecture acceptance

- A3 production code imports only existing contracts/authorities needed for the closed composition.
- It contains no source/platform selection literal, provider call, name collection, loop, EV/ROI/fee/risk algorithm, fallback, retry, cache, task, network, runtime, lifecycle, SteamApis, Redis, scheduler, purchase, or auto-buy behavior.
- Tests fake only the narrow SteamDT market-data client boundary and use all intermediate production authorities.
- Protected code remains unchanged except the explicitly authorized `MemoryError` rethrow in `ValuationService`; its public contract and ordinary failure behavior remain unchanged.
- Exactly eight approved paths differ, exactly three files exist in the feature-spec directory, and no path is staged.

## Runtime safety

All tests and checks are fake-only/offline and must observe:

```text
real SteamDT requests: 0
SteamApis connections: 0
BUFF direct requests: 0
Redis connections: 0
Discord requests: 0
PostgreSQL connections: 0
live smoke executions: 0
scheduler/background executions: 0
auto-buy or purchase actions: 0
```

## Observed results

Validated offline on Python 3.13:

```text
tests/test_steamdt_buff_live_recipe_valuation.py: 18 passed
tests/test_steamdt_buff_price_provider.py: 47 passed
tests/test_steamdt_buff_price_policy.py: 85 passed
tests/test_live_recipe_valuation.py: 41 passed
tests/test_valuation_service.py: 15 passed
Full pytest: 2388 passed, 23 skipped, 1 warning
Ruff: passed
Mypy app: no issues in 65 source files
git diff --check: passed
Scope audit: exactly 8 approved paths, 0 staged paths
HEAD: d1e7161bbfb80f0a6cf2c64f1b3fe31b842d7407
```

The full suite's one warning is the established Starlette `TestClient` / `httpx` deprecation warning and is unrelated to A3. Git emitted LF-to-CRLF working-copy notices for three modified files; no whitespace error was found.

The synthetic E2E used only a recording fake `SteamDTMarketDataClient` and the real aggregate helper, BUFF selector/provider, `ValuationService`, Step 2F valuation, metrics/fee, and risk authorities. It made no real SteamDT or other network request and did not connect SteamApis, BUFF, Redis, Discord, or PostgreSQL. No scheduler/background task, live smoke, automatic purchase, or purchase-link behavior ran.

The A3 result preserved selected source-offer IDs, original recipe geometry, and compact actual paint seeds. Exact BUFF sell values entered existing EV/ROI/fee calculations; higher bids and other-platform prices did not. No-BUFF, duplicate-BUFF, missing/zero sell, and ordinary provider failures rejected whole affected recipes before metrics/risk; a later complete recipe remained independently valued.

Exactly eight approved paths differ. The only protected production change is the explicitly authorized two-line `MemoryError` rethrow in `ValuationService`, with one focused test; no public contract or ordinary error behavior changed. Nothing is staged, committed, or pushed, and Step 2M-A4 was not started.
