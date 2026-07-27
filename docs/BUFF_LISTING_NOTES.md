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

## Phase 12E3A — Offline Listing Facts Provider

`tests/fixtures/buff/listing_facts_v1.json` is a second synthetic, versioned fixture owned by this project. It defines explicit classification metadata for offline tests only. It is **not** a BUFF official response, a captured live payload, a confirmed external metadata mapping, or evidence of an available endpoint.

Facts fixture v1 has the exact top-level fields `schema_version`, `source`, and `records`. The version is exact JSON integer `1` (bool is invalid), source is exact canonical `buff`, and records is an ordered JSON array. Every record has exactly `listing_id`, `market_hash_name`, `is_stattrak`, `is_souvenir`, and `has_special_seed`; the three flags must be JSON booleans. Identity strings are stripped and must remain nonempty, while case and internal whitespace remain significant.

The parser and file loader are strict and fail closed. Missing or unknown fields, malformed records, non-boolean flags, malformed JSON, duplicate JSON object keys, duplicate canonical `(listing_id, market_hash_name)` identities, and one listing ID associated with different canonical item names reject the complete fixture. Parsed order is preserved and no valid prefix is returned. The file loader can detect duplicate keys before decoding loses them; a caller-provided `Mapping` cannot recover decoder-discarded duplicates.

`OfflineBuffListingFactsProvider` is built only from immutable records and performs no I/O. It defensively reconstructs every record before publishing private state and independently enforces both uniqueness rules without last-write-wins behavior. `lookup_facts()` returns the existing `BuffListingEligibilityFacts` only when both candidate listing ID and canonical market name match. Unknown IDs and known IDs queried with the wrong name both return the same public `MISSING` status with `facts=None`, so unknown metadata is never treated as three safe false values and a name mismatch never receives another item's facts.

Classification is authoritative only because the synthetic metadata says so. The provider does not inspect or infer from item names, paint seeds, wear, price, quantity, float, stickers, or listing-ID syntax. A StatTrak- or Souvenir-shaped name can map to false facts, and an explicit special-seed fact does not require a numeric paint seed. The provider does not call the fixture parser or eligibility evaluator; Phase 12E3B is the isolated caller that composes a returned fact with the existing evaluator as a separate step.

Records, lookup results, and returned facts are immutable and defensively reconstructed. Fixed public errors retain only stable field/cause/index metadata and do not expose identities, rejected values, payloads, paths, seller data, credentials, URLs, or original exception text. The fixture contains no seller/account data, Cookie, token, Authorization value, password, URL, inspect link, endpoint, or raw transport field.

There is no real BUFF facts adapter and E3A itself has no eligibility orchestration. The E3B service below adds only isolated qualification composition; neither phase is connected to solver, pipeline, scheduler, FastAPI, provider, valuation, SteamDT, Redis, cache, Discord, or production runtime. This offline seam is not production-ready. Breaking changes to facts fixture v1 require a new explicit schema version.

## Phase 12E3B — Listing Qualification Service Core

`BuffListingQualificationService` is a thin single-candidate orchestration boundary. It accepts the existing `BuffListingFactsProvider`, optionally accepts an evaluator callable that defaults to `evaluate_buff_listing_eligibility()`, and calls those collaborators in order. It owns neither collaborator, performs no setup or cleanup, and does not duplicate facts, policy, reasons, or eligibility rules.

Candidate and policy inputs are validated and defensively snapshotted before any collaborator call. The provider is awaited exactly once with a detached candidate. Its result must be the exact existing `BuffListingFactsLookupResult`, must satisfy the existing `FOUND`/`MISSING` facts invariant, and must bind both canonical listing ID and market name to the current candidate. A valid `MISSING` result is a normal `MISSING_FACTS` outcome with `decision=None`; it is not rejection, does not call the evaluator, and never creates an all-false facts object.

A valid `FOUND` result calls the existing or injected evaluator exactly once with detached candidate, facts, and policy. The returned value must be the exact existing `BuffListingEligibilityDecision` and must match the current candidate, found facts, and policy. Its canonical reasons remain owned by the existing eligibility module. No reasons derives `QUALIFIED`; one or more reasons derives `REJECTED`. Qualification status is not stored or accepted by the constructor, so contradictory caller-supplied status cannot exist.

Qualification results are frozen, keyword-only, repr-suppressed defensive snapshots. Exact public model subclasses, non-result collaborator values, tampered nested state, identity mismatches, contradictory lookup/decision combinations, and mismatched decisions fail closed with fixed safe qualification validation. Public error text and repr retain no listing identity, market name, raw object, payload, reason, path, seller data, credential, URL, or nested exception text.

Provider and evaluator invocation errors are not converted into business outcomes or wrapped as validation failures; ordinary typed errors, resource failures, cancellation, and control-flow exceptions propagate unchanged. There is no retry, fallback, alternate provider, facts inference from names or paint seeds, environment/config read, file or network I/O, batch operation, task/thread creation, or background work.

This service is not reverse-wired into listing parsing, facts lookup, eligibility rules, scanner, solver, risk, valuation, pipeline, scheduler, FastAPI, Discord, BUFF, SteamDT, Redis, cache, or any runtime. There is no real metadata adapter or automatic purchase, and the seam is not production-ready.

## Phase 12E4A — Manual Offline Qualification Integration

`scripts/buff_listing_qualification_integration.py` is the first manual surface that executes the complete existing offline listing chain. It loads a strict listing fixture, normalizes every observation in fixture order, loads a strict facts fixture, builds `OfflineBuffListingFactsProvider`, uses one default `BuffListingEligibilityPolicy`, builds `BuffListingQualificationService`, and sequentially qualifies every candidate once. The command owns only this composition and its summary; parsing, normalization, lookup, facts, policy, reasons, and qualification semantics remain in their existing modules.

`tests/fixtures/buff/qualification_listings_v1.json` and `qualification_facts_v1.json` are dedicated project-owned synthetic integration inputs that reuse the existing schemas. They are not BUFF responses, captured market data, or evidence of an endpoint or field mapping. Four observations deliberately yield `QUALIFIED`, `REJECTED`, `QUALIFIED`, and `MISSING_FACTS`: the third observation repeats the first compound identity to prove that no listing is deduplicated, the rejected identity has explicit `is_stattrak=true` facts, and the missing identity has no facts record. Counts are therefore total 4, qualified 2, rejected 1, and missing facts 1.

The run result stores immutable ordered candidate and qualification-result tuples and derives all counts. Candidate order and duplicates remain intact. The command does not join identities itself, infer classification from a market name or paint seed, synthesize all-false facts, reorder reasons, retry, fall back, run concurrently, continue after failure, or publish a partial success result. `REJECTED` retains the existing canonical reasons, while `MISSING_FACTS` remains a normal separate business outcome with `facts=None` and `decision=None`.

Both direct and module entrypoints use repository-anchored fixture defaults and accept only explicit listing/facts fixture overrides. Importing the module reads no fixture or environment and creates no client, runtime, service, or task. Successful output includes fixed counts and ordered per-listing status/facts/reason fields; market names are credential/URL-redacted and JSON-escaped. Listing IDs, raw objects/payloads, facts objects, paths, credentials, URLs, exception messages, and tracebacks are never printed. Invalid CLI or non-file paths return 2, content or orchestration failures return 1 without partial output, complete runs return 0 even with rejection/missing facts, and interruption returns 130.

This milestone sends no BUFF or SteamDT request and uses no Redis. It has no BUFF endpoint, auth, Cookie, login, crawler, metadata fetch, scanner, solver, risk, valuation, pipeline, scheduler, FastAPI, Discord, background worker, or automatic purchase. It remains a synthetic manual integration check and is not production-ready.

## Phase 12E4B0 — Authoritative goods_id Contract Propagation

The newer listing domain now retains `goods_id` only when a source supplies it explicitly. `BuffListingObservation.goods_id` and `BuffTradableCandidate.goods_id` are optional solely for backward compatibility: `None` means no authoritative goods ID was present. A supplied string is detached, stripped, and must remain nonempty. The domain never derives it from listing ID, market name, paint seed, the literal source `buff`, a hash, or a placeholder.

Listing fixture schema v1 remains frozen and unchanged. Its exact record fields do not include `goods_id`, a v1 record that adds the field is rejected, and successfully parsed v1 observations have `goods_id=None`. Project-owned listing fixture schema v2 retains the same top-level contract and existing listing semantics but requires one nonblank string `goods_id` per record. Missing, unknown, wrong-type, and blank v2 values fail closed; malformed v2 never downgrades to legacy `None`. Fixture schema versions are internal offline contracts rather than BUFF API versions, and the synthetic v2 identifiers confirm no live response field or mapping.

`tests/fixtures/buff/listings_v2.json` and `qualification_listings_v2.json` are synthetic v2 examples. The repeated qualification identity carries the same goods ID in both observations, while unrelated identities use distinct IDs. The unchanged `qualification_facts_v1.json` still produces `QUALIFIED`, `REJECTED`, `QUALIFIED`, and `MISSING_FACTS` with counts 4/2/1/1. Facts schema and lookup identity remain listing ID plus market name only: goods ID is not a facts field, provider key, eligibility fact, policy rule, reason, or qualification-status input.

Normalization, eligibility decisions, qualification collaborator inputs, and returned qualification results preserve populated and legacy-null goods ID through defensive snapshots. The manual integration command now defaults to v2 listings and v1 facts, while an explicit v1 listing fixture still runs. Output never includes goods ID; a market name containing its non-null goods ID is completely redacted just like one containing its listing ID.

This prerequisite resolves the provenance gap found before the solver adapter. A later adapter may require both `QUALIFIED` status and a nonempty goods ID; E4B0 does not create that adapter, change `CandidateListing`, or execute the recipe solver. It adds no live BUFF client, endpoint, auth, Cookie, login, crawler, SteamDT, Redis, pipeline, scheduler, FastAPI, Discord, background work, or automatic purchase, and it is not production-ready.

## Existing Legacy Pipeline Mock

`tests/fixtures/pipeline/mock_buff_orders.json` is pre-existing synthetic pipeline input for the older `BuffSellOrder` mock path. It contains mock `seller_id`, inspect-link, raw-shaped fields, and JSON-number float values. It is not reused, copied, or treated as Phase 12E2A schema v1, and it is not evidence of an official BUFF response shape.

## Explicitly Not Implemented

Phase 12E2A/E2B/E3A/E3B/E4A/E4B0 add no live BUFF mapping, HTTP client behavior, endpoint, authentication, signature, login, Cookie handling, crawler, captcha handling, risk-control bypass, browser automation, or automatic purchase. E4A adds only a manual synthetic offline composition of the existing contracts; E4B0 adds only explicit project-owned goods-ID provenance and listing fixture v2 compatibility. These phases do not connect SteamDT or Redis and are not wired into provider, solver, valuation, pipeline, scheduler, FastAPI, Discord, config, or deployment.

An adapter for real BUFF payloads may only be designed after the project has a lawful, authorized, sanitized sample and confirmed official field semantics. Until then, all endpoint, authentication, request, response-field, and timestamp mapping questions remain tracked in `docs/BUFF_API_NOTES.md`. This fixture parser is not production-ready.
