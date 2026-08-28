# Phase 12E3B — Validation

## Automated commands

Run without any live-service opt-in:

```bash
py -3.13 -m pytest tests/test_buff_listing_eligibility.py
py -3.13 -m pytest tests/test_buff_listing_facts.py
py -3.13 -m pytest tests/test_buff_listing_qualification.py
py -3.13 -m pytest tests/test_buff_listing_eligibility.py tests/test_buff_listing_facts.py tests/test_buff_listing_qualification.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
```

## Acceptance audit

- Status values are exactly `qualified`, `rejected`, and `missing_facts`.
- Status is derived from validated lookup/decision state and cannot be supplied or mutated.
- Result fields are exactly candidate, policy, lookup result, and optional decision.
- Result and nested public state are frozen, keyword-only where applicable, repr-safe, and defensively detached.
- Exact candidate, policy, lookup-result, and decision subclasses are rejected.
- The service invokes the provider exactly once per valid call and the evaluator at most once.
- `FOUND` plus an eligible decision produces `QUALIFIED`.
- `FOUND` plus an ineligible decision produces `REJECTED` with all canonical reasons unchanged.
- `MISSING` produces `MISSING_FACTS`, skips the evaluator, and never constructs all-false facts.
- Lookup listing ID and market name both match the queried candidate.
- Found decisions match the authoritative candidate, lookup facts, and policy.
- Invalid collaborator returns, contradictory/tampered state, nested tampering, and mismatches fail closed with fixed safe qualification validation.
- Provider capability validation does not invoke properties/descriptors, and evaluator selection does not invoke truthiness.
- Provider/evaluator ordinary typed errors, `MemoryError`, `KeyboardInterrupt`, `asyncio.CancelledError`, and other `BaseException` values propagate unchanged.
- Validation text/repr reveals no listing identity, market name, raw object, payload, reason, path, seller data, credential, Cookie, Bearer value, password, Redis URL, or nested exception.
- No fact is inferred from item names, listing IDs, wear, stickers, or paint seeds.
- No parser, client/auth, SteamDT, Redis/cache, metadata provider, scanner, solver, risk, valuation, pipeline, scheduler, FastAPI, config, environment, file-I/O, retry, task, thread, or background API is imported or called.
- Lower-level BUFF and runtime/downstream modules do not reverse-import qualification.
- Existing eligibility and facts focused tests pass independently and together with qualification tests.
- Full regression, Ruff, and Mypy pass.
- All three existing dry-runs retain their prior offline behavior.
- No BUFF, SteamDT, or Redis connection occurs.
- `git diff --check` reports no actual whitespace error.
- The final diff contains exactly the seven approved files, with no staged, generated, temporary, secret, log, cache, or worktree artifacts.
- No existing domain/parser/facts/eligibility, fixture, metadata, scanner, solver, risk, provider, valuation, pipeline, scheduler, FastAPI, config, environment, client, SteamDT, Redis, Docker, database, Discord, roadmap, or API-note file is modified.
- No commit, push, or next phase occurs.
