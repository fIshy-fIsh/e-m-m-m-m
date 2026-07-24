# BUFF Listing Notes

## Phase 12E2A — Project-Owned Offline Fixture Contract

`tests/fixtures/buff/listings_v1.json` is a synthetic, versioned fixture owned by this project. It exists only for offline parser and integration tests. It is **not** a BUFF official API response, a captured live payload, or evidence of a confirmed BUFF endpoint/field mapping.

Fixture schema v1 has the exact top-level fields:

- `schema_version`: exact JSON integer `1` (bool is invalid)
- `source`: exact canonical string `buff`
- `observed_at`: one timezone-aware ISO-8601 string for every listing in the fixture; `Z` and explicit offsets are accepted and normalized to UTC
- `listings`: ordered JSON array

Each listing requires `listing_id`, `market_hash_name`, `price_cny`, and `quantity`. It may include `float_value`, `wear_name`, `paint_seed`, and `sticker_metadata`. `price_cny` and non-null `float_value` must be JSON strings and are converted directly to `Decimal`; JSON numbers are rejected. Sticker entries are exact `{ "key": string, "value": string }` objects converted into immutable string pairs.

The parser is strict and fail-closed:

- missing and unknown fields are rejected;
- malformed JSON and duplicate JSON object keys are rejected by the file loader;
- unsupported schema versions, invalid source, malformed timestamps, wrong types, invalid Decimal values, invalid records, and malformed sticker entries reject the complete fixture;
- no malformed record is skipped and no partial tuple is returned;
- listing order and duplicate listing IDs are preserved;
- sticker order and duplicates are preserved;
- quantity zero is preserved;
- no listing deduplication or filtering is performed;
- mutable mappings/lists are defensively converted into immutable observations;
- raw payload data is not retained on observations.

`BuffListingParseError` uses one safe public error type with stable cause classification for JSON decode, file read, fixture schema, and domain validation failures. Public error text and repr never include rejected values, complete payloads, paths, credentials, Cookie/Authorization/token data, seller information, URLs, or nested exception messages.

Schema v1 must not be silently changed. A breaking fixture-contract change requires a new schema version and explicit parser support.

## Existing Legacy Pipeline Mock

`tests/fixtures/pipeline/mock_buff_orders.json` is pre-existing synthetic pipeline input for the older `BuffSellOrder` mock path. It contains mock `seller_id`, inspect-link, raw-shaped fields, and JSON-number float values. It is not reused, copied, or treated as Phase 12E2A schema v1, and it is not evidence of an official BUFF response shape.

## Explicitly Not Implemented

Phase 12E2A adds no live BUFF mapping, HTTP client behavior, endpoint, authentication, signature, login, Cookie handling, crawler, captcha handling, risk-control bypass, browser automation, or automatic purchase. It does not connect SteamDT or Redis and is not wired into provider, valuation, pipeline, scheduler, FastAPI, Discord, config, or deployment.

An adapter for real BUFF payloads may only be designed after the project has a lawful, authorized, sanitized sample and confirmed official field semantics. Until then, all endpoint, authentication, request, response-field, and timestamp mapping questions remain tracked in `docs/BUFF_API_NOTES.md`. This fixture parser is not production-ready.
