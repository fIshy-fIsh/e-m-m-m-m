# Phase 12E2A Validation

## Automated checks

```bash
py -3.13 -m pytest tests/test_buff_listing.py
py -3.13 -m pytest tests/test_buff_listing_parser.py
py -3.13 -m pytest tests/test_buff_listing.py tests/test_buff_listing_parser.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
```

## Acceptance audit

- The new committed-shape fixture is project-owned, visibly synthetic, and documented as not representing the BUFF official API response.
- The pre-existing pipeline fixture is recognized as synthetic legacy mock data with seller/raw-shaped fields and is not copied or used as the E2A schema.
- Mapping and file parsing produce the same ordered observations for the valid fixture.
- Exact field sets, version/source, JSON string Decimals, exact integers, aware timestamps, and sticker entries fail closed.
- The file loader rejects duplicate JSON keys and classifies JSON decode separately from fixture/domain parse failures.
- Malformed records never produce a partial result.
- Quantity zero, listing duplicates, sticker duplicates, Decimal precision, UTC normalization, and blank wear normalization are preserved.
- Results are immutable and detached from later input mutation; raw input is not retained.
- Errors expose no raw value, payload, path content, Cookie, Authorization/Bearer token, Redis URL, password, or nested exception message.
- `MemoryError`, `KeyboardInterrupt`, and other `BaseException` values are not wrapped.
- Import/AST checks prove there is no client/auth, SteamDT, Redis, provider/valuation, pipeline/scheduler/FastAPI, env read, task/thread, network, or file-write behavior.
- Existing runtime modules do not reverse-import the parser.
- Full regression, Ruff, Mypy, and all three existing offline dry-runs pass without connecting BUFF, SteamDT, or Redis.
- `git diff --stat` and `git status --short` show only approved implementation, tests, fixture, documentation, and feature-spec files; nothing is staged, committed, or pushed.
