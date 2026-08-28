# Phase 12D5C Validation

## Automated checks

```bash
py -3.13 -m pytest tests/test_steamdt_refresh_integration.py
py -3.13 -m pytest tests/test_steamdt_refresh_planner.py tests/test_steamdt_refresh_executor.py tests/test_steamdt_price_refresh_service.py tests/test_steamdt_price_snapshot_source.py tests/test_steamdt_cached_price_resolver.py tests/test_steamdt_refresh_integration.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
git diff --check
```

## Manual offline command checks

```bash
py -3.13 -m scripts.steamdt_refresh_integration --mode fake --item "AK-47 | Redline (Field-Tested)" --item "AWP | Asiimov (Field-Tested)" --item " AK-47 | Redline (Field-Tested) " --chunk-size 1 --max-concurrency 2
```

```bash
py -3.13 scripts/steamdt_refresh_integration.py --mode fake --item "AK-47 | Redline (Field-Tested)" --item "AWP | Asiimov (Field-Tested)" --chunk-size 2 --max-concurrency 2
```

Both commands must exit 0, identify synthetic data, preserve planner ordering and deduplication counts, select from the shared cache, report zero SteamDT requests, and report no Redis usage.

## Acceptance audit

- Importing the command has no environment, client, network, task, or Redis side effects.
- Fake mode cannot read credentials or construct external runtimes.
- Disabled live mode exits 2 with zero runtime and request activity.
- Injected live runtime tests prove the complete chain and ownership close behavior without network access.
- Item failures return a complete safe report and exit 1; `NO_CANDIDATES` returns normal success.
- Request counts accept only exact nonnegative integers and otherwise print `unavailable`.
- Cancellation propagates after cleanup, never enters resolution, and emits no partial summary.
- Pipeline and scheduler behavior remain unchanged and do not import the command.
- No test or validation command connects SteamDT or Redis.
- The real enabled live integration is intentionally not run in this phase.
- `git diff --stat` and `git status --short` show only approved scope; nothing is staged, committed, or pushed.
