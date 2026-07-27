# Phase 12E4B — Requirements

## Context and ownership

Phase 12E4B0 preserved an explicitly supplied authoritative `goods_id` through the project-owned BUFF listing and qualification contracts. Phase 12E4B adds only the isolated boundary from one existing `BuffListingQualificationResult` to the existing solver-facing `CandidateListing`.

The qualification module continues to own facts, policy, eligibility reasons, status derivation, defensive snapshots, and collaborator orchestration. `CandidateListing` remains owned by the legacy market-scanner module. The recipe solver and `SkinMetadata` retain their existing responsibilities. This phase introduces no parallel model or duplicated business policy.

## Public API

Create:

```python
class BuffListingSolverAdapterError(ValueError):
    ...


def adapt_qualified_buff_listing(
    qualification_result: BuffListingQualificationResult,
) -> CandidateListing:
    ...
```

The error message is always exactly:

```text
invalid BUFF listing solver adapter contract
```

The function accepts only the exact `BuffListingQualificationResult` type. Subclasses and all other objects fail closed.

## Revalidation and accepted state

The adapter first rebuilds the result through the existing public `BuffListingQualificationResult` constructor. This provides an independent validated snapshot and rechecks the existing nested qualification contract without importing or copying private qualification helpers.

After reconstruction, all of these conditions are required:

- status is exactly `QUALIFIED`;
- lookup status is exactly `FOUND`;
- lookup facts exist;
- a decision exists and `is_eligible` is true;
- result candidate equals decision candidate;
- result policy equals decision policy;
- lookup facts equal decision facts;
- candidate `goods_id` is non-null and therefore explicitly authoritative;
- candidate float is non-null;
- candidate available quantity is at least the result policy's `min_available_quantity`.

`REJECTED`, `MISSING_FACTS`, legacy-v1 `goods_id=None`, missing float, wrong types, and tampered or inconsistent snapshots fail closed. The adapter returns no `None` or skip outcome.

The adapter does not invoke a facts provider, eligibility evaluator, qualification service, metadata service, or recipe solver.

## Field mapping

The adapter constructs the existing `CandidateListing` with this exact mapping:

| `CandidateListing` field | Source or explicit value |
| --- | --- |
| `goods_id` | `candidate.goods_id` |
| `listing_id` | `candidate.listing_id` |
| `market_hash_name` | `candidate.market_hash_name` |
| `price_cny` | `candidate.buy_price_cny` |
| `float_value` | one checked `float(candidate.float_value)` conversion |
| `paint_seed` | `candidate.paint_seed` |
| `inspect_link` | `None` |
| `source` | `"buff"` |
| `scanned_at` | `candidate.observed_at` |
| `raw` | `None` |

`buy_price_cny` remains a `Decimal` and never passes through float. The converted float must be finite and within inclusive `[0.0, 1.0]`. Conversion is not rounded, clamped, formatted, or repeated; it is only a compatibility boundary for the existing float-based solver contract.

`available_quantity` is checked but is not expanded into multiple candidates. Wear, stickers, facts, policy, reasons, seller data, account data, Cookie, token, URL, inspect link, and raw transport data are not stored in `CandidateListing`.

The adapter never derives `goods_id` from listing ID, market name, paint seed, the literal source, a placeholder, a hash, metadata, or a network lookup.

## Destination and solver responsibilities

The existing `CandidateListing` requires nonblank goods/listing IDs, nonnegative Decimal price, an optional float in `[0, 1]`, and a timezone-aware scan timestamp. The adapter supplies every destination field legally and explicitly.

The recipe solver reads market name, float, price, paint seed, and listing ID. It does not read goods ID, inspect link, source, scan time, or raw data, although the destination contract still requires a goods ID. `SkinMetadata` remains authoritative for StatTrak, Souvenir, collection, rarity, and item float-range metadata. The adapter does not copy qualification facts into the candidate or reconcile them with metadata.

## Determinism and errors

Every successful call returns a newly constructed existing `CandidateListing`. Repeated adaptation of the same valid input is deterministic and does not mutate the supplied qualification result.

All ordinary validation, reconstruction, conversion, comparison, property, and destination-construction errors become the fixed `BuffListingSolverAdapterError` with no chained source text. `MemoryError` propagates unchanged. The adapter never catches `BaseException`, so `asyncio.CancelledError`, `KeyboardInterrupt`, and other control-flow exceptions propagate unchanged.

Public error text and repr do not include goods ID, listing ID, market name, price, float, rejection reasons, raw object text, nested exception text, Cookie, Bearer value, token, password, Redis URL, or other secret-shaped data.

## Approved file scope

Create:

- `app/services/buff_listing_solver_adapter.py`
- `tests/test_buff_listing_solver_adapter.py`
- `specs/2026-07-27-buff-listing-solver-adapter/plan.md`
- `specs/2026-07-27-buff-listing-solver-adapter/requirements.md`
- `specs/2026-07-27-buff-listing-solver-adapter/validation.md`

Modify:

- `README.md`
- `docs/BUFF_LISTING_NOTES.md`

## Explicit exclusions

This phase does not modify or execute:

- BUFF listing, parser, facts, eligibility, or qualification implementations;
- `CandidateListing`, market scanner, recipe solver, trade-up engine, metadata, risk, or valuation;
- direct BUFF HTTP/client/auth/login/Cookie/crawler calls or imports; the required existing `CandidateListing` remains defined in the legacy market-scanner module, whose transitive import graph includes `BuffClient`, but adapter import and execution instantiate no client and perform no network work;
- SteamDT, Redis, cache, limiter, retry, fallback, or background work;
- pipeline, scheduler, FastAPI, config, environment, Docker, database, Discord, or deployment;
- automatic purchase or any market write;
- roadmap, SPEC, API notes, fixtures, or earlier feature specs.

There is no batch adapter, quantity expansion, deduplication, solver execution, scanner/pipeline wiring, live BUFF response mapping, or production readiness. No commit or push is permitted unless separately requested.
