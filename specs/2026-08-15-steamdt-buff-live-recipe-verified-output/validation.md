# Phase 13A Step 2M-A5-PRE2 — Validation

## Required offline commands

```bash
py -3.13 -m pytest tests/test_steamdt_buff_live_recipe_fixture.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
git diff --check
git diff --name-only
git diff --stat
git diff --cached --name-only
git status --short
```

## Behavioral acceptance

- The stable public constant is exactly `M4A4 | Desolate Space (Factory New)`.
- The verified builder accepts no arguments and only delegates once to the unchanged generic PRE1 builder with the exact constant.
- The generic builder continues to accept other valid caller-provided names.
- The returned result remains exactly one recipe, ten inputs, and one canonical output.
- The final production-derived output identity equals the constant, and independently engine-derived wear is `Factory New`.
- Repeated verified builds are structurally equal and detached.
- Existing zero price/contribution construction placeholders and deterministic synthetic compatibility provenance remain unchanged.
- The future provider lookup budget derived from the one canonical output remains one; PRE2 itself performs no provider lookup.

## Architecture acceptance

- The wrapper AST contains no parameters and exactly one return of one generic-builder call with the public constant as its sole keyword value.
- The generic builder remains the only topology, metadata, candidate, solver/config, construction, and validation authority.
- Production fixture source contains no historical observed dynamic price and no price quote/provider/client/valuation/runtime behavior.
- Existing guards continue to prove there is no handwritten trade-up geometry; environment/file/network access; SteamApis observation/pool/purchase data; valuation/EV/ROI/risk execution; cache/scheduler/background work; or reverse import from protected authorities.
- Exactly six approved paths differ and no path is staged.

## Synthetic-topology acceptance

The exact output name is historically query-verified, but the fixture's inputs, collection, candidate prices/floats/seeds, provenance, rarity topology, and timestamp remain synthetic. Validation must not claim that those inputs can produce the real item, that the collection topology is real, or that the result is currently available, buyable, executable, profitable, recommended, or within acceptable risk.

## Runtime safety

All implementation and validation remain offline and must observe:

```text
real SteamDT requests: 0
SteamDT provider lookups: 0
live valuation smoke executions: 0
valuation executions: 0
EV/ROI/risk evaluations: 0
SteamApis observations/connections: 0
BUFF requests: 0
Redis connections: 0
Discord requests: 0
PostgreSQL connections: 0
scheduler/background executions: 0
purchase actions: 0
```

## Manual provenance retained without replay

The user reported one successful manual query on 2026-08-15 through `SteamDTBuffPriceProvider`, source `steamdt:buff`, with request count one. PRE2 validation must not repeat that request. The historical observed dynamic price is neither fixture data nor a future expected value and is intentionally omitted here.

## Observed results

Validated entirely offline on Python 3.13:

```text
tests/test_steamdt_buff_live_recipe_fixture.py: 38 passed
Full pytest: 2484 passed, 23 skipped, 1 warning
Ruff: passed
Mypy app: no issues in 66 source files
git diff --check: passed
```

The full suite's one warning is the established Starlette `TestClient` / `httpx` deprecation warning and is unrelated to PRE2. Git emitted LF-to-CRLF working-copy notices for the three modified pre-existing files; no whitespace error was found.

Focused tests confirmed the exact public constant and zero-argument wrapper, one-call delegation to the generic builder by return identity, exact locked output identity, independently engine-derived Factory New wear, deterministic one-recipe/ten-input/one-output geometry, unchanged synthetic compatibility provenance, and a derived future request budget of one. Static guards confirmed that production fixture source contains no historical observed price, provider/client/quote, valuation/EV/ROI/risk path, environment/file/network access, SteamApis observation/pool/purchase data, or copied topology/geometry.

All validation remained construction-only and offline. Real SteamDT requests, provider lookups, A4/A5 smoke executions, valuation/EV/ROI/risk evaluations, SteamApis observations/connections, BUFF requests, Redis/Discord/PostgreSQL connections, scheduler/background work, and purchase actions were all zero.
