# Phase 13A Step 2C — Validation

## Required commands

```bash
py -3.13 -m pytest tests/test_steamapis_listing.py
py -3.13 -m pytest tests/test_steamapis_candidate_adapter.py
py -3.13 -m pytest tests/test_steamapis_offer_pool.py
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

- Added and Updated may both first-insert one exact defensively revalidated observation.
- Newer message time replaces, older input does not overwrite, an identical equal-time replay is idempotent, and a differing equal-time observation fails closed.
- TTL uses `now - message_timestamp >= ttl`, expires at the exact boundary, and is enforced lazily through all pool reads and writes without background work.
- Capacity never exceeds `max_size` after ingest and deterministically evicts oldest message time then lexical-ascending source ID.
- Snapshots are frozen, keyword-only, repr-safe, tuple-backed, detached from later dictionary changes, and sorted by the exact five-key contract.
- Provenance joins use only `source_offer_id`, preserve opaque purchase links only on observations, and return `None` for valid expired/unknown IDs.
- Candidate projection calls only the existing Step 2B adapter, retains snapshot order, stores no candidates, filters no trade locks, and returns no partial tuple after failure.
- Errors are fixed and redacted; memory and control-flow exceptions propagate.

## Architecture and safety acceptance

- The pool has no JSON parser, WebSocket/client/network, environment/file, URL parser/browser, BUFF adapter, metadata, recipe solver, SteamDT, Redis, pipeline, scheduler, FastAPI, Discord, database, task/thread, login, purchase, or market-write behavior.
- TTL and capacity are documented as project-owned local policies rather than provider removal events.
- No provider raw object, owner/seller/account data, API key, Authorization value, Cookie, token, secret, or URL-derived marketplace ID is retained or emitted.
- No dependency is installed and no external service is contacted.

## Scope acceptance

Exactly these seven paths may differ from HEAD:

```text
README.md
app/services/steamapis_offer_pool.py
docs/STEAMAPIS_MARKET_DATA_NOTES.md
specs/2026-08-12-steamapis-offer-pool/plan.md
specs/2026-08-12-steamapis-offer-pool/requirements.md
specs/2026-08-12-steamapis-offer-pool/validation.md
tests/test_steamapis_offer_pool.py
```

No protected module, dependency/config/environment file, integration script, fixture, or prior spec may change. `git diff --check` must report no actual whitespace error. Work remains uncommitted and unpushed and stops before Step 2D.

## Results

- `tests/test_steamapis_listing.py`: 93 passed.
- `tests/test_steamapis_candidate_adapter.py`: 41 passed.
- `tests/test_steamapis_offer_pool.py`: 58 passed across 39 focused test functions.
- Full pytest: 1905 passed, 23 skipped, 1 pre-existing Starlette/httpx deprecation warning.
- Ruff: all checks passed.
- Mypy: no issues in 55 source files.
- Mock pipeline, one-shot scheduler, and Docker smoke dry-runs: passed without external connections.
- `git diff --check`: no actual whitespace error; Git emitted only the existing Windows LF-to-CRLF working-copy warning for the two modified documentation files.
- Scope/safety audit: exactly the seven approved paths changed; the only credential-like strings are explicit dummy redaction-test values and the pre-existing documented `?apiKey=...` placeholder. No dependency, protected module, external connection, background work, secret, purchase action, commit, push, or Step 2D work.
