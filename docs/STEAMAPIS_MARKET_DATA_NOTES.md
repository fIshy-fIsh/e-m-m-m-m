# SteamApis Market Data Notes

## Purpose

This document records the SteamApis Market Data WebSocket facts used by the project-owned Phase 13A Step 2A listing parser. It keeps provider documentation separate from internal identity and validation decisions so later transport and adapter phases do not invent fields or claim BUFF identifiers that the provider does not document.

## Official documentation

- https://docs.steamapis.com/market-data/websocket
- https://docs.steamapis.com/market-data/websocket/offers
- https://docs.steamapis.com/market-data/reference

A fresh read of all three official pages was attempted before implementation. The page-fetch tool was initially blocked by domain safety verification and official-domain search returned no usable excerpts. On the requested retry, read-only HTTP retrieval succeeded for all three official URLs. The endpoint/authentication/subscription page and offer field table/example confirmed the contract below directly; no third-party blog, reverse-engineering repository, private BUFF interface, captured credentials, or URL inference was used.

## Confirmed contract used by Step 2A

### WebSocket endpoint

```text
wss://marketplaceapi.steamapis.com/ws/v2/offers
```

### API-key query parameter

```text
?apiKey=...
```

Step 2A stores, reads, logs, or transmits no API key and creates no WebSocket client.

### Subscription

```json
{
  "subscribeTo": ["Buff163"],
  "games": ["CS2"],
  "newFloorOnly": false
}
```

### Message types

The documented message types used by this phase are:

- `subscribed`
- `offer`
- `error`

The parser additionally returns project-owned `ignored` results for supported business exclusions. `ignored` is not asserted to be a SteamApis wire message type.

### Offer envelope

A documented offer message contains:

- `type`
- `eventType`
- `marketplace`
- `game`
- `timestamp`
- `data`

The target values are exact `Buff163` and `CS2`. Documented event types supported here are exact `Added` and `Updated`.

### Offer data

The strict target-offer schema requires presence of the supplied documented keys:

- `name`
- `purchaseLink`
- `priceUSD`
- `priceEUR`
- `priceCNY`
- `priceRUB`
- `daysTradeLocked`
- `foundAt`
- `inspectLink`
- `float`
- `paintIndex`
- `paintSeed`
- `stickers`

Step 2A retains only CNY plus the requested listing geometry/provenance fields. USD, EUR, and RUB values are never converted, retained, or used as fallback.

### Timestamp units

- Envelope `timestamp`: Unix milliseconds.
- Data `foundAt`: Unix seconds.

The parser converts both by their named unit, without a magnitude heuristic, to timezone-aware UTC datetimes. The official table explicitly labels envelope `timestamp` as milliseconds. The offer example uses a second-scale `foundAt` value, matching the supplied Step 2A contract; the table itself describes `foundAt` only as a Unix timestamp.

### CNY and float

- `priceUSD` is a documented always-present number.
- `priceEUR`, `priceCNY`, and `priceRUB` are documented as number or null.
- `daysTradeLocked` is documented as number or null.
- `inspectLink`, `float`, `paintIndex`, `paintSeed`, and `stickers` are documented CS2-specific nullable fields.
- A present `priceCNY` must be a finite positive JSON number and is retained as `Decimal`.
- A present `float` must be a finite JSON number in inclusive `[0, 1]` and is retained as `Decimal`.
- Missing or null target CNY/float is a stable project-owned ignored outcome.
- No other currency is used to synthesize CNY.

### Stickers

Null stickers normalize to an empty tuple. Every retained sticker contains only:

- nonblank `name`
- finite `wear` in `[0, 1]`
- nonnegative integer `slot`

Malformed sticker entries fail the complete target offer. Unknown additional provider fields are tolerated and discarded.

### Purchase link

`purchaseLink` is retained as an opaque manual URL string. This phase:

- strips boundary whitespace only;
- does not request or open the link;
- does not canonicalize the URL;
- does not parse its path or query;
- does not infer marketplace identifiers from it;
- does not perform any purchase action.

## Undocumented identifiers and removal behavior

The supplied official contract does not publish:

- BUFF `goods_id`;
- BUFF `listing_id`;
- a stable marketplace offer ID;
- a removal/deleted event.

Step 2A therefore does not fabricate those identifiers and implements no removal, expiry, deletion, or pool semantics. Those concerns remain deferred to later explicitly specified phases.

## Project-owned source-local identity

`source_offer_id` is an internal opaque digest over:

```text
canonical_marketplace + "\x00" + canonical_game + "\x00" + stripped_purchase_link
```

The result is lowercase SHA-256 hex. It remains stable across Added/Updated messages and changed price, float, seed, or timestamp for the same opaque link.

It is explicitly **not**:

- a BUFF goods ID;
- a BUFF listing ID;
- a SteamApis-documented marketplace ID;
- evidence that an identifier was extracted from the URL.

The digest does not include an API key or other credentials and does not expose the purchase link itself.

## Parser boundary

`app/services/steamapis_listing.py` is a pure standard-library parser/domain module. It:

- accepts one JSON string;
- rejects duplicate keys at any object depth;
- tolerates unknown additional fields without storing raw data;
- distinguishes subscribed, offer, ignored, and server-error outcomes;
- uses fixed redacted parse failures;
- retains no raw payload, owner/seller/account data, alternate prices, API key, Authorization value, or Cookie.

This module is not a SteamApis client, not a BUFF official API contract, and not evidence of undocumented BUFF field mappings.

## Explicitly not implemented

Phase 13A Step 2A includes no:

- WebSocket/HTTP client or subscription sender;
- dependency installation;
- authentication/config/environment reading;
- retry, reconnect, heartbeat, task, thread, service, factory, or runtime;
- live candidate pool or removal behavior;
- `CandidateListing` adapter;
- metadata classification or facts provider;
- recipe solver, trade-up, EV, ROI, risk, SteamDT, Redis/cache, pipeline, scheduler, FastAPI, Discord, database, browser, or purchase behavior.

The parser is not production-ready. A later phase must re-check current official documentation in an environment that can access it before enabling any live transport.
