# Phase 13A Step 2B — Validation

## Required commands

```bash
py -3.13 -m pytest tests/test_steamapis_listing.py
py -3.13 -m pytest tests/test_steamapis_candidate_adapter.py
py -3.13 -m pytest tests/test_market_scan_service.py
py -3.13 -m pytest tests/test_recipe_solver.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
git diff --name-status
git diff --stat
git status --short
```

## Behavioral acceptance

- One exact valid observation maps to the exact existing `CandidateListing` type.
- Goods/listing identities equal `steamapis:buff163:<source_offer_id>` and source equals `steamapis:buff163`.
- Tests and docs state that these are not authoritative BUFF IDs or a provider-documented marketplace ID.
- Market name, Decimal CNY, paint seed, documented inspect link, and message timestamp map exactly; raw is `None`.
- Decimal CNY precision is preserved without float conversion.
- Observation float is checked before conversion, converted once without rounding/clamping/string conversion, and checked afterward.
- Purchase link is absent from every candidate field and candidate repr while remaining unchanged on the source observation for a later source-ID join.
- Full public-constructor reconstruction rejects wrong types, subclasses, tampered identity/source/value/time state, and inconsistent observations.
- Repeated mapping is deterministic and returns independent candidates without mutating the source.
- Ordinary failures use only the fixed redacted adapter error with no nested chain; memory and control-flow exceptions propagate.

## Architecture and safety acceptance

- The adapter has no WebSocket/client/network, URL parser, environment, file, pool, metadata, solver, SteamDT, Redis, pipeline, scheduler, FastAPI, Discord, task/thread, browser, login, purchase, or market-write behavior.
- It does not import or call the Phase 12 BUFF adapter or reinterpret its source-local IDs as authoritative BUFF identity.
- Protected runtime modules do not reverse-import the adapter.
- No raw provider object, owner/seller/account data, credentials, API keys, Cookie, token, or secret-shaped value is retained or emitted.
- No dependency is installed and no external service is contacted.

## Scope acceptance

Exactly these seven paths may differ from HEAD:

```text
README.md
app/services/steamapis_candidate_adapter.py
docs/STEAMAPIS_MARKET_DATA_NOTES.md
specs/2026-08-11-steamapis-candidate-adapter/plan.md
specs/2026-08-11-steamapis-candidate-adapter/requirements.md
specs/2026-08-11-steamapis-candidate-adapter/validation.md
tests/test_steamapis_candidate_adapter.py
```

No protected module, dependency/config/environment file, fixture, or previous spec changes. `git diff --check` must report no actual whitespace error. The final work remains uncommitted and unpushed and stops before Step 2C.

## Results

- `tests/test_steamapis_listing.py`: 93 passed.
- `tests/test_steamapis_candidate_adapter.py`: 41 passed.
- `tests/test_market_scan_service.py`: 25 passed.
- `tests/test_recipe_solver.py`: 50 passed.
- Full pytest: 1847 passed, 23 skipped, 1 pre-existing Starlette/httpx deprecation warning.
- Ruff: all checks passed.
- Mypy: no issues in 54 source files.
- Mock pipeline, one-shot scheduler, and Docker smoke dry-runs: passed without external connections.
- `git diff --check`: no actual whitespace error; Git emitted only the existing Windows LF-to-CRLF working-copy warning.
- Scope/safety audit: exactly the seven approved paths changed; no dependency, protected module, external connection, secret, purchase action, commit, push, or Step 2C work.
