# Phase 13D-0 — Validation

## Commands

```bash
py -3.13 -m pytest tests/test_buff_item_identity.py
py -3.13 -m pytest \
  tests/test_buff_item_identity.py \
  tests/test_buff_listing_provider.py \
  tests/test_buff_anonymous_listing_client.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
git diff --check
git diff --name-only
git diff --stat
git diff --cached --name-only
git status --short
```

## Acceptance

- No verified mapping is claimed or stored.
- The immutable DTO and async protocol expose only the frozen contract.
- Unresolved lookup is represented by `None` in test-local implementations.
- No current provider, listing DTO, client, smoke, metadata, solver, valuation, or runtime is modified or wired.
- Exactly seven approved paths differ and the index remains empty.
- All automated validation is offline with zero BUFF/SteamDT/SteamApis/provider/runtime activity.

## Observed results

Validated entirely offline on Python 3.13:

```text
tests/test_buff_item_identity.py: 21 passed
Focused identity/provider/client regressions: 66 passed
Full pytest: 2794 passed, 23 skipped, 1 warning
Ruff: passed
Mypy app: no issues in 69 source files
git diff --check: passed
```

The warning is the existing Starlette TestClient / HTTPX deprecation warning. No live BUFF or SteamDT request, SteamApis connection, mapping lookup, provider/runtime execution, Redis/database/Discord activity, scheduler/background work, login/Cookie action, or market write occurred.
