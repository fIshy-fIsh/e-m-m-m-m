# Phase 12E2B — Validation

## Automated commands

Run without any live-service opt-in:

```bash
py -3.13 -m pytest tests/test_buff_listing.py
py -3.13 -m pytest tests/test_buff_listing_parser.py
py -3.13 -m pytest tests/test_buff_listing_eligibility.py
py -3.13 -m pytest tests/test_buff_listing.py tests/test_buff_listing_parser.py tests/test_buff_listing_eligibility.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
```

## Acceptance audit

- Facts accept only exact booleans and are never inferred from candidate fields.
- Policy threshold is an exact positive integer and all policy flags are exact booleans.
- Each individual rule has focused coverage, including disabled/allowed policy behavior.
- Combined failures retain all six reasons in canonical order without duplicates.
- Empty reasons derive `is_eligible=True`; nonempty reasons derive `False`.
- Direct decision construction rejects missing, extra, reordered, duplicate, raw-string, or inapplicable reasons.
- Candidate, facts, policy, and reasons are defensively reconstructed into immutable decision state.
- Invalidly tampered frozen inputs fail closed with fixed redacted errors.
- `MemoryError`, `KeyboardInterrupt`, and other `BaseException` values are not wrapped.
- E1/E2A still accept and preserve zero quantity, zero price, and missing float as format-valid data.
- No item-name or paint-seed heuristic inference exists.
- No solver, risk filter, provider, cache, client, I/O, environment, task, thread, or runtime wiring is imported or called.
- Pipeline, scheduler, FastAPI, scanner, solver, and risk modules do not reverse-import eligibility.
- Full regression, Ruff, and Mypy pass.
- All three existing dry-runs retain their prior output and remain offline.
- No BUFF, SteamDT, or Redis connection occurs.
- `git diff --check` reports no actual whitespace error.
- The final diff contains exactly the seven approved files, with no generated, temporary, secret, staged, or worktree artifacts.
- No commit, push, or next phase occurs.
