# Phase 13E-0 — Trade-up Input Candidate Boundary — Requirements

## Purpose

Establish the internal boundary between `BuffListing` (provider output) and the future trade-up engine input boundary. The boundary is a single, minimal, immutable, repr-suppressed DTO that explicitly preserves unresolved identity and never guesses a `market_hash_name` from another field.

This phase does **not** implement:

- a resolver for `market_hash_name ↔ BUFF goods_id`;
- a scanner, scheduler, EV, ROI, or risk integration;
- a solver, valuation, or `InputItem` mapping;
- a new BUFF endpoint, mapper, or fixture;
- a SteamApis, SteamDT, or metadata integration.

## Public API

`app/services/trade_up_input_candidate.py` exports exactly:

```python
TradeUpInputCandidateValidationError
TradeUpInputCandidate
```

### Validation error

`TradeUpInputCandidateValidationError(ValueError)` exposes only the allowlisted `field` value. The fixed message is `invalid trade-up input candidate contract`. No rejected value, payload, URL, or nested exception text is included.

### Candidate DTO

```python
@dataclass(frozen=True, kw_only=True, repr=False)
class TradeUpInputCandidate:
    listing_id: str
    goods_id: str
    market_hash_name: str | None
    price_cny: Decimal
    paintwear: Decimal
    asset_id: str
    source: str = "buff"
```

Validation rules:

- `listing_id`, `goods_id`, `asset_id`, `source`: exact built-in `str`, nonblank, already canonical (no padding).
- `market_hash_name`: `None` or exact nonblank already-canonical `str`. `None` is the explicit unresolved-identity marker and is the default factory state.
- `price_cny`: exact `Decimal`, finite, greater than zero.
- `paintwear`: exact `Decimal`, finite, in inclusive `[0, 1]`.
- `source` default is `"buff"`; callers may not relabel it to imply a different authority.

The DTO validates scalar shape only. It does not prove that `market_hash_name` and `goods_id` are semantically related. It does not look up a canonical name.

## Boundary placement

```
BUFF Listing Provider
    BuffListing
        ↓ (later, identity-resolved adapter)
TradeUpInputCandidate
        ↓ (future)
Trade-up Engine
```

A future identity-resolved adapter will map `BuffListing` plus a verified identity source into `TradeUpInputCandidate`. This phase does not include that adapter.

## Required tests

- exact public exports, field order, and keyword-only construction;
- frozen and repr-suppressed behavior; rejected values never appear in `repr(candidate)` or error text;
- `market_hash_name` defaults to `None` and accepts exact nonblank values when supplied;
- `price_cny` accepts positive finite `Decimal` and rejects nonpositive, nonfinite, or non-Decimal values;
- `paintwear` accepts finite `[0, 1]` `Decimal` and rejects out-of-range or nonfinite values; boundary values `0` and `1` are valid;
- every padded string and every wrong built-in type is rejected with the allowlisted field;
- the error has no `__cause__` and no `__context__`;
- the DTO never imports, calls, or references the BUFF provider, identity resolver, scanner, solver, EV/ROI, risk, valuation, SteamDT, SteamApis, metadata, or purchase code.

## Architecture decision

This is a contract-only phase. No `BuffListing → TradeUpInputCandidate` adapter is added now. The boundary is established by the DTO's existence and contract. Identity resolution remains a separate, later phase.

## Protected scope

Do not modify `BuffListing`, the anonymous client/provider/smokes, Phase 12 BUFF modules, SteamDT, SteamApis, metadata, scanner, solver, trade-up engine, EV/ROI, risk, valuation, pipeline, scheduler, config, `.env.example`, dependencies, or any live smoke.

## Allowed files

- `app/services/trade_up_input_candidate.py`
- `tests/test_trade_up_input_candidate.py`
- `specs/2026-08-21-trade-up-input-candidate-boundary/{plan,requirements,validation}.md`
- minimal AI context handoff update

## Validation

```bash
py -3.13 -m pytest tests/test_trade_up_input_candidate.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
git diff --check
git diff --name-only
git status --short
```

No live request, no provider call, no SteamApis connection, no scheduler activation, no purchase, no market-write.
