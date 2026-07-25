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

## Phase 12E2B — Listing Eligibility Filter Core

`BuffListingObservation` and `BuffTradableCandidate` express format-valid data only. `BuffListingEligibilityDecision` is the separate immutable result that expresses whether a normalized candidate may proceed toward a future solver. E1/E2A continue to permit quantity zero, zero price, and a missing float; E2B classifies those values according to an explicit policy rather than changing their domain or fixture validity.

The caller must provide `BuffListingEligibilityFacts` with exact boolean `is_stattrak`, `is_souvenir`, and `has_special_seed` values. The evaluator treats these facts as authoritative and never infers them from market names, paint seeds, wear, stickers, or listing identifiers. A listing may therefore have a StatTrak- or Souvenir-shaped name without being classified as one, and a known-looking paint seed is not special unless the caller says so. There is no real facts provider in this phase.

The default immutable policy requires:

- `min_available_quantity=1`;
- a positive buy price;
- a present float value;
- explicitly marked StatTrak, Souvenir, and special-seed listings to be excluded.

Each applicable reason is retained in the fixed order: insufficient quantity, non-positive price, missing float, StatTrak disallowed, Souvenir disallowed, then special seed disallowed. The stable reason values use lowercase snake case. `is_eligible` is derived and true exactly when the immutable reason tuple is empty.

Facts, policy, and decision models are frozen, keyword-only, and repr-suppressed. Decision construction defensively reconstructs the candidate, facts, and policy and recomputes the complete canonical reason tuple, rejecting duplicate, missing, extra, reordered, raw-string, or inapplicable reasons. Validation uses fixed safe text and never renders listing contents, rejected values, credentials, URLs, or nested exception messages.

This filter does not call or alter the legacy scanner, recipe solver, opportunity risk filter, metadata providers, valuation, pipeline, scheduler, FastAPI, Discord, BUFF, SteamDT, Redis, or cache. It does not calculate EV, recipes, risk, price value, or trade-up results. It has no environment/config reads or runtime wiring and is not production-ready.

## Existing Legacy Pipeline Mock

`tests/fixtures/pipeline/mock_buff_orders.json` is pre-existing synthetic pipeline input for the older `BuffSellOrder` mock path. It contains mock `seller_id`, inspect-link, raw-shaped fields, and JSON-number float values. It is not reused, copied, or treated as Phase 12E2A schema v1, and it is not evidence of an official BUFF response shape.

## Explicitly Not Implemented

Phase 12E2A/E2B add no live BUFF mapping, HTTP client behavior, endpoint, authentication, signature, login, Cookie handling, crawler, captcha handling, risk-control bypass, browser automation, or automatic purchase. They do not connect SteamDT or Redis and are not wired into provider, valuation, pipeline, scheduler, FastAPI, Discord, config, or deployment.

An adapter for real BUFF payloads may only be designed after the project has a lawful, authorized, sanitized sample and confirmed official field semantics. Until then, all endpoint, authentication, request, response-field, and timestamp mapping questions remain tracked in `docs/BUFF_API_NOTES.md`. This fixture parser is not production-ready.
