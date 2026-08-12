# Phase 13A Step 2B — SteamApis Candidate Adapter Requirements

## Purpose

Add one pure boundary from the existing immutable `SteamApisListingObservation` to the existing source-agnostic solver input `CandidateListing`. This phase does not create transport, pooling, metadata, solving, valuation, alerts, or purchase behavior.

## Existing destination contract

`CandidateListing` currently contains:

```python
goods_id: str
listing_id: str
market_hash_name: str | None
price_cny: Decimal
float_value: float | None
paint_seed: int | None
inspect_link: str | None
source: str
scanned_at: datetime
raw: dict[str, Any] | None
```

It requires nonblank goods/listing identity strings, nonnegative CNY price, an optional float in inclusive `[0, 1]`, and an aware scan timestamp. The adapter must supply every field explicitly and must not rely on the destination's class-definition-time `scanned_at` default.

The current recipe solver reads market name, price, float, paint seed, and listing ID. Listing ID is only its final deterministic selection tie-break. It does not read goods ID, source, inspect link, scan timestamp, or raw data. Metadata remains authoritative for collection, rarity, StatTrak, Souvenir, and item float bounds.

## Public API

Create in `app/services/steamapis_candidate_adapter.py`:

```python
class SteamApisCandidateAdapterError(ValueError):
    ...


def adapt_steamapis_listing_to_candidate(
    observation: SteamApisListingObservation,
) -> CandidateListing:
    ...
```

The function accepts only the exact `SteamApisListingObservation` type; subclasses and all other objects fail closed.

The error always renders exactly:

```text
invalid SteamApis candidate adapter contract
```

It has no public reason code or field value.

## Revalidation

Before mapping, the adapter rebuilds a fresh `SteamApisListingObservation` through its public constructor using every public field. This reuses, without duplicating parser logic, the existing checks for:

- exact canonical marketplace `Buff163`;
- exact canonical game `CS2`;
- valid source-local SHA-256 identity and recomputation from the opaque purchase link;
- exact event and field types;
- nonblank market/purchase/optional inspect strings;
- finite positive Decimal CNY;
- finite Decimal float in inclusive `[0, 1]`;
- exact optional paint/trade-lock integers;
- aware UTC-normalized timestamps;
- exact defensively rebuilt sticker tuple.

Manually constructed inconsistent values and frozen-object tampering fail closed. The adapter does not parse raw JSON or import private Step 2A helpers.

## Source-local CandidateListing identity

SteamApis does not document BUFF `goods_id`, BUFF `listing_id`, or a stable marketplace offer ID. The adapter therefore builds one explicit project-owned compatibility identity:

```text
steamapis:buff163:<observation.source_offer_id>
```

Exact mapping:

```text
goods_id   = "steamapis:buff163:" + source_offer_id
listing_id = "steamapis:buff163:" + source_offer_id
source     = "steamapis:buff163"
```

The two destination IDs are:

- not a BUFF goods ID;
- not a BUFF listing ID;
- not a SteamApis-documented marketplace ID;
- not evidence of an ID encoded in the purchase URL.

They only satisfy the existing source-agnostic `CandidateListing` contract and provide a deterministic join key for a later pool. The adapter does not parse, canonicalize, open, or request the purchase link; extract path/query values; hash again; or derive identity from market name, price, float, seed, event, or timestamp. The identity must never be passed into the strict Phase 12 BUFF domain as authoritative BUFF identity.

## Field mapping

| `CandidateListing` field | Source or explicit value |
| --- | --- |
| `goods_id` | `steamapis:buff163:<source_offer_id>` |
| `listing_id` | same source-local identity |
| `market_hash_name` | `observation.market_hash_name` |
| `price_cny` | `observation.price_cny` unchanged |
| `float_value` | one checked direct Decimal-to-float conversion |
| `paint_seed` | `observation.paint_seed` |
| `inspect_link` | `observation.inspect_link` |
| `source` | `steamapis:buff163` |
| `scanned_at` | `observation.message_timestamp` |
| `raw` | `None` |

`message_timestamp` represents the current Added/Updated observation and is therefore used instead of the original provider discovery time `found_at`.

The documented inspect link is preserved, including `None`. It is not replaced by the purchase link.

## Decimal and legacy float boundary

`price_cny` remains the exact validated Decimal object. It is never converted through float.

Before converting the observation float, the adapter explicitly verifies that the Decimal is finite and in inclusive `[0, 1]`. It then performs exactly one direct Decimal-to-float conversion. The result must be a finite builtin float in inclusive `[0.0, 1.0]`.

The adapter does not round, clamp, format, stringify, or repeat the conversion. This is only the compatibility boundary for the existing float-based `CandidateListing` and solver.

## Purchase-link provenance

The purchase link remains solely on `SteamApisListingObservation`. It is never stored in candidate inspect link, raw data, goods/listing identity, source, market name, or any parallel DTO.

A later live-pool phase may retain observations and join:

```text
source_offer_id → purchase_link
```

This phase creates no pool or manual-link DTO. Adaptation does not mutate or strip the source observation, so its purchase provenance remains available to that later owner.

## Errors and redaction

All ordinary exact-type, property access, reconstruction, identity, conversion, and destination-construction failures become a fresh `SteamApisCandidateAdapterError` with the fixed text and suppressed chaining.

`MemoryError` propagates unchanged. The adapter does not catch `BaseException`, so `asyncio.CancelledError`, `KeyboardInterrupt`, and other control-flow exceptions propagate unchanged.

Public adapter errors contain no source offer ID, purchase/inspect link, market name, price, float, paint seed, raw data, server/nested exception text, API key, Authorization/Cookie, token, password, seller/account data, or other secret-shaped value.

## Determinism and retained data

Each successful call creates a new existing `CandidateListing`. Repeated adaptation of equal valid observations is deterministic. The supplied observation is not modified.

The candidate does not retain event type, marketplace/game fields, purchase link, paint index, trade-lock days, found time, stickers, alternate prices, provider payload, seller/account data, credentials, or secrets.

## Why the Phase 12 BUFF adapter is not reused

`adapt_qualified_buff_listing()` accepts only exact qualified BUFF results and requires validated facts, eligibility policy/decision, quantity, lookup status, and an authoritative BUFF goods ID. It hardcodes BUFF source semantics and maps a different observation timestamp. SteamApis observations provide none of those Phase 12 qualification contracts. Manufacturing them would fabricate BUFF semantics, so Step 2B uses a sibling adapter and leaves all Phase 12 modules unchanged.

## Approved file scope

Create:

- `app/services/steamapis_candidate_adapter.py`
- `tests/test_steamapis_candidate_adapter.py`
- `specs/2026-08-11-steamapis-candidate-adapter/plan.md`
- `specs/2026-08-11-steamapis-candidate-adapter/requirements.md`
- `specs/2026-08-11-steamapis-candidate-adapter/validation.md`

Modify:

- `README.md`
- `docs/STEAMAPIS_MARKET_DATA_NOTES.md`

## Explicit exclusions

Do not modify or execute:

- `steamapis_listing.py`, `CandidateListing`, market scanner, recipe solver, or Phase 12 BUFF adapters/domains;
- WebSocket/HTTP client, dependency, subscription, authentication, retry, reconnect, live pool, removal semantics, service, factory, background task, or runtime wiring;
- metadata, trade-up, EV/ROI/risk, SteamDT, Redis/cache, pipeline, scheduler, FastAPI, Discord, Docker/database, config/environment, or fixtures;
- browser activity, automatic login, Cookie capture, CAPTCHA/risk-control bypass, automated purchasing, or any market write.

The adapter is not production-ready. No commit or push is allowed, and Step 2C must not begin.
