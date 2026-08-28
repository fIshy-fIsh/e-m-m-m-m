# Phase 12E4C — Validation

## Commands

```bash
py -3.13 -m pytest tests/test_buff_listing_qualification_integration.py
py -3.13 -m pytest tests/test_buff_listing_solver_adapter.py
py -3.13 -m pytest tests/test_buff_listing_solver_adapter_integration.py
py -3.13 -m pytest tests/test_buff_listing_qualification_integration.py tests/test_buff_listing_solver_adapter.py tests/test_buff_listing_solver_adapter_integration.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 -m scripts.buff_listing_solver_adapter_integration
py -3.13 scripts/buff_listing_solver_adapter_integration.py
py -3.13 -m scripts.buff_listing_solver_adapter_integration --listings-fixture tests/fixtures/buff/qualification_listings_v1.json --facts-fixture tests/fixtures/buff/qualification_facts_v1.json
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
git diff --name-status
git diff --stat
git status --short
```

## Acceptance criteria

- Git baseline was clean on `feature/steamdt-cache-rate-limit` at `4785896c419c3738d7558724f4f4dacc8be0bb87` before implementation.
- The integration calls the existing qualification runner exactly once and never repeats fixture parsing, normalization, facts lookup, eligibility, or qualification.
- Only exact `QUALIFIED` results reach `adapt_qualified_buff_listing()`, once each and in original order; `REJECTED` and `MISSING_FACTS` are normal skips and never reach the adapter.
- Qualified duplicate occurrences remain duplicated and ordered; quantity is neither expanded nor used for deduplication.
- The exact existing `CandidateListing` and adapter mapping are preserved without copying mapping logic.
- The result stores exactly the qualification run result and an exact tuple of solver candidates, is frozen/keyword-only/repr-suppressed, enforces exact types and adapted/qualified cardinality, and derives all five counts.
- Default v2 fixtures produce 4 qualification results, 2 qualified results, 2 adapted candidates, 1 skipped rejected, and 1 skipped missing facts.
- Explicit v1 listings reach a qualified null-goods-ID result, fail closed at adaptation, exit 1, and print no partial success summary.
- Any ordinary adapter/orchestration failure aborts immediately and is redacted; `MemoryError`, cancellation, and non-`Exception` control flow preserve their contract.
- Successful output lists only adapted index, safely rendered market name, source, and float-presence flag and includes solver/external-use attestations.
- Output contains no goods/listing ID, price, numeric float, seed, inspect/raw value, fixture path, exception text, traceback, object repr, credential-shaped value, or URL-shaped value.
- The existing market-name renderer is publicly renamed with no semantic change and both commands share it.
- Direct and module entrypoints return 0 with identical default output; invalid CLI/path returns 2; interruption maps to 130.
- Import performs no fixture/environment read, client/service/runtime/task construction, or external activity.
- Static and runtime tests prove no recipe solver, metadata lookup, pipeline, scheduler, FastAPI, client, SteamDT, Redis, network, background mechanism, or reverse runtime wiring is introduced.
- Full pytest, Ruff, Mypy, both CLI entrypoints, and all three existing dry-runs pass. `run_mock_pipeline.py` may execute its pre-existing solver path; the new integration path never invokes it.
- Exactly the nine approved paths change. No application module, fixture, API note, roadmap, runtime/config/deployment file, secret, or generated file changes.
- `git diff --check` reports no actual whitespace error.
- Work remains uncommitted and unpushed, and no next phase starts.
