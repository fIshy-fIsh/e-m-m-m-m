# Phase 12E4B0 — Requirements

## Context and ownership

Phase 12E4B found that the existing solver-facing `CandidateListing` requires a nonempty BUFF `goods_id`, but the newer BUFF listing and qualification contracts do not carry one. This phase closes only that provenance gap. It does not implement the solver adapter.

`goods_id` is authoritative only when an upstream source or project-owned fixture supplies it explicitly. The implementation must never derive it from listing ID, market name, paint seed, source name, hashes, placeholders, or network lookup.

## Domain contract

`BuffListingObservation` and `BuffTradableCandidate` gain keyword-only `goods_id: str | None = None` fields.

- `None` means legacy or unknown; no authoritative goods ID was supplied.
- A supplied value must be a string, is defensively detached and stripped, and must remain nonempty.
- Blank, whitespace-only, and non-string values fail with the existing safe listing validation error for `goods_id`.
- Both models remain frozen, keyword-only, and repr-suppressed.
- `normalize_buff_listing()` preserves normalized goods ID without requiring it for format validity or applying solver eligibility.

## Listing fixture schemas

Listing fixture schema version 1 remains unchanged:

- A v1 record does not permit `goods_id`.
- Parsing v1 explicitly produces `goods_id=None`.
- Existing v1 fixture files remain byte-unchanged.

Listing fixture schema version 2 retains the exact v1 top-level fields and existing listing fields but adds required per-record `goods_id`:

- `schema_version` is exact JSON integer `2`; bool is invalid.
- `goods_id` must be a JSON string and must remain nonempty after domain normalization.
- Missing, unknown, blank, and wrong-type values fail closed; malformed v2 never downgrades to `None`.
- Existing Decimal-string, timestamp, sticker, ordering, duplicate-listing, duplicate-JSON-key, and no-partial-result semantics remain unchanged.

Fixture schema versions are project-owned offline contracts, not BUFF API versions. Synthetic v2 values do not confirm an external response field or mapping.

## Snapshot propagation

Every existing reconstruction of `BuffTradableCandidate` must preserve goods ID:

- eligibility input and decision snapshots;
- qualification authoritative, provider, evaluator, decision, and result snapshots.

Full candidate equality includes goods ID. Result candidates and decision candidates therefore must match the authoritative input goods ID.

Goods ID is not:

- a facts-record or facts-lookup field;
- part of facts identity;
- an eligibility fact or policy rule;
- an ineligibility reason;
- a qualification status input.

The facts provider remains keyed only by canonical `(listing_id, market_hash_name)`. Candidates with that same pair and different goods IDs receive the same facts outcome.

## Synthetic fixtures

Create `tests/fixtures/buff/listings_v2.json` and `qualification_listings_v2.json` by retaining the existing synthetic record semantics and adding explicit synthetic goods IDs.

The repeated qualification observation uses the same goods ID as its first occurrence. Existing `qualification_facts_v1.json` remains unchanged and still yields ordered statuses:

1. `QUALIFIED`
2. `REJECTED`
3. `QUALIFIED`
4. `MISSING_FACTS`

Counts remain total 4, qualified 2, rejected 1, and missing facts 1.

No fixture may contain seller/account data, credentials, Cookie, Authorization, token, password, URL, inspect link, endpoint, or raw transport payload.

## Manual integration

The manual qualification command defaults to `qualification_listings_v2.json` and the unchanged `qualification_facts_v1.json`.

- Direct and module entrypoints retain the same output, ordering, counts, and exit codes.
- Explicit v1 listing fixtures still run and produce candidates with `goods_id=None`.
- Goods IDs are never printed.
- A market name containing its non-null candidate goods ID is completely redacted, matching the existing listing-ID fail-closed treatment.
- The command remains offline and does not call a solver.

## Approved files

Create:

- `specs/2026-07-26-buff-goods-id-contract/plan.md`
- `specs/2026-07-26-buff-goods-id-contract/requirements.md`
- `specs/2026-07-26-buff-goods-id-contract/validation.md`
- `tests/fixtures/buff/listings_v2.json`
- `tests/fixtures/buff/qualification_listings_v2.json`

Modify:

- `app/services/buff_listing.py`
- `app/services/buff_listing_parser.py`
- `app/services/buff_listing_eligibility.py`
- `app/services/buff_listing_qualification.py`
- `scripts/buff_listing_qualification_integration.py`
- the six existing BUFF listing/parser/facts/eligibility/qualification/integration test modules
- `README.md`
- `docs/BUFF_LISTING_NOTES.md`

## Explicit exclusions

This phase does not modify or implement:

- `CandidateListing`, market scanner, recipe solver, trade-up engine, or a solver adapter;
- facts implementation/schema/identity or existing facts fixtures;
- existing v1 listing fixtures;
- metadata, risk, valuation, pipeline, scheduler, FastAPI, config, Docker, database, Discord, or automatic purchase;
- BUFF client, HTTP, endpoint, login, Cookie, auth, crawler, captcha, risk-control bypass, or live mapping;
- SteamDT, Redis, cache, retry, fallback, tasks, threads, or background work;
- roadmap, SPEC, or either API-notes file.

The work remains offline, synthetic, not production-ready, uncommitted, and unpushed.
