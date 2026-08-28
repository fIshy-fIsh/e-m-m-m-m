# Phase 13K-0 — Production Candidate Adapter Architecture Review (Requirements)

## Goal

Define the production boundary between the listing source and the canonical candidate → enrichment seam, without introducing any live wiring, identity resolver, or Protected Core change. The review freezes the future `BuffListing → TradeUpInputCandidate` adapter contract before any implementation begins.

## Functional Requirements

### FR-1 — Adapter location and dependencies

- FR-1.1 The adapter must live in `app/services/buff_listing_candidate_adapter.py`.
- FR-1.2 The adapter may import only: `app.services.buff_listing` (`BuffListing` DTO), `app.services.buff_listing_provider` (the `BuffListingProvider` protocol surface), `app.services.trade_up_input_candidate` (`TradeUpInputCandidate` + validation error).
- FR-1.3 The adapter must NOT import any module under `app.services.tradeup_engine`, `app.services.recipe_solver`, `app.services.ev_service`, `app.services.risk_filter`, `app.services.valuation_service`, `app.services.live_recipe_valuation`, `app.services.metadata_models`, `app.services.metadata_provider`, `app.services.metadata_service`, `app.services.live_metadata_catalog`, `app.services.trade_up_input_enrichment`, `app.jobs.scheduler`, `app.api.*`, `app.db.*`, `app.cache.*`, `app.webhook.*`, `app.services.scanner`.
- FR-1.4 The adapter must NOT import any of: `httpx`, `asyncio`, `requests`, `aiohttp`, `websockets`, `json`, `os.environ`, `open(`, `BUFF_*` env accessors, `SteamApis`, `steamdt`, `steamapis` modules.
- FR-1.5 The adapter does not own a `BuffListingProvider` instance; it accepts already-acquired `BuffListing` values.

### FR-2 — Public surface

- FR-2.1 `__all__` is the exact tuple: `("CandidateAdapterRejectionReason", "CandidateAdapterRejection", "BuffListingCandidateAdapter", "convert_buff_listing_to_candidate", "convert_buff_listings")`.
- FR-2.2 `CandidateAdapterRejectionReason` is a `StrEnum` with the closed set:
  - `MISSING_IDENTITY`
  - `MISSING_PRICE`
  - `INVALID_FLOAT`
  - `MISSING_ASSET_ID`
  - `UNSUPPORTED_SOURCE`
- FR-2.3 `CandidateAdapterRejection` is a frozen, kw-only, repr-suppressed dataclass with fields: `listing: BuffListing`, `reason: CandidateAdapterRejectionReason`. The `__repr__` and `__str__` forms must NOT expose any value field of the rejected listing (`listing_id`, `goods_id`, `market_hash_name`, `price_cny`, `paintwear`, `asset_id`).
- FR-2.4 `BuffListingCandidateAdapter` is a `Protocol` with one method `convert(listing: BuffListing) -> TradeUpInputCandidate | CandidateAdapterRejection`.
- FR-2.5 `convert_buff_listing_to_candidate(listing)` is the synchronous default implementation; it never raises for the five documented rejection reasons. It raises `TypeError` only when given a non-`BuffListing` argument.
- FR-2.6 `convert_buff_listings(listings)` returns the kept candidates in input order; rejected listings are dropped (the caller's responsibility to keep rejection histograms). It does not raise.

### FR-3 — Candidate construction contract

- FR-3.1 On success, the adapter returns a `TradeUpInputCandidate` with these fields sourced from `BuffListing`:
  - `listing_id` ← `BuffListing.listing_id`
  - `goods_id` ← `BuffListing.goods_id`
  - `market_hash_name` ← `BuffListing.market_hash_name` (may be `None`)
  - `price_cny` ← `BuffListing.price_cny`
  - `paintwear` ← `BuffListing.paintwear` (Decimal → Decimal passthrough; no float conversion at this layer)
  - `asset_id` ← `BuffListing.asset_id`
  - `source` ← `BuffListing.source`
- FR-3.2 `stattrak` and `souvenir` default to `False`. The adapter does NOT receive them from `BuffListing` in the current contract.
- FR-3.3 When `BuffListing.market_hash_name is None`, the adapter returns a candidate with `market_hash_name=None`. It does NOT raise and does NOT return a rejection (the rejection happens downstream in `TradeUpInputEnrichment` as `MARKET_HASH_NAME_UNRESOLVED`).
- FR-3.4 The adapter enforces the rejection vocabulary on:
  - `MISSING_PRICE` — `price_cny` not a `Decimal`, not finite, or `<= 0`.
  - `INVALID_FLOAT` — `paintwear` not a `Decimal`, not finite, or outside `[0.0, 1.0]`.
  - `MISSING_ASSET_ID` — `asset_id` not a non-empty stripped string.
  - `UNSUPPORTED_SOURCE` — `source` not in the closed allowlist (currently `{"buff"}`).
- FR-3.5 `MISSING_IDENTITY` is reserved for an explicit refusal mode; it is NOT triggered by `market_hash_name is None` in this phase (FR-3.3 governs that case).

### FR-4 — Identity handling

- FR-4.1 The adapter does not consult any identity resolver.
- FR-4.2 The adapter does not derive, guess, infer, or fabricate `market_hash_name`.
- FR-4.3 When a future identity source becomes available (out of scope here), the adapter reads the resolved name from the upstream listing DTO; the adapter itself does not own the derivation.

### FR-5 — Field ownership rationale

- FR-5.1 Candidate-owned fields are exactly those that describe a specific listing instance, not a catalog row: `market_hash_name`, `price_cny`, `paintwear`, `asset_id`, `source`, `stattrak`, `souvenir`. They are values that vary per listing.
- FR-5.2 Metadata-owned fields describe the catalog row (collection / rarity / float band). They do NOT appear on `TradeUpInputCandidate`; they enter the seam via `TradeUpInputEnrichment`. The adapter does not enrich; it only normalizes per-listing fields.
- FR-5.3 The adapter does not invent or carry `collection_name`, `rarity`, `min_float`, or `max_float`. Adding any of those to the candidate boundary would violate `D-ENRICH-001`.

### FR-6 — Integration boundary

- FR-6.1 The adapter takes already-acquired `BuffListing` values as input. It does not call `BuffListingProvider`.
- FR-6.2 The future production wiring (separate phase) iterates the provider's listings and feeds each through the adapter; the adapter output then enters `enrich_candidates(...)`.
- FR-6.3 Dependency direction remains: `BuffListingProvider → BuffListing → adapter → TradeUpInputCandidate → TradeUpInputEnrichment → InputItem → engine`. No backward edges.

## Non-Functional Requirements

- NFR-1 Determinism: two conversions of the same `BuffListing` produce byte-equal `TradeUpInputCandidate` values.
- NFR-2 Repr / str safety: `CandidateAdapterRejection.__repr__()` and `__str__()` expose no value field of the rejected listing.
- NFR-3 Static dependency guards: a test file (per FR-7) reads `app/services/buff_listing_candidate_adapter.py` source and asserts no Protected Core / live / external token appears.
- NFR-4 No new third-party dependency.
- NFR-5 Public API exactness: `__all__` is the exact 5-tuple listed in FR-2.1.

## Out of Scope (frozen here)

- No identity resolver, no identity guessing, no SteamDT / SteamApis identity mapping.
- No live BUFF / SteamDT / SteamApis endpoint call.
- No scanner / scheduler / webhook / purchase / database / cache wiring.
- No modification to `BuffListingProvider`, `BuffListing`, `BuffListingObservation`, `BuffTradableCandidate`, `BuffItemIdentity`, or `BuffItemIdentityResolver`.
- No modification to `TradeUpInputEnrichment`, `TradeUpInputCandidate`, `tradeup_engine`, `recipe_solver`, `ev_service`, `risk_filter`, `metadata_*`.
- No production / scheduler wiring that consumes the adapter output.
- No JSON / CSV / log report file.
- No diagnostic counters on production DTOs.
- No change to `BuffListing.source` semantics; the adapter only enforces a closed allowlist.

## Acceptance

This design passes if the future implementation phase:

- Adds `app/services/buff_listing_candidate_adapter.py` and `tests/test_buff_listing_candidate_adapter.py`.
- Honors all FR-* and NFR-* requirements.
- Passes the static dependency guards and `__all__` exactness test.
- Leaves all Protected Core modules untouched.
- Reproduces byte-equal candidates across two reruns.