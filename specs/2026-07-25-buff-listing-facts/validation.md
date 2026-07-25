# Phase 12E3A — Validation

## Automated commands

Run without any live-service opt-in:

```bash
py -3.13 -m pytest tests/test_buff_listing.py
py -3.13 -m pytest tests/test_buff_listing_parser.py
py -3.13 -m pytest tests/test_buff_listing_eligibility.py
py -3.13 -m pytest tests/test_buff_listing_facts.py
py -3.13 -m pytest tests/test_buff_listing.py tests/test_buff_listing_parser.py tests/test_buff_listing_eligibility.py tests/test_buff_listing_facts.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
```

## Acceptance audit

- The fixture is synthetic, project-owned, versioned, and contains no private or transport data.
- Schema version is exact integer `1`; source is exact canonical `buff`; records is an ordered JSON array.
- Every record has the exact five fields and exact boolean flags.
- Missing and unknown fields, malformed records, duplicate JSON keys, duplicate canonical identities, and listing-ID collisions fail closed.
- Record order is preserved; complete failure returns no partial tuple.
- Mapping inputs, record inputs, and provider constructor inputs are defensively detached.
- Public models are immutable, keyword-only where applicable, and repr-safe.
- Validation/parser messages are fixed and reveal no identity, rejected value, path, payload, secret, URL, or nested exception text.
- `MemoryError`, `KeyboardInterrupt`, and other `BaseException` values propagate.
- The provider exposes one narrow async lookup and performs no I/O, environment read, network access, task/thread creation, or lifecycle work.
- Exact canonical listing ID and market name produce `FOUND` with the existing eligibility facts model.
- Unknown ID and known ID with the wrong name both produce the same `MISSING` shape with `facts=None`.
- Missing never becomes an all-false facts object, and wrong-name lookup never receives another record's facts.
- Repeated lookup is deterministic and does not mutate candidate or records.
- Provider construction independently enforces duplicate/collision invariants without silent overwrite.
- Returned facts can be passed directly to the existing eligibility evaluator, but the provider itself never calls it.
- No classification is inferred from item names, paint seed, wear, price, quantity, float, or other candidate data.
- No BUFF client/auth, SteamDT, Redis/cache, metadata provider, scanner, solver, risk, valuation, pipeline, scheduler, FastAPI, config, or runtime module is imported or called.
- Runtime and downstream modules do not reverse-import the facts provider.
- Existing E1, E2A, and E2B focused tests pass independently and together.
- Full regression, Ruff, and Mypy pass.
- All three existing dry-runs retain their prior offline behavior.
- No BUFF, SteamDT, or Redis connection occurs.
- `git diff --check` reports no actual whitespace error.
- The final diff contains exactly the eight approved files, with no staged, generated, temporary, secret, log, cache, or worktree artifacts.
- No existing domain/parser/eligibility, fixture, metadata, scanner, solver, risk, provider, valuation, pipeline, scheduler, FastAPI, config, environment, client, SteamDT, Redis, Docker, database, Discord, roadmap, or API-note file is modified.
- No commit, push, or next phase occurs.
