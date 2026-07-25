# Phase 12E3A — Requirements

## Context

Phase 12E2B accepts explicit `BuffListingEligibilityFacts` but deliberately has no provider. This phase adds an offline, project-owned metadata boundary that maps a candidate's exact listing identity to those existing facts without inference or runtime wiring. It supports the deterministic, traceable, read-only principles in `specs/mission.md` and the modular service boundary in `specs/tech-stack.md`.

No existing module owns this exact responsibility. Legacy skin metadata defaults/coerces classifications, carries no special-seed fact, and does not distinguish missing metadata from explicit false facts, so it is not reused as the authority for this contract.

## Scope and decisions

- Reuse `BuffTradableCandidate` as the lookup input and `BuffListingEligibilityFacts` as the found value.
- Add `BuffListingFactsRecord` with exactly `listing_id`, `market_hash_name`, `is_stattrak`, `is_souvenir`, and `has_special_seed`.
- Records, lookup results, and eligibility facts are immutable, keyword-only where constructed publicly, defensively reconstructed, and repr-safe.
- Identity strings are stripped and must remain nonempty. Case and internal whitespace remain significant.
- The three classification flags accept exact booleans only.
- Do not infer StatTrak or Souvenir from item names and do not infer special seed from `paint_seed`.
- Add `BuffListingFactsLookupStatus` with stable values `found` and `missing`.
- A lookup result contains status, the normalized queried listing ID and market name, and optional facts.
- `FOUND` requires facts; `MISSING` requires `facts=None`.
- Missing metadata never defaults to an all-false facts object.
- A known listing ID queried with the wrong canonical item name returns the same public `MISSING` shape as an unknown ID and never returns the stored facts.
- The async provider protocol exposes only `lookup_facts(candidate)`.
- `OfflineBuffListingFactsProvider` is constructed from records, performs no I/O or external work, consumes and defensively copies its input, and returns deterministic fresh lookup results.
- Duplicate canonical `(listing_id, market_hash_name)` records fail closed.
- One canonical listing ID associated with different canonical market names also fails closed.
- Duplicate identity and listing-ID collision have distinct stable causes with the same fixed redacted public message.

## Project-owned fixture v1

`tests/fixtures/buff/listing_facts_v1.json` is a synthetic contract owned by this project. It is not a BUFF official response or captured payload.

The top level has exactly:

- `schema_version`: exact JSON integer `1`; bool is invalid.
- `source`: exact canonical string `buff`.
- `records`: JSON array in source order.

Every record has exactly:

- `listing_id`
- `market_hash_name`
- `is_stattrak`
- `is_souvenir`
- `has_special_seed`

Missing and unknown fields fail closed. Record flags must be JSON booleans. Parsed order is preserved. The mapping parser cannot recover duplicate JSON keys already discarded by a decoder; the file loader detects duplicate keys at every JSON object level. No malformed record is skipped and no partial tuple is returned.

The fixture contains no seller or account data, Cookie, token, Authorization value, password, URL, inspect link, endpoint, credentials, or raw transport payload.

## Errors and confidentiality

- Public validation and parse messages are fixed and do not interpolate rejected data.
- Stable metadata may include `field`, zero-based `record_index`, and stable cause.
- Errors and public repr never reveal listing identities, market names, raw payloads, paths, seller information, secrets, URLs, or original exception text.
- Ordinary expected file, JSON, schema, and domain failures are classified with suppressed chaining.
- `MemoryError`, `KeyboardInterrupt`, and other `BaseException` values are not caught or wrapped.

## Approved file scope

Create:

- `app/services/buff_listing_facts.py`
- `tests/test_buff_listing_facts.py`
- `tests/fixtures/buff/listing_facts_v1.json`
- `specs/2026-07-25-buff-listing-facts/plan.md`
- `specs/2026-07-25-buff-listing-facts/requirements.md`
- `specs/2026-07-25-buff-listing-facts/validation.md`

Modify:

- `README.md`
- `docs/BUFF_LISTING_NOTES.md`

## Explicit exclusions

- No real BUFF API, adapter, endpoint, authentication, login, Cookie handling, crawler, captcha handling, browser automation, risk-control bypass, or market write.
- No SteamDT, Redis, cache, database, environment, configuration, Docker, or deployment connection.
- No eligibility orchestration, scanner, recipe solver, risk filter, valuation, provider, pipeline, scheduler, FastAPI, Discord, or runtime wiring.
- No provider call to the fixture parser or eligibility evaluator.
- No changes to existing BUFF domain, parser, fixture, or eligibility semantics.
- No changes to metadata, solver, risk, pipeline, scheduler, FastAPI, config, client, SteamDT, Redis, Docker, Alembic, PostgreSQL, Discord, or `docs/STEAMDT_API_NOTES.md` files.
- No roadmap status update, commit, push, or next phase.
