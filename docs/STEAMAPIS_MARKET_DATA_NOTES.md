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

Step 2A therefore does not fabricate those identifiers or implement pool behavior. Step 2C adds only the project-owned local TTL and capacity policy documented below; it does not claim provider removal semantics.

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

## Step 2B CandidateListing compatibility boundary

`CandidateListing` is the project's existing source-agnostic solver input. The Step 2B adapter revalidates an exact observation and uses this explicit project-owned namespace to satisfy its mandatory identity fields:

```text
goods_id   = "steamapis:buff163:" + source_offer_id
listing_id = "steamapis:buff163:" + source_offer_id
source     = "steamapis:buff163"
```

These candidate values are **not** a BUFF goods ID, a BUFF listing ID, or a SteamApis-documented marketplace ID. They are a compatibility projection only. The adapter does not parse or canonicalize `purchaseLink`, extract its path/query, hash it again, or derive identity from market name, price, float, seed, event, or timestamp. It does not send the source-local values into the strict Phase 12 BUFF domain.

The remaining candidate projection is:

- `market_hash_name`, `paint_seed`, and documented `inspect_link` are preserved;
- `price_cny` remains the exact `Decimal`;
- the validated Decimal float is converted once to the existing legacy float contract and checked again;
- envelope `message_timestamp` becomes `scanned_at`, rather than the original `found_at` discovery time;
- `raw` is always `None`.

`purchaseLink` remains only on `SteamApisListingObservation`. Step 2C retains that observation in a bounded pool and joins `source_offer_id → purchase_link`; Step 2B creates no second manual-link DTO. Neither step creates a WebSocket client or dependency, metadata lookup, recipe solver execution, SteamDT/Redis call, runtime wiring, browser behavior, or purchase action, and neither is production-ready.

## Step 2C bounded in-memory offer pool

Step 2C retains exact `SteamApisListingObservation` values in an instance-local dictionary keyed only by project-owned `source_offer_id`. The observation remains the source of truth for current event state and opaque purchase provenance; `CandidateListing` values are derived on demand through the unchanged Step 2B adapter and are never cached alongside it.

Both Added and Updated may first-insert because a reconnect can expose an update before the local process has observed an add. For an existing ID, envelope `message_timestamp` alone determines ordering: newer replaces, older is ignored, identical equal-time input is idempotent, and differing equal-time content fails closed because there is no finer documented ordering authority. Event type itself does not override timestamp ordering.

The pool applies two project-owned local retention policies:

- positive TTL expiry occurs when `now - message_timestamp >= ttl` and is checked lazily on ingest, snapshot, provenance lookup, and candidate projection;
- positive `max_size` bounds the live set by repeatedly evicting oldest message timestamp, then lexical-ascending source ID at a tie.

TTL and capacity eviction are not marketplace removal events and do not assert that SteamApis or BUFF removed a listing. The documented contract still contains no Removed/Deleted event. Capacity never depends on price, float, market name, trade lock, or apparent profitability.

Immutable tuple-backed snapshots sort by market name, Decimal CNY, Decimal float, message timestamp, and source ID. Different source IDs remain distinct even when market names match. Provenance lookup supports only `source_offer_id → observation` and `source_offer_id → purchase_link`; it creates no reverse link index and never parses, requests, opens, logs, or otherwise interprets the link.

`daysTradeLocked` remains on the observation, including `None`, but Step 2C applies no eligibility filter and never interprets `None` as zero. Trade-lock policy is deferred to an explicit live eligibility/evaluation step.

Step 2C is synchronous local state only. It adds no WebSocket dependency/client, external connection, metadata classification, recipe solver execution, SteamDT, Redis, pipeline, scheduler, FastAPI, Discord, task/thread, browser behavior, or purchase action. It is not production-ready.

## Step 2D exact live metadata classification

Step 2D adds only this synchronous in-memory chain:

```text
SteamApisOfferPoolSnapshot
→ unchanged Step 2B CandidateListing adapter
→ exact SkinMetadata catalog lookup
→ eligible/rejected classification
→ solver-compatible rarity/mode buckets
```

The catalog receives already-normalized `SkinMetadata`; it does not invoke a provider, read a file or environment variable, or fetch metadata. Each record is detached with `raw=None`. Lookup remains exact and case-sensitive, and any duplicate exact market name fails the complete catalog instead of inheriting the current recipe solver's silent dictionary-comprehension last-wins behavior.

Every pool observation retains its own `source_offer_id` occurrence and is projected exactly once through Step 2B. Missing metadata is an explicit `metadata_not_found` rejection rather than a silent skip. The other structural rejection codes are `missing_collection`, `candidate_float_missing`, and `float_outside_skin_range`; skin float bounds are inclusive. No adjusted-float, recipe, output-probability, EV, ROI, risk, valuation, or profitability calculation runs here.

Eligible candidates are grouped by exact input rarity, StatTrak mode, and Souvenir mode. Collection is deliberately not part of this solver bucket identity: the existing trade-up solver may mix multiple collections in one same-rarity/mode ten-item recipe, while collection determines output topology and which candidate universes a later incremental scanner must reconsider. Each bucket therefore retains an exact `affected_collections` frozenset.

The opaque `purchaseLink` and `daysTradeLocked`, including `None`, remain only on the source observation/pool. `source_offer_id` is the sole join back to that provenance. Step 2D does not copy or interpret the purchase link, reject trade-locked offers, infer rarity/collection/StatTrak/Souvenir/special-seed facts from names or seeds, or treat an unknown trade lock as zero.

Step 2D creates no WebSocket/client/network, SteamApis/BUFF/SteamDT/Redis connection, solver invocation, provider runtime, pipeline, scheduler, FastAPI, Discord, task/thread, browser, login, marketplace write, or purchase action. It is an offline structural boundary and is not production-ready.

## Step 2E offline live recipe construction

Step 2E adds this synchronous synthetic chain:

```text
SteamApisOfferPoolSnapshot
→ Step 2D classification once
→ matching exact rarity/StatTrak/Souvenir bucket
→ construction-only recipe solver
→ selected CandidateListing listing-ID trace
→ exact LiveCandidateBinding source_offer_id mapping
```

The existing construction result intentionally contains normalized `InputItem` values rather than listing identity. Step 2E therefore adds a source-agnostic solver wrapper that retains the ten exact `CandidateListing.listing_id` values directly from the same selected internal pairs used to build those inputs. The existing `ConstructedRecipe` three-field contract, `construct_recipes()` output, and evaluated `solve_recipes()` flow remain compatible, and trade-up calculation is not repeated.

Live construction uses only Step 2D eligible bindings. It processes exact input rarity, StatTrak, and Souvenir buckets independently; `None` mode targets may match both boolean values but never combine them. Collection remains outside the bucket key so eligible candidates from multiple collections may enter one ten-input recipe. Exact input metadata and only same-mode next-rarity output metadata are supplied to construction.

Selected listing IDs map back through an exact index over the same bucket's `binding.candidate.listing_id`. Each resulting source ID comes from the matched binding's explicit `source_offer_id`. The integration does not strip or parse the project-owned `steamapis:buff163:` compatibility namespace, parse a purchase link, or match identity by market name, price, float, seed, or iteration order. Unknown, repeated, incomplete, or cross-bucket selected identity fails the complete operation.

The result stores only the complete classification, existing construction geometry, and ordered source IDs. The opaque `purchaseLink` remains solely on the original observation/pool and can be joined manually through `source_offer_id`; it is not copied into a recipe or result. Existing output `estimated_price_cny` values are still zero-valued metadata geometry placeholders, not SteamDT or live marketplace valuation, so this step produces no profitable-opportunity conclusion.

Step 2E does not call `solve_recipes()`, opportunity metrics, risk evaluation, or valuation. It installs no WebSocket dependency and creates no provider/client/network, SteamApis/BUFF/SteamDT/Redis/Discord connection, runtime/pipeline/scheduler/FastAPI/database integration, task/thread, browser/login, marketplace write, or purchase action. It is an offline synthetic integration and is not production-ready.

## Step 2F offline live recipe valuation

Step 2F starts only from the already-constructed Step 2E result:

```text
LiveRecipeConstructionResult
→ injected ValuationService once per recipe, sequentially
→ complete provider-quote and unchanged-geometry gate
→ existing calculate_opportunity_metrics()
→ existing evaluate_opportunity() with construction paint seeds
→ valued opportunity or stable valuation rejection
```

Every original output requires one exact aligned provider quote. A provider error, any declared or undeclared missing output, an existing keep/zero/drop fallback, or malformed/changed output geometry rejects the entire affected recipe before metrics or risk. The metadata zero price is never a live fallback, partial output probability is never evaluated, and no alternate source or currency is inferred. A trusted valuation can change only `estimated_price_cny` and `expected_value_contribution`.

EV, ROI, profit distributions, and fee handling remain authoritative in the existing metrics service and use `RecipeSolverConfig.sell_fee_rate`. Risk remains authoritative in the existing risk filter, receives the exact compact non-null paint seeds retained by construction rather than `None`, and produces an opportunity even when `passed` is false. Valuation rejection means incomplete or untrusted pricing; it does not mean a complete opportunity failed configured risk thresholds.

Selected source IDs remain exact and ordered in every final opportunity or rejection. The valuation module does not remap identity, access the offer pool, parse a URL, or copy `purchaseLink`; operators retain the Step 2E source-ID join to the original pool. Tests inject deterministic synthetic/fake price behavior only. This step creates no SteamDT client or real SteamDT/SteamApis/BUFF/Redis/WebSocket/Discord/network connection, no provider factory/cache/limiter, no runtime/pipeline/scheduler/FastAPI/database/background task, and no browser/login/marketplace write/purchase action. It deliberately leaves the legacy pipeline's existing fail-open valuation and `paint_seeds=None` reassessment unchanged and is not production-ready.

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
- metadata classification or facts provider;
- recipe solver, trade-up, EV, ROI, risk, SteamDT, Redis/cache, pipeline, scheduler, FastAPI, Discord, database, browser, or purchase behavior.

Step 2B adds only the isolated `SteamApisListingObservation`-to-`CandidateListing` adapter. Step 2C adds only the bounded local observation pool described above. Step 2D adds only detached exact metadata classification and solver-compatible bucket construction. Step 2E adds only offline construction and exact selected-source provenance mapping. Step 2F adds only injected offline complete valuation plus existing EV/risk evaluation. None adds excluded external or runtime behavior.

The parser is not production-ready. A later phase must re-check current official documentation in an environment that can access it before enabling any live transport.
