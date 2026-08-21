# Phase 13H-0 — Synthetic Trade-up Pipeline Integration — Validation

## Commands

```bash
py -3.13 -m pytest tests/test_trade_up_pipeline.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
git diff --check
git diff --name-only
git status --short
```

## Acceptance

- `TradeUpInputCandidate` flows into the existing trade-up engine via the new synthetic `candidates_to_input_items` adapter.
- `market_hash_name` is `None` by default and never inferred from other fields; unresolved or unknown names are skipped.
- The full synthetic pipeline (`calculate_tradeup_results` → `calculate_opportunity_metrics` → `evaluate_opportunity`) executes without raising on constructed fixtures.
- No live provider, no identity resolver, no BUFF endpoint, no SteamApis, no scanner/scheduler, no purchase flow, no Protected Core modification.

## Observed results

Validated entirely offline on Python 3.13:

```text
tests/test_trade_up_pipeline.py: 12 passed
Full pytest: 2848 passed, 23 skipped, 1 warning
Ruff: passed
Mypy app: no issues in 71 source files
git diff --check: passed
```

The full-suite warning is the existing Starlette TestClient / HTTPX deprecation warning. Real BUFF/SteamDT/SteamApis requests, live-smoke executions, Redis/Discord/PostgreSQL connections, scheduler/background work, login/session/Cookie actions, and purchase/market-write actions were all zero.
