# Phase 12E2A Requirements

## Scope

- Add `app/services/buff_listing_parser.py` with a pure mapping parser and a thin path loader.
- Add a project-owned synthetic `schema_version=1` JSON fixture under `tests/fixtures/buff/`.
- Return immutable `tuple[BuffListingObservation, ...]` values that remain compatible with `normalize_buff_listing()`.
- Importing the parser must not read files, environment settings, or create external/runtime state.

## Fixture contract v1

- Exact top-level fields: `schema_version`, `source`, `observed_at`, and `listings`.
- `schema_version` is exact integer `1`; bool is invalid.
- `source` is the exact canonical string `buff`.
- `observed_at` is a nonblank timezone-aware ISO-8601 string. `Z` and explicit offsets are accepted and normalized to UTC.
- `listings` is a JSON array; order and duplicates are retained.
- Exact required record fields: `listing_id`, `market_hash_name`, `price_cny`, and `quantity`.
- Optional record fields: `float_value`, `wear_name`, `paint_seed`, and `sticker_metadata`.
- `price_cny` and non-null `float_value` are JSON strings converted directly to `Decimal`; JSON numbers and bool are invalid.
- Sticker metadata is null or an array of exact `{ "key": string, "value": string }` objects, preserving order and duplicates.
- Missing and unknown fields fail closed. Schema changes require a new version rather than an implicit v1 change.

## Parsing and errors

- `parse_buff_listing_fixture()` accepts a `Mapping[str, object]` directly and performs no I/O.
- `load_buff_listing_fixture()` reads UTF-8 JSON and rejects malformed JSON and duplicate object keys before calling the mapping parser.
- A single `BuffListingParseError` exposes stable classification through safe `field`, optional zero-based `record_index`, and reason/cause metadata.
- JSON decode and fixture/domain errors are distinguishable by classification while public message and repr remain fixed and payload-safe.
- Do not retain a raw payload or original exception object/message.
- Catch ordinary parsing/domain failures only; do not catch `MemoryError`, `KeyboardInterrupt`, or other `BaseException` values.
- Any malformed record rejects the complete fixture; no partial tuple is returned.

## Data behavior

- Reuse `BuffListingObservation` construction for required-string, Decimal range, exact-int, optional wear, sticker-pair, and timestamp domain validation.
- Do not repair types, convert floats to Decimal, filter quantity zero, deduplicate listings, judge eligibility, compute prices/EV/risk/trade-ups, or access caches/providers.
- Defensive materialization must detach results from mutable input mappings/lists.

## Exclusions

- No BUFF HTTP client, endpoint, authentication, signature, login, Cookie, crawler, captcha handling, risk-control bypass, or automatic purchase.
- No SteamDT, Redis, planner, executor, resolver, provider, valuation, pipeline, scheduler, FastAPI, Discord, Docker, Alembic, PostgreSQL, config, or `.env` changes.
- No real or unclear-provenance BUFF payload is copied into the new fixture.
- No commit or push.
