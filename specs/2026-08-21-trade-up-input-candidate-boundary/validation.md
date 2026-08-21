# Phase 13E-0 — Trade-up Input Candidate Boundary — Validation

## Commands

```bash
py -3.13 -m pytest tests/test_trade_up_input_candidate.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
git diff --check
git diff --name-only
git status --short
```

## Acceptance

- `TradeUpInputCandidate` is created, tested, and documented without modifying any existing production module.
- `market_hash_name` is `None` by default and is never inferred from other fields.
- All validation errors are fixed-text fixed-context and never expose rejected values.
- The DTO contains no adapter, no resolver, no scanner, no solver, no valuation, no SteamDT/SteamApis integration.
- Existing BUFF provider behavior, Protected Core, and test suite remain unchanged.

## Observed results

Pending implementation and offline validation.
