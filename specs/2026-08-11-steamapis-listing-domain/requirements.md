# Phase 13A Step 2A — SteamApis Offer Domain + Strict Parser Requirements

## Purpose

Create a pure, deterministic boundary from one documented SteamApis WebSocket JSON message to an immutable project-owned SteamApis listing observation. This phase validates source data quality only. It does not connect a WebSocket or any external system and does not adapt observations into `CandidateListing`.

## Source contract and verification status

Official documentation URLs:

- `https://docs.steamapis.com/market-data/websocket`
- `https://docs.steamapis.com/market-data/websocket/offers`
- `https://docs.steamapis.com/market-data/reference`

The implementation contract below was re-verified immediately before final validation by read-only HTTP retrieval of the three official pages. The official offer field table and example confirm the endpoint, API-key query, subscription/message vocabulary, Added/Updated envelope, field names and nullability, millisecond message timestamp, and example second-scale `foundAt`. No third-party source, reverse engineering, private BUFF endpoint, or URL inference was used.

User-confirmed wire contract:

- WebSocket endpoint: `wss://marketplaceapi.steamapis.com/ws/v2/offers`
- API-key query parameter: `apiKey`
- Subscription:

  ```json
  {
    "subscribeTo": ["Buff163"],
    "games": ["CS2"],
    "newFloorOnly": false
  }
  ```

- Message types include `subscribed`, `offer`, and `error`.
- An offer envelope contains `type`, `eventType`, `marketplace`, `game`, `timestamp`, and `data`.
- Supported event types are exact `Added` and `Updated`.
- The target source is exact `Buff163` plus exact `CS2`.
- Documented offer data fields used for the strict schema are `name`, `purchaseLink`, `priceUSD`, `priceEUR`, `priceCNY`, `priceRUB`, `daysTradeLocked`, `foundAt`, `inspectLink`, `float`, `paintIndex`, `paintSeed`, and `stickers`.
- `timestamp` is Unix milliseconds; `foundAt` is Unix seconds.
- Each retained sticker has `name`, `wear`, and `slot`.
- The documentation currently does not publish a BUFF goods ID, BUFF listing ID, stable marketplace offer ID, or removal/deleted event.

## Selected decisions

- The three selected source-documentation facts above are used as supplied and the blocked re-fetch is documented rather than hidden.
- Offer messages use the full required envelope. `subscribed` and `error` use kind-specific minimum validation: an exact recognized `type` is sufficient, and additional fields are ignored.
- `SteamApisParsedMessage` is a strict immutable, keyword-only, repr-suppressed result with cross-field invariants.
- Unknown additional fields are tolerated at every known object level but never retained.
- Missing/null target CNY or float and non-target marketplace/game are explicit `IGNORED` business outcomes. Malformed present values and unsupported event/message kinds fail closed.

## Public API

All public symbols live in `app/services/steamapis_listing.py`:

```python
class SteamApisListingEventType(StrEnum):
    ADDED = "Added"
    UPDATED = "Updated"

class SteamApisMessageKind(StrEnum):
    SUBSCRIBED = "subscribed"
    OFFER = "offer"
    IGNORED = "ignored"
    ERROR = "error"

@dataclass(frozen=True, kw_only=True, repr=False)
class SteamApisSticker:
    name: str
    wear: Decimal
    slot: int

@dataclass(frozen=True, kw_only=True, repr=False)
class SteamApisListingObservation:
    source_offer_id: str
    event_type: SteamApisListingEventType
    marketplace: str
    game: str
    market_hash_name: str
    purchase_link: str
    inspect_link: str | None
    price_cny: Decimal
    float_value: Decimal
    paint_index: int | None
    paint_seed: int | None
    days_trade_locked: int | None
    found_at: datetime
    message_timestamp: datetime
    stickers: tuple[SteamApisSticker, ...]

@dataclass(frozen=True, kw_only=True, repr=False)
class SteamApisParsedMessage:
    kind: SteamApisMessageKind
    offer: SteamApisListingObservation | None = None
    ignore_reason: str | None = None

class SteamApisListingParseError(ValueError): ...

def parse_steamapis_message(payload: str) -> SteamApisParsedMessage: ...

def make_steamapis_source_offer_id(
    marketplace: str,
    game: str,
    purchase_link: str,
) -> str: ...
```

The four stable ignored reasons are:

- `other_marketplace`
- `other_game`
- `missing_price_cny`
- `missing_float`

## Model invariants

- All public dataclasses are exact frozen, keyword-only, repr-suppressed values and retain detached builtin strings/tuples only.
- Marketplace/game on an accepted observation are stored canonically as exact `Buff163` and `CS2`.
- Required strings are exact strings, stripped at their boundaries, and nonempty. Internal spacing/case is not rewritten.
- `price_cny` is a finite positive `Decimal`.
- `float_value` and sticker `wear` are finite `Decimal` values in inclusive `[0, 1]`.
- Paint index/seed and trade-lock days are exact nonnegative ints or `None`; sticker slot is an exact nonnegative int. Booleans are rejected.
- `inspect_link` is `None` or a stripped nonblank builtin string.
- Both times are aware UTC datetimes.
- Stickers are an exact tuple of exact `SteamApisSticker` values; order and duplicate occurrences are preserved.
- The source ID is a 64-character lowercase ASCII hexadecimal digest and must equal a recomputation from the accepted marketplace, game, and purchase link.
- Parsed-result invariant:
  - `OFFER`: offer present, ignore reason absent;
  - `IGNORED`: offer absent, one allowlisted ignore reason present;
  - `SUBSCRIBED`/`ERROR`: offer and ignore reason both absent.

## Source-local identity

`source_offer_id` is a project-owned, source-local, opaque identity. It is not:

- a BUFF goods ID;
- a BUFF listing ID;
- a SteamApis-documented marketplace ID;
- evidence of an ID encoded in the purchase URL.

The exact preimage is:

```text
canonical_marketplace + "\x00" + canonical_game + "\x00" + stripped_purchase_link
```

The public value is `sha256(preimage.encode("utf-8")).hexdigest()`.

The helper must not parse or URL-canonicalize the purchase link, extract path/query values, retain the full link inside the ID, or include price, float, seed, timestamp, API key, credentials, or other data. Added/Updated messages and price/float updates with the same link produce the same identity; a different link produces a different identity.

## Strict JSON behavior

- Input must be an exact builtin string.
- Decode once with `json.loads`, `parse_float=Decimal`, recursive duplicate-key rejection through `object_pairs_hook`, and rejection of nonstandard `NaN`/`Infinity` constants.
- The root must be an exact JSON object.
- Unknown additional fields are tolerated, because the third-party API may add fields; no unknown field is retained.
- Offer messages require the full envelope fields and an object `data`.
- A target offer requires every enumerated data key except that absence/null of `priceCNY` or `float` becomes the stable ignored outcome rather than a parse failure.
- Alternate currency fields must be present under the supplied strict schema and validated against their documented number/null shapes, but are not retained or used as CNY fallback.
- JSON integer tokens (excluding bool) and Decimal fractional tokens are accepted for CNY/float/sticker wear; values never pass through binary float.
- Paint/trade-lock/slot fields accept exact integer tokens only, with the documented nullable behavior.
- `timestamp` and `foundAt` accept finite, nonnegative JSON numeric tokens and are converted according to their fixed documented units, without magnitude heuristics.
- `stickers: null` becomes an empty tuple. Otherwise it must be an exact list of objects with required `name`, `wear`, and `slot`; malformed entries fail the entire offer atomically.
- No removal semantics are invented because no removal/deleted event is documented.

## Message semantics

- `subscribed` returns `SUBSCRIBED` and stores no server fields.
- A supported target offer returns `OFFER` with one observation.
- A structurally valid non-target offer or target offer missing/null target CNY/float returns `IGNORED` with one stable reason.
- `error` returns `ERROR`; any server error text is discarded and never reflected.
- Unknown message type or unknown offer event type fails closed with a typed parse error.

## Error and redaction contract

`SteamApisListingParseError` always renders:

```text
invalid SteamApis market message
```

It may retain only an allowlisted stable reason code such as `invalid_json`, `invalid_envelope`, `invalid_offer`, `invalid_timestamp`, `invalid_price`, `invalid_float`, `invalid_sticker`, or `unsupported_event`.

Public error text/repr/chaining and all public model reprs must not expose raw JSON, market names, purchase/inspect links, values, server error text, API keys, authorization data, Cookies, seller/account data, or nested exception text. Ordinary failures are translated with suppressed chaining. `MemoryError`, `KeyboardInterrupt`, cancellation, and other `BaseException` control flow are not caught.

## Retained and excluded data

The observation retains only the exact fields listed in its public contract. It does not retain:

- owner/seller/account information;
- raw payloads or unknown fields;
- API keys, query authentication, Authorization, or Cookies;
- USD, EUR, or RUB prices;
- a fabricated BUFF goods/listing ID;
- rarity, collection, StatTrak/Souvenir classification, special-seed classification, or metadata models.

## Approved repository scope

Create exactly:

- `app/services/steamapis_listing.py`
- `tests/test_steamapis_listing.py`
- `docs/STEAMAPIS_MARKET_DATA_NOTES.md`
- `specs/2026-08-11-steamapis-listing-domain/plan.md`
- `specs/2026-08-11-steamapis-listing-domain/requirements.md`
- `specs/2026-08-11-steamapis-listing-domain/validation.md`

Modify exactly:

- `README.md`

Do not change dependencies, config/environment, clients, `CandidateListing`, scanner, solver, trade-up/EV/risk, SteamDT, Redis/cache, metadata, Phase 12 BUFF modules, pipeline, scheduler, FastAPI, Discord, Docker/database, fixtures, roadmap, or deployment files.

## Execution boundaries and exclusions

This phase creates no WebSocket/HTTP client, subscription sender, runtime/factory/service, live pool, CandidateListing adapter, metadata lookup, solver execution, SteamDT valuation, Redis/cache connection, pipeline/scheduler/FastAPI/Discord wiring, database operation, background task, retry/reconnect behavior, browser operation, or purchase action. It installs no dependency and performs no external request. It is not production-ready and does not start Step 2B.
