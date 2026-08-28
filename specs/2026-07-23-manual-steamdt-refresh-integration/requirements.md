# Phase 12D5C Requirements

## Scope

- Add `scripts/steamdt_refresh_integration.py` and `tests/test_steamdt_refresh_integration.py`.
- Support direct-file and module execution.
- CLI options: `--mode fake|live`, repeatable `--item`, positive `--chunk-size`, and positive `--max-concurrency`.
- Defaults: fake mode, chunk size 5, concurrency 2; require at least one item.
- The CLI must not trim, deduplicate, or chunk items; the existing planner owns those behaviors.

## Fake mode

- Fully offline and deterministic.
- Must not read the SteamDT API key, construct a client, read a Redis URL, or connect externally.
- Must use the real planner, executor, refresh service, `InMemoryPriceCache`, and cached resolver.
- Must use a small script-local source with at least two selector-before candidates per item and `Decimal` prices.
- Output must clearly identify synthetic/fake data.

## Live mode

- Requires both `--mode live` and `STEAMDT_RUN_REFRESH_INTEGRATION=true`.
- A disabled gate returns exit 2 before reading the API key, constructing runtime state, or sending requests.
- Enabled mode reuses the existing SteamDT client runtime composition, limiter, retry, parser, and concrete single-item source.
- Uses only `InMemoryPriceCache`; never connects Redis or uses the official batch endpoint.
- Adds no command-level retry and never falls back to fake.
- The owned runtime closes on success, failure, and cancellation.
- This phase must not execute a real online live command.

## Orchestration and outcomes

- Order: planner, executor, shared cache, then resolver for each unique item in plan order.
- Do not reimplement concurrency or item-failure isolation.
- `NO_CANDIDATES` is a successful refresh outcome.
- Exit 0: all unique refreshes succeeded.
- Exit 1: at least one item failed or orchestration/runtime/cleanup failed.
- Exit 2: CLI, validation, or live-gate error.
- Exit 130: `KeyboardInterrupt`.
- `CancelledError` propagates, resolution does not begin after cancelled execution, no partial report is returned, and no detached task remains.

## Safe output

- Include aggregate plan, execution, selection, request-count, and Redis-use fields.
- Include per-item index, canonical name, occurrence/chunk, execution/refresh/write/cache/resolution/selection fields, refresh advice, and safe error type.
- Print only allowlisted data; never print secrets, URLs with credentials, Authorization values, raw payloads, exception messages, or tracebacks.
- Escape control characters and redact sensitive-shaped text with the existing smoke helper behavior.

## Exclusions

- No planner, executor, refresh, source, client, selector, cache, limiter, or retry semantic changes.
- No Redis/cache backend, provider, valuation, pipeline, scheduler, FastAPI, Discord, BUFF, Docker, Alembic, PostgreSQL, or background-worker wiring.
- No automatic buying, login, cookie extraction, CAPTCHA bypass, risk-control bypass, or browser purchase automation.
- No commit or push.
