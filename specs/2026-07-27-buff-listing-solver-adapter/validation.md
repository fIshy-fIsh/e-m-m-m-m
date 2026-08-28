# Phase 12E4B — Validation

## Commands

```bash
py -3.13 -m pytest tests/test_buff_listing_qualification.py
py -3.13 -m pytest tests/test_market_scan_service.py
py -3.13 -m pytest tests/test_recipe_solver.py
py -3.13 -m pytest tests/test_buff_listing_solver_adapter.py
py -3.13 -m pytest tests/test_buff_listing_qualification.py tests/test_market_scan_service.py tests/test_recipe_solver.py tests/test_buff_listing_solver_adapter.py
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

## Acceptance criteria

- A valid v2-derived `QUALIFIED` result maps into the exact existing `CandidateListing` with all specified fields and safe explicit defaults.
- The result is reconstructed through its public constructor before adapter gates; no qualification private helper is imported or copied.
- `REJECTED`, `MISSING_FACTS`, legacy-null goods ID, missing float, wrong exact type, subclasses, and tampered nested snapshots fail closed.
- Lookup must be `FOUND` with facts; the decision must be present, eligible, and consistent with result candidate, facts, and policy.
- Available quantity is checked against the actual result policy threshold and is not expanded.
- Decimal price value and precision are preserved without float conversion.
- Decimal float is converted exactly once, and the converted representation is finite and within `[0.0, 1.0]`.
- Every successful call returns an independent deterministic existing candidate and does not mutate the input.
- Ordinary destination-construction failure is wrapped in the exact fixed safe adapter error.
- The same injected `MemoryError`, `asyncio.CancelledError`, and another `BaseException` propagate unchanged.
- Error text and repr disclose no identities, market data, rejection reason, raw object, nested exception, credentials, URL, or secret-shaped value.
- Tests and static inspection prove the adapter does not directly call or import a facts provider, evaluator, qualification service, recipe solver, metadata service, live client, config/environment, pipeline, scheduler, FastAPI, SteamDT, Redis, task, thread, retry, or background mechanism. Importing the required existing `CandidateListing` transitively loads its legacy market-scanner module and `BuffClient` type dependency, but creates no client and performs no network or authentication work.
- Existing domain/runtime modules do not reverse-import the adapter.
- Focused tests, combined tests, full pytest, Ruff, Mypy, and all three existing dry-runs pass.
- Dry-runs preserve existing behavior and do not execute the new adapter path.
- No BUFF, SteamDT, or Redis connection occurs.
- Exactly the seven approved paths are changed; all protected source, fixture, API-note, roadmap, and runtime files remain unchanged.
- `git diff --check` reports no actual whitespace error.
- Work remains uncommitted and unpushed, and no next phase begins.
