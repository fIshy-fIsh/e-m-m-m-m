# Phase 12E4A — Validation

## Automated commands

```bash
py -3.13 -m pytest tests/test_buff_listing_qualification_integration.py
py -3.13 -m pytest tests/test_buff_listing.py tests/test_buff_listing_parser.py tests/test_buff_listing_eligibility.py tests/test_buff_listing_facts.py tests/test_buff_listing_qualification.py tests/test_buff_listing_qualification_integration.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
py -3.13 -m scripts.buff_listing_qualification_integration
py -3.13 scripts/buff_listing_qualification_integration.py
```

## Acceptance audit

- Git started clean on `feature/steamdt-cache-rate-limit` at `6fef04c323c2a3ff4e08293674e637a336be8de9`.
- The command reuses the real listing loader, normalizer, facts loader, offline facts provider, default eligibility policy, and qualification service.
- Import performs no fixture/environment read, client/runtime construction, task creation, network, or Redis I/O.
- Both direct and module entrypoints accept only the two fixture options and use repository-anchored dedicated defaults.
- The exact processing order is listing load, per-observation normalization, facts load, provider/policy/service construction, and sequential per-candidate qualification.
- Every observation is normalized exactly once and every candidate is qualified exactly once; the real service performs exactly one facts lookup for each candidate.
- Listing order and duplicate identities are preserved; there is no deduplication, concurrency, retry, fallback, or partial success result.
- The dedicated fixtures are strict project-owned synthetic schema-v1 documents and produce ordered statuses `qualified`, `rejected`, `qualified`, `missing_facts`.
- The rejected decision retains the existing canonical `stattrak_disallowed` reason.
- Missing facts retain `facts=None`, do not synthesize all-false facts, and remain distinct from rejection.
- The run result contains immutable ordered candidate/result tuples and only derived total/status counts; its lengths and positional correlation are validated.
- Repeated runs are deterministic and return fresh run state.
- Complete runs return 0 even with rejected and missing-facts results; CLI/non-file path errors return 2; parser/provider/qualification/orchestration failures return 1; interruption returns 130.
- Processing failures do not print partial success counts or item summaries and never become business outcomes.
- `MemoryError` and `asyncio.CancelledError` are not wrapped as business or command failure state.
- Successful output contains the required mode, counts, per-listing safe fields, and zero BUFF/SteamDT/Redis usage.
- External market names are credential/URL-redacted and JSON-escaped; control characters cannot add output lines.
- No listing ID, raw object/payload, facts object, fixture path, Cookie, Authorization/Bearer value, token, password, URL, exception message, nested exception text, or traceback appears in output.
- Failure output uses fixed command-owned stage labels rather than arbitrary error class names.
- Static/runtime checks prove no BUFF client/auth/network, SteamDT, Redis/cache, solver/risk/valuation, pipeline/scheduler/FastAPI/config/environment, database, Discord, retry, task, thread, executor, or background capability is imported or called.
- Application/runtime modules do not reverse-import the command.
- Full tests, Ruff, Mypy, and all three existing dry-runs pass without live-service opt-in.
- Both manual entrypoints exit 0 and show all three statuses and counts 4/2/1/1 without connecting BUFF, SteamDT, or Redis.
- `git diff --check` reports no actual whitespace error.
- The final diff contains exactly the nine approved files, with no staged, generated, temporary, secret, log, cache, or worktree artifacts.
- Existing listing/parser/facts/eligibility/qualification modules and fixtures, runtime/downstream modules, roadmap, both API-note files, config/environment, Docker, database, and deployment remain unchanged.
- No commit, push, or next phase occurs.
